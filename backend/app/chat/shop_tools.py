# =============================================================================
# chat/shop_tools.py  -  The ONLY things the customer chatbot is allowed to do
# -----------------------------------------------------------------------------
# Security model: the language model never writes SQL here. It can only ask to
# call one of these functions with simple arguments. Each function runs a fixed,
# parameterised query that returns safe, customer-facing information.
#
# The logged-in customer id is passed by the SERVER (from the request), never by
# the model - so a customer can only ever see their own orders, whatever they type.
# =============================================================================

from ..db import fetch_all, fetch_one
from ..llm import embed, to_pgvector


def _has_images() -> bool:
    """Product photos are optional (ai/fetch_product_images.py creates the table)."""
    row = fetch_one("SELECT to_regclass('ai.product_images') IS NOT NULL AS ok")
    return bool(row and row["ok"])

# ---------------------------------------------------------------------------
# Tool descriptions sent to the model (OpenAI "function calling" format).
# The model reads the descriptions to decide which tool fits the question.
# ---------------------------------------------------------------------------
TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the Cottonil catalog by meaning (Arabic or English), e.g. "
                           "'light cotton t-shirt for summer', 'بوكسر رجالي', 'kids pajamas'. "
                           "Returns matching products with sizes, colours and prices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What the customer is looking for"},
                    "max_price": {"type": "number", "description": "Optional max price in EGP"},
                    "size": {"type": "string", "description": "Optional size, e.g. M, L, XL, 2XL, Free, 4 (kids age)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_branches",
            "description": "List Cottonil branches and points of sale in a governorate "
                           "(Arabic name, e.g. القاهرة، الإسكندرية، الجيزة).",
            "parameters": {
                "type": "object",
                "properties": {"governorate": {"type": "string"}},
                "required": ["governorate"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_policy",
            "description": "Answer questions about returns, exchanges, refunds, delivery, shipping, "
                           "payment methods, size guide, product care and the reseller program.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "my_orders",
            "description": "List the logged-in customer's most recent orders.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "How many orders (max 10)"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "track_order",
            "description": "Status of one of the logged-in customer's orders: items, total, "
                           "delivery and returns. Needs the order id, e.g. SO000123.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_suggestions",
            "description": "For resellers / repeat buyers: the products they buy most, when they "
                           "last bought them, and a suggested reorder.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "purchase_summary",
            "description": "The logged-in customer's total purchases per year (orders, units, amount).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

LOGIN_REQUIRED = {"error": "login_required",
                  "message": "The customer must be logged in to see orders or purchase history."}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def search_products(query: str, max_price: float | None = None, size: str | None = None, **_):
    qvec = to_pgvector(embed([query])[0])
    conds, params = ["TRUE"], {"q": qvec}
    if max_price:
        conds.append("e.min_price <= %(max_price)s")
        params["max_price"] = max_price
    if size:
        conds.append("EXISTS (SELECT 1 FROM gold.dim_product p WHERE p.product_id = e.product_id "
                     "AND upper(p.size) = upper(%(size)s))")
        params["size"] = size
    images = _has_images()
    img_col = "i.image_url" if images else "NULL"
    img_join = "LEFT JOIN ai.product_images i ON i.product_id = e.product_id" if images else ""
    rows = fetch_all(f"""
        SELECT e.product_id, e.name_ar AS name, e.category, e.audience, e.sizes, e.colors,
               round(e.min_price) AS min_price, round(e.max_price) AS max_price, e.url,
               {img_col} AS image_url,
               round((1 - (e.embedding <=> %(q)s::vector))::numeric, 3) AS similarity
        FROM ai.product_embeddings e
        {img_join}
        WHERE {' AND '.join(conds)}
        ORDER BY e.embedding <=> %(q)s::vector
        LIMIT 5
    """, params)
    return {"products": rows} if rows else {"products": [], "message": "No matching products."}


def find_branches(governorate: str, **_):
    rows = fetch_all("""
        SELECT b.branch_display_name AS name, b.governorate_ar AS governorate, b.city_ar AS city,
               b.retail_location_type AS type, s.address_ar AS address
        FROM gold.dim_branch b
        JOIN silver.branches s USING (branch_id)
        WHERE b.governorate_ar ILIKE '%%' || %(g)s || '%%' OR %(g)s ILIKE '%%' || b.governorate_ar || '%%'
        ORDER BY b.retail_location_type, b.branch_display_name
    """, {"g": governorate.strip()})
    if rows:
        return {"branches": rows}
    govs = [r["governorate_ar"] for r in fetch_all(
        "SELECT DISTINCT governorate_ar FROM gold.dim_branch ORDER BY 1")]
    return {"branches": [], "message": "No branch in that governorate.", "governorates_with_branches": govs}


def store_policy(question: str, **_):
    qvec = to_pgvector(embed([question])[0])
    rows = fetch_all("""
        SELECT title, content FROM ai.kb_chunks
        ORDER BY embedding <=> %(q)s::vector LIMIT 3
    """, {"q": qvec})
    return {"policy_sections": rows,
            "note": "Demo policy text written for this project, not the official Cottonil policy."}


def my_orders(customer_id: str | None, limit: int = 5, **_):
    if not customer_id:
        return LOGIN_REQUIRED
    rows = fetch_all("""
        SELECT sales_order_id AS order_id, order_date, sales_channel AS channel, sold_units AS units,
               round(paid_total_egp, 2) AS total_paid_egp, return_level,
               fulfillment_status AS delivery_status
        FROM gold.fact_orders WHERE customer_key = %(c)s
        ORDER BY order_date DESC LIMIT %(n)s
    """, {"c": customer_id, "n": max(1, min(int(limit or 5), 10))})
    return {"orders": rows}


def track_order(customer_id: str | None, order_id: str, **_):
    if not customer_id:
        return LOGIN_REQUIRED
    order = fetch_one("""
        SELECT o.sales_order_id AS order_id, o.order_date, o.sales_channel AS channel,
               o.payment_method, round(o.paid_total_egp, 2) AS total_paid_egp,
               o.return_level, round(o.refund_egp, 2) AS refunded_egp,
               o.carrier, o.ship_date, o.delivery_date, o.delivery_days, o.fulfillment_status,
               b.branch_display_name AS branch
        FROM gold.fact_orders o JOIN gold.dim_branch b ON b.branch_id = o.branch_id
        WHERE o.sales_order_id = upper(%(o)s) AND o.customer_key = %(c)s
    """, {"o": order_id.strip(), "c": customer_id})
    if not order:
        # same answer whether the order doesn't exist or belongs to someone else
        return {"error": "not_found", "message": "No order with this id on your account."}
    items = fetch_all("""
        SELECT p.product_name_ar AS product, p.size, p.color_ar AS colour, s.quantity,
               s.returned_units, round(s.net_sales_egp, 2) AS amount_before_vat_egp
        FROM gold.fact_sales_line s JOIN gold.dim_product p ON p.sku_id = s.sku_id
        WHERE s.sales_order_id = %(o)s
    """, {"o": order["order_id"]})
    return {"order": order, "items": items}


def reorder_suggestions(customer_id: str | None, **_):
    if not customer_id:
        return LOGIN_REQUIRED
    rows = fetch_all("""
        SELECT p.product_name_ar AS product, p.category,
               SUM(s.quantity - s.returned_units) AS units_bought,
               COUNT(DISTINCT s.sales_order_id) AS times_ordered,
               MAX(s.order_date) AS last_bought,
               round(SUM(s.quantity - s.returned_units)::numeric
                     / GREATEST(COUNT(DISTINCT s.sales_order_id), 1)) AS suggested_reorder_units
        FROM gold.fact_sales_line s JOIN gold.dim_product p ON p.sku_id = s.sku_id
        WHERE s.customer_key = %(c)s
        GROUP BY 1, 2 ORDER BY units_bought DESC LIMIT 8
    """, {"c": customer_id})
    return {"top_products": rows} if rows else {"top_products": [], "message": "No purchase history yet."}


def purchase_summary(customer_id: str | None, **_):
    if not customer_id:
        return LOGIN_REQUIRED
    rows = fetch_all("""
        SELECT EXTRACT(YEAR FROM order_date)::int AS year, COUNT(*) AS orders,
               SUM(sold_units) AS units, round(SUM(paid_total_egp), 2) AS total_paid_egp
        FROM gold.fact_orders WHERE customer_key = %(c)s
        GROUP BY 1 ORDER BY 1
    """, {"c": customer_id})
    return {"years": rows}


TOOLS = {
    "search_products": search_products,
    "find_branches": find_branches,
    "store_policy": store_policy,
    "my_orders": my_orders,
    "track_order": track_order,
    "reorder_suggestions": reorder_suggestions,
    "purchase_summary": purchase_summary,
}
CUSTOMER_TOOLS = {"my_orders", "track_order", "reorder_suggestions", "purchase_summary"}