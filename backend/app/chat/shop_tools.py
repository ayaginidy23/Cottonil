# =============================================================================
# chat/shop_tools.py  -  The ONLY things the customer chatbot is allowed to do
# -----------------------------------------------------------------------------
# Security model: the language model never writes SQL here. It can only ask to
# call one of these functions with simple arguments. Each function runs a fixed,
# parameterised query that returns safe, customer-facing information.
#
# The logged-in customer id is passed by the SERVER (from the request), never by
# the model - so a customer can only ever see their own orders, whatever they type.
#
# Tools (14):
#   catalog     search_products, compare_products, bought_together, size_advice
#   offers      current_offers (from app.promotions, managed on the Offers page)
#   store       find_branches, store_policy
#   cart        add_to_cart, remove_from_cart  (the cart lives in the browser; the
#               tool only checks the product/size exists and returns the real price)
#   reseller    b2b_quote (price quote with demo wholesale tiers, saved for the PDF)
#   my account  my_orders, track_order, reorder_suggestions, purchase_summary
# =============================================================================

import json
import re
import secrets
from datetime import date, timedelta

from ..db import fetch_all, fetch_one, pool
from ..llm import embed, to_pgvector
from ..promotions import active_offers
from ..security_log import log_event


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
    {
        "type": "function",
        "function": {
            "name": "current_offers",
            "description": "The offers and discounts running today (e.g. 15% off a category, discount "
                           "for 3+ pieces). Use it whenever the customer asks about offers, sales, "
                           "discounts, عروض، خصومات، تخفيضات.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string", "description": "Optional: only offers for this category"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_products",
            "description": "Compare 2-4 products side by side (category, audience, sizes, colours, "
                           "price range, photo). Use product ids from search_products, or names.",
            "parameters": {
                "type": "object",
                "properties": {"products": {"type": "array", "items": {"type": "string"},
                                            "description": "2-4 product ids (e.g. PR0012) or names"}},
                "required": ["products"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bought_together",
            "description": "Complete the look: matching items to wear with this product (uses real "
                           "'bought together' patterns only when they are strong).",
            "parameters": {
                "type": "object",
                "properties": {"product": {"type": "string", "description": "Product id or name"}},
                "required": ["product"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "size_advice",
            "description": "Recommend a size from the customer's body measurements. Ask for height "
                           "and weight (or waist), or the child's age for kids. Optionally pass the "
                           "product to check that the size exists for it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "audience": {"type": "string", "enum": ["men", "women", "kids"]},
                    "height_cm": {"type": "number"},
                    "weight_kg": {"type": "number"},
                    "waist_cm": {"type": "number"},
                    "age_years": {"type": "number", "description": "Kids only"},
                    "fit": {"type": "string", "enum": ["regular", "relaxed", "tight"]},
                    "product": {"type": "string", "description": "Optional product id or name"},
                },
                "required": ["audience"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a product in a given size (and optional colour) to the customer's "
                           "cart. Ask for the size first if the customer did not say it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product": {"type": "string", "description": "Product id or name"},
                    "size": {"type": "string"},
                    "color": {"type": "string", "description": "Optional colour (Arabic as in the catalog)"},
                    "quantity": {"type": "integer"},
                },
                "required": ["product", "size"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove a product (optionally only one size) from the cart.",
            "parameters": {
                "type": "object",
                "properties": {"product": {"type": "string"}, "size": {"type": "string"}},
                "required": ["product"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "b2b_quote",
            "description": "Create a wholesale price quote (downloadable PDF) for a reseller or company "
                           "that wants many units: list prices, volume discount and total.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product": {"type": "string", "description": "Product id or name"},
                                "quantity": {"type": "integer"},
                                "size": {"type": "string", "description": "Optional"},
                            },
                            "required": ["product", "quantity"],
                        },
                    },
                    "company_name": {"type": "string", "description": "Optional company / shop name"},
                },
                "required": ["items"],
            },
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
    url_col = "COALESCE(i.product_url, e.url)" if images else "e.url"   # real product page when known
    img_join = "LEFT JOIN ai.product_images i ON i.product_id = e.product_id" if images else ""
    rows = fetch_all(f"""
        SELECT e.product_id, e.name_ar AS name, e.category, e.audience, e.sizes, e.colors,
               round(e.min_price) AS min_price, round(e.max_price) AS max_price, {url_col} AS url,
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


def _login_required(tool: str):
    log_event("shop", "login_required", "asked the guest to log in", None, tool=tool)
    return LOGIN_REQUIRED


def my_orders(customer_id: str | None, limit: int = 5, **_):
    if not customer_id:
        return _login_required("my_orders")
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
        return _login_required("track_order")
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
        # same answer whether the order doesn't exist or belongs to someone else;
        # if it exists on another account, write it in the security log
        if fetch_one("SELECT 1 AS x FROM gold.fact_orders WHERE sales_order_id = upper(%(o)s)",
                     {"o": order_id.strip()}):
            log_event("shop", "other_customer_order", "refused - order belongs to another account",
                      f"cust:{customer_id}", order_id=order_id.strip().upper())
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
        return _login_required("reorder_suggestions")
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
        return _login_required("purchase_summary")
    rows = fetch_all("""
        SELECT EXTRACT(YEAR FROM order_date)::int AS year, COUNT(*) AS orders,
               SUM(sold_units) AS units, round(SUM(paid_total_egp), 2) AS total_paid_egp
        FROM gold.fact_orders WHERE customer_key = %(c)s
        GROUP BY 1 ORDER BY 1
    """, {"c": customer_id})
    return {"years": rows}


# ---------------------------------------------------------------------------
# Shared helpers for the catalog tools
# ---------------------------------------------------------------------------
SIZE_ORDER = ["2", "3", "4", "5", "6", "7", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "FREE"]
SIZE_RANK_SQL = ("COALESCE(array_position(ARRAY['" + "','".join(SIZE_ORDER) + "'], upper(size)), 99)")


def resolve_product(product: str | None) -> str | None:
    """Accept a product id (PR0012) or a (part of a) product name; return the product id."""
    if not product:
        return None
    text = str(product).strip()
    row = fetch_one("SELECT product_id FROM gold.dim_product WHERE product_id = upper(%(p)s) LIMIT 1",
                    {"p": text})
    if not row:
        row = fetch_one("""
            SELECT product_id FROM gold.dim_product
            WHERE product_name_ar ILIKE '%%' || %(p)s || '%%' OR %(p)s ILIKE '%%' || product_name_ar || '%%'
            ORDER BY length(product_name_ar) LIMIT 1""", {"p": text})
    return row["product_id"] if row else None


def product_cards(ids: list[str]) -> list[dict]:
    """Customer-safe product info (no sales, no costs), in the order of `ids`."""
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return []
    images = _has_images()
    img_col = "MAX(i.image_url)" if images else "NULL"
    url_col = "COALESCE(MAX(i.product_url), MIN(p.source_url))" if images else "MIN(p.source_url)"
    img_join = "LEFT JOIN ai.product_images i ON i.product_id = p.product_id" if images else ""
    rows = fetch_all(f"""
        WITH sz AS (
            SELECT product_id, string_agg(size, ', ' ORDER BY rnk) AS sizes
            FROM (SELECT DISTINCT product_id, size, {SIZE_RANK_SQL} AS rnk FROM gold.dim_product
                  WHERE product_id = ANY(%(ids)s)) t GROUP BY 1
        )
        SELECT p.product_id, MIN(p.product_name_ar) AS name, MIN(p.category) AS category,
               MIN(p.audience) AS audience, MIN(sz.sizes) AS sizes,
               string_agg(DISTINCT p.color_ar, ', ') AS colors,
               round(MIN(p.sku_list_price_egp)) AS min_price, round(MAX(p.sku_list_price_egp)) AS max_price,
               {url_col} AS url, {img_col} AS image_url
        FROM gold.dim_product p
        JOIN sz ON sz.product_id = p.product_id
        {img_join}
        WHERE p.product_id = ANY(%(ids)s)
        GROUP BY p.product_id
    """, {"ids": ids})
    by_id = {r["product_id"]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


# ---------------------------------------------------------------------------
# Offers (app.promotions)
# ---------------------------------------------------------------------------
def current_offers(category: str | None = None, **_):
    offers = active_offers()
    if category:
        c = category.strip().lower()
        offers = [o for o in offers if o["scope"] != "category" or c in (o["target"] or "").lower()
                  or (o["target"] or "").lower() in c]
    if not offers:
        return {"offers": [], "message": "No offers are running today."}
    return {"offers": [{
        "title_ar": o["title_ar"], "title_en": o["title_en"],
        "discount": f"{float(o['discount_pct']) * 100:.0f}%",
        "applies_to": ("the whole order with " + str(o["min_units"]) + "+ pieces") if o["scope"] == "order"
                      else f"{o['scope']}: {o['target']}",
        "ends_on": str(o["ends_on"]),
    } for o in offers],
        "rule": "The cart applies the best offer automatically; offers are not combined. "
                "Wholesale quotes use the volume tiers instead."}


# ---------------------------------------------------------------------------
# K - compare products
# ---------------------------------------------------------------------------
def compare_products(products: list[str] | None = None, **_):
    ids = [resolve_product(p) for p in (products or [])[:4]]
    found = product_cards([i for i in ids if i])
    if len(found) < 2:
        return {"error": "need_two_products", "message": "Find at least two products first (search_products)."}
    return {"comparison": found, "products": found}


# ---------------------------------------------------------------------------
# F - complete the look / bought together (market basket, ml/market_basket.py)
# ---------------------------------------------------------------------------
MIN_LIFT = 1.05      # below this, "bought together" is just chance


def bought_together(product: str, **_):
    pid = resolve_product(product)
    if not pid:
        return {"error": "not_found", "message": "Product not found - search for it first."}
    pairs = []
    if fetch_one("SELECT to_regclass('gold.ml_product_pairs') IS NOT NULL AS ok")["ok"]:
        pairs = [r["product_b"] for r in fetch_all("""
            SELECT product_b FROM gold.ml_product_pairs
            WHERE product_a = %(p)s AND lift >= %(l)s ORDER BY lift DESC, together DESC LIMIT 4
        """, {"p": pid, "l": MIN_LIFT})]
    if pairs:
        return {"basis": "Customers who bought this product often bought these too.",
                "for_product": pid, "products": product_cards(pairs)}
    # No strong pattern in the orders: suggest popular items of OTHER categories for the
    # same audience (a matching outfit), so the customer still gets a useful answer.
    rows = fetch_all("""
        WITH me AS (SELECT MIN(category) AS category, MIN(audience) AS audience
                    FROM gold.dim_product WHERE product_id = %(p)s)
        SELECT p.product_id
        FROM gold.dim_product p CROSS JOIN me
        LEFT JOIN gold.fact_sales_line s ON s.sku_id = p.sku_id
        WHERE p.category <> me.category AND p.audience = me.audience
        GROUP BY p.product_id, p.category
        ORDER BY ROW_NUMBER() OVER (PARTITION BY p.category ORDER BY COUNT(s.sales_line_id) DESC),
                 COUNT(s.sales_line_id) DESC
        LIMIT 4
    """, {"p": pid})
    return {"basis": "No strong 'bought together' pattern for this product, so these are matching "
                     "items from other categories for the same audience.",
            "for_product": pid, "products": product_cards([r["product_id"] for r in rows])}


# ---------------------------------------------------------------------------
# G - size advisor (DEMO size chart: Cottonil does not publish an official one)
# ---------------------------------------------------------------------------
ADULT_SIZES = ["M", "L", "XL", "2XL", "3XL", "4XL"]
# upper weight limit (kg) and waist limit (cm) of each adult size
WEIGHT_CHART = {"men": [72, 82, 92, 104, 116, 999], "women": [64, 74, 84, 94, 104, 999]}
WAIST_CHART = {"men": [84, 92, 100, 108, 116, 999], "women": [78, 86, 94, 102, 110, 999]}
KIDS_HEIGHT = [(2, 95), (3, 101), (4, 107), (5, 113), (6, 119), (7, 999)]   # (age size, max height cm)


def _pick(limits: list[int], value: float) -> int:
    return next(i for i, lim in enumerate(limits) if value <= lim)


def size_advice(audience: str = "men", height_cm: float | None = None, weight_kg: float | None = None,
                waist_cm: float | None = None, age_years: float | None = None, fit: str = "regular",
                product: str | None = None, **_):
    audience = (audience or "men").lower()
    notes = []
    if audience == "kids":
        if not age_years and not height_cm:
            return {"need": "the child's age (years) or height (cm)"}
        size_by_age = int(min(max(round(age_years), 2), 7)) if age_years else None
        size_by_height = next(a for a, h in KIDS_HEIGHT if height_cm <= h) if height_cm else None
        size = str(max(s for s in (size_by_age, size_by_height) if s))   # tall child -> bigger size
        if fit == "relaxed" and int(size) < 7:
            size = str(int(size) + 1)
        notes.append("Kids sizes are the age in years.")
    else:
        key = "women" if audience.startswith("w") else "men"
        if not weight_kg and not waist_cm:
            return {"need": "height and weight (kg), or waist (cm)"}
        idx = max(_pick(WEIGHT_CHART[key], weight_kg) if weight_kg else 0,
                  _pick(WAIST_CHART[key], waist_cm) if waist_cm else 0)
        tall = height_cm and height_cm >= (185 if key == "men" else 175)
        if tall:
            idx += 1
            notes.append("Tall body: one size up for length.")
        if fit == "relaxed":
            idx += 1
        elif fit == "tight":
            idx -= 1
        idx = min(max(idx, 0), len(ADULT_SIZES) - 1)
        size = ADULT_SIZES[idx]
    notes.append("Between two sizes? Take the bigger one: cotton can shrink a little after the first wash.")

    result = {"recommended_size": size, "fit": fit or "regular", "notes": notes,
              "chart": "Demo size chart for this project (not an official Cottonil chart)."}
    pid = resolve_product(product) if product else None
    if pid:
        sizes = [r["size"] for r in fetch_all(f"""
            SELECT DISTINCT size, {SIZE_RANK_SQL} AS rnk FROM gold.dim_product
            WHERE product_id = %(p)s ORDER BY rnk""", {"p": pid})]
        result["product_sizes"] = sizes
        if size.upper() not in [x.upper() for x in sizes]:
            if any(x.upper() == "FREE" for x in sizes):
                result["note_for_product"] = "This product comes in one free size."
            else:
                ranks = {x: SIZE_ORDER.index(x.upper()) for x in sizes if x.upper() in SIZE_ORDER}
                want = SIZE_ORDER.index(size.upper()) if size.upper() in SIZE_ORDER else 0
                bigger = [x for x, r in sorted(ranks.items(), key=lambda kv: kv[1]) if r >= want]
                result["note_for_product"] = (f"Size {size} is not made for this product; the closest is "
                                              f"{bigger[0] if bigger else (sizes[-1] if sizes else '-')}.")
        result["products"] = product_cards([pid])
    return result


# ---------------------------------------------------------------------------
# I - cart (kept in the browser; checkout sends the order by WhatsApp)
# ---------------------------------------------------------------------------
def add_to_cart(product: str, size: str, color: str | None = None, quantity: int = 1, **_):
    pid = resolve_product(product)
    if not pid:
        return {"error": "not_found", "message": "Product not found - search for it first."}
    sku = fetch_one("""
        SELECT sku_id, product_id, product_name_ar AS name, size, color_ar AS color,
               category, audience, round(sku_list_price_egp) AS unit_price
        FROM gold.dim_product
        WHERE product_id = %(p)s AND upper(size) = upper(%(s)s)
        ORDER BY (color_ar = COALESCE(%(c)s, '')) DESC, color_ar NULLS LAST
        LIMIT 1""", {"p": pid, "s": str(size).strip(), "c": color})
    if not sku:
        sizes = [r["size"] for r in fetch_all(
            f"SELECT DISTINCT size, {SIZE_RANK_SQL} AS rnk FROM gold.dim_product "
            "WHERE product_id = %(p)s ORDER BY rnk", {"p": pid})]
        return {"error": "size_not_available", "available_sizes": sizes}
    qty = max(1, min(int(quantity or 1), 500))
    card = product_cards([pid])
    item = {**sku, "quantity": qty, "image_url": card[0]["image_url"] if card else None,
            "url": card[0]["url"] if card else None}
    if color and sku["color"] != color:
        item["note"] = f"Colour '{color}' not found, added {sku['color']}."
    return {"cart_action": {"type": "add", "item": item}, "added": item}


def remove_from_cart(product: str, size: str | None = None, **_):
    pid = resolve_product(product)
    if not pid:
        return {"error": "not_found"}
    return {"cart_action": {"type": "remove", "product_id": pid, "size": size}, "removed": pid}


# ---------------------------------------------------------------------------
# J - B2B price quote (DEMO wholesale tiers), saved so the PDF page can load it
# ---------------------------------------------------------------------------
WHOLESALE_TIERS = [(300, 0.15), (100, 0.10), (24, 0.05), (0, 0.0)]    # (min total units, discount)
QUOTE_VALID_DAYS = 7
QUOTE_DDL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.b2b_quotes (
    quote_id     TEXT PRIMARY KEY,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    customer_key TEXT,
    quote        JSONB NOT NULL
);
"""


def b2b_quote(items: list[dict] | None = None, company_name: str | None = None,
              customer_id: str | None = None, **_):
    lines, problems = [], []
    for it in (items or [])[:30]:
        pid = resolve_product(it.get("product"))
        qty = int(it.get("quantity") or 0)
        if not pid or qty <= 0:
            problems.append(str(it.get("product")))
            continue
        size = it.get("size")
        row = fetch_one("""
            SELECT MIN(product_name_ar) AS name, MIN(category) AS category,
                   round(AVG(sku_list_price_egp), 2) AS unit_price
            FROM gold.dim_product
            WHERE product_id = %(p)s AND (%(s)s::text IS NULL OR upper(size) = upper(%(s)s::text))
        """, {"p": pid, "s": size})
        if not row or row["unit_price"] is None:
            problems.append(f"{it.get('product')} size {size}")
            continue
        lines.append({"product_id": pid, "name": row["name"], "category": row["category"],
                      "size": size or "assorted", "quantity": qty, "unit_price": float(row["unit_price"]),
                      "line_total": round(float(row["unit_price"]) * qty, 2)})
    if not lines:
        return {"error": "no_valid_items", "message": "Could not find these products.", "not_found": problems}

    units = sum(l["quantity"] for l in lines)
    discount_pct = next(d for minimum, d in WHOLESALE_TIERS if units >= minimum)
    subtotal = round(sum(l["line_total"] for l in lines), 2)
    discount = round(subtotal * discount_pct, 2)
    next_tier = next(((m, d) for m, d in sorted(WHOLESALE_TIERS) if m > units), None)
    customer = None
    if customer_id:
        customer = fetch_one("SELECT customer_key, customer_segment, governorate_ar FROM gold.dim_customer "
                             "WHERE customer_key = %(c)s", {"c": customer_id})
    quote = {
        "quote_id": f"Q-{date.today():%Y%m%d}-{secrets.token_hex(2).upper()}",
        "date": date.today().isoformat(),
        "valid_until": (date.today() + timedelta(days=QUOTE_VALID_DAYS)).isoformat(),
        "company_name": (company_name or "").strip()[:80] or None,
        "customer": customer,
        "lines": lines,
        "total_units": units,
        "subtotal": subtotal,
        "discount_pct": discount_pct,
        "discount": discount,
        "total": round(subtotal - discount, 2),
        "next_tier": {"min_units": next_tier[0], "discount_pct": next_tier[1],
                      "units_missing": next_tier[0] - units} if next_tier else None,
        "tiers": [{"min_units": m, "discount_pct": d} for m, d in sorted(WHOLESALE_TIERS) if m > 0],
        "note": "Demo wholesale tiers for this project, list prices in EGP. Final prices are confirmed "
                "by the Cottonil wholesale team.",
    }
    try:
        with pool.connection() as conn:
            conn.execute(QUOTE_DDL)
            conn.execute("INSERT INTO app.b2b_quotes (quote_id, customer_key, quote) VALUES (%(q)s, %(c)s, %(j)s::jsonb)",
                         {"q": quote["quote_id"], "c": customer_id, "j": json.dumps(quote, ensure_ascii=False, default=str)})
    except Exception as e:
        print(f"WARNING: quote not saved: {e}")
    if problems:
        quote["not_found"] = problems
    return {"quote": quote}


def get_quote(quote_id: str) -> dict | None:
    if not re.fullmatch(r"Q-\d{8}-[0-9A-F]{4}", quote_id or ""):
        return None
    try:
        row = fetch_one("SELECT quote FROM app.b2b_quotes WHERE quote_id = %(q)s", {"q": quote_id})
    except Exception:
        return None
    return row["quote"] if row else None


TOOLS = {
    "search_products": search_products,
    "current_offers": current_offers,
    "compare_products": compare_products,
    "bought_together": bought_together,
    "size_advice": size_advice,
    "find_branches": find_branches,
    "store_policy": store_policy,
    "add_to_cart": add_to_cart,
    "remove_from_cart": remove_from_cart,
    "b2b_quote": b2b_quote,
    "my_orders": my_orders,
    "track_order": track_order,
    "reorder_suggestions": reorder_suggestions,
    "purchase_summary": purchase_summary,
}
# tools that receive the logged-in customer id from the SERVER
CUSTOMER_TOOLS = {"my_orders", "track_order", "reorder_suggestions", "purchase_summary", "b2b_quote"}
