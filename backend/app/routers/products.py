# =============================================================================
# routers/products.py  -  Product gallery, product page and what-if simulator
#   GET /api/products              -> every catalog product with photo + key numbers
#   GET /api/products/{id}         -> one product: KPIs, monthly units, sizes, colours,
#                                     best branches, category forecast
#   GET /api/simulator/baseline    -> last 12 complete months per category, the
#                                     starting point of the discount what-if simulator
# All endpoints use the same global filters as the dashboards (date range,
# branches, channels), through the same safe build_where().
# =============================================================================

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..chat.shop_tools import SIZE_RANK_SQL, _has_images
from ..db import fetch_all, fetch_one
from ..filters import Filters, build_where

router = APIRouter(prefix="/api", tags=["products"])

SALES_COLUMNS = {"date": "s.order_date", "branch": "s.branch_id", "channel": "s.sales_channel"}


def _filters(date_from, date_to, branch, channel) -> Filters:
    return Filters(date_from=date_from, date_to=date_to,
                   branches=tuple(sorted(branch)), channels=tuple(sorted(channel)))


def _image_parts():
    if _has_images():
        return ("MAX(i.image_url)", "COALESCE(MAX(i.product_url), MIN(p.source_url))",
                "LEFT JOIN ai.product_images i ON i.product_id = p.product_id")
    return "NULL", "MIN(p.source_url)", ""


@router.get("/products")
def list_products(date_from: date | None = None, date_to: date | None = None,
                  branch: list[str] = Query(default=[]), channel: list[str] = Query(default=[])):
    where, params = build_where(SALES_COLUMNS, _filters(date_from, date_to, branch, channel))
    img, url, join = _image_parts()
    return fetch_all(f"""
        WITH sales AS (
            SELECT s.product_id,
                   SUM(s.quantity - s.returned_units) AS units,
                   SUM(s.net_sales_after_returns_egp) AS net_sales,
                   SUM(s.margin_after_returns_egp) / NULLIF(SUM(s.net_sales_after_returns_egp), 0) AS margin_pct,
                   SUM(s.returned_units)::numeric / NULLIF(SUM(s.quantity), 0) AS return_rate
            FROM gold.fact_sales_line s WHERE {where} GROUP BY 1
        )
        SELECT p.product_id, MIN(p.product_name_ar) AS name, MIN(p.category) AS category,
               MIN(p.audience) AS audience,
               round(MIN(p.sku_list_price_egp)) AS min_price, round(MAX(p.sku_list_price_egp)) AS max_price,
               COUNT(DISTINCT p.size) AS sizes, COUNT(DISTINCT p.color_ar) AS colors,
               {img} AS image_url, {url} AS url,
               MAX(sl.units) AS units, MAX(sl.net_sales) AS net_sales,
               MAX(sl.margin_pct) AS margin_pct, MAX(sl.return_rate) AS return_rate
        FROM gold.dim_product p
        LEFT JOIN sales sl ON sl.product_id = p.product_id
        {join}
        GROUP BY p.product_id
        ORDER BY MAX(sl.net_sales) DESC NULLS LAST
    """, params)


@router.get("/products/{product_id}")
def product_detail(product_id: str, date_from: date | None = None, date_to: date | None = None,
                   branch: list[str] = Query(default=[]), channel: list[str] = Query(default=[])):
    f = _filters(date_from, date_to, branch, channel)
    where, params = build_where(SALES_COLUMNS, f)
    params = {**params, "pid": product_id.upper()}
    img, url, join = _image_parts()
    info = fetch_one(f"""
        SELECT p.product_id, MIN(p.product_name_ar) AS name, MIN(p.category) AS category,
               MIN(p.audience) AS audience, MIN(p.size_group) AS size_group,
               round(MIN(p.sku_list_price_egp)) AS min_price, round(MAX(p.sku_list_price_egp)) AS max_price,
               COUNT(DISTINCT p.sku_id) AS skus, {img} AS image_url, {url} AS url
        FROM gold.dim_product p {join}
        WHERE p.product_id = %(pid)s GROUP BY p.product_id
    """, params)
    if not info:
        raise HTTPException(404, "Unknown product")

    kpis = fetch_one(f"""
        SELECT SUM(s.quantity - s.returned_units) AS units,
               SUM(s.net_sales_after_returns_egp) AS net_sales,
               SUM(s.margin_after_returns_egp) / NULLIF(SUM(s.net_sales_after_returns_egp), 0) AS margin_pct,
               SUM(s.returned_units)::numeric / NULLIF(SUM(s.quantity), 0) AS return_rate,
               SUM(s.discount_egp) / NULLIF(SUM(s.net_sales_egp + s.discount_egp), 0) AS discount_rate,
               COUNT(DISTINCT s.customer_key) FILTER (WHERE s.customer_key <> 'GUEST') AS customers,
               COUNT(DISTINCT s.sales_order_id) AS orders
        FROM gold.fact_sales_line s WHERE s.product_id = %(pid)s AND {where}
    """, params)
    share = fetch_one(f"""
        SELECT SUM(s.net_sales_after_returns_egp) FILTER (WHERE s.product_id = %(pid)s)
                 / NULLIF(SUM(s.net_sales_after_returns_egp), 0) AS share_of_category
        FROM gold.fact_sales_line s JOIN gold.dim_product p ON p.sku_id = s.sku_id
        WHERE p.category = %(cat)s AND {where}
    """, {**params, "cat": info["category"]})
    kpis["share_of_category"] = share["share_of_category"] if share else None

    monthly = fetch_all(f"""
        SELECT s.month_start, SUM(s.quantity - s.returned_units) AS units,
               SUM(s.net_sales_after_returns_egp) AS net_sales
        FROM gold.fact_sales_line s JOIN gold.dim_date d ON d.date_key = s.month_start
        WHERE s.product_id = %(pid)s AND d.is_complete_month AND {where}
        GROUP BY 1 ORDER BY 1
    """, params)
    sizes = fetch_all(f"""
        SELECT p.size AS label, SUM(s.quantity - s.returned_units) AS units,
               SUM(s.returned_units)::numeric / NULLIF(SUM(s.quantity), 0) AS return_rate
        FROM gold.fact_sales_line s JOIN gold.dim_product p ON p.sku_id = s.sku_id
        WHERE s.product_id = %(pid)s AND {where}
        GROUP BY p.size ORDER BY MIN({SIZE_RANK_SQL.replace('size', 'p.size')})
    """, params)
    colors = fetch_all(f"""
        SELECT p.color_ar AS label, SUM(s.quantity - s.returned_units) AS units
        FROM gold.fact_sales_line s JOIN gold.dim_product p ON p.sku_id = s.sku_id
        WHERE s.product_id = %(pid)s AND {where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8
    """, params)
    branches = fetch_all(f"""
        SELECT b.branch_display_name AS label, SUM(s.quantity - s.returned_units) AS units,
               SUM(s.net_sales_after_returns_egp) AS net_sales
        FROM gold.fact_sales_line s JOIN gold.dim_branch b ON b.branch_id = s.branch_id
        WHERE s.product_id = %(pid)s AND {where}
        GROUP BY 1 ORDER BY net_sales DESC NULLS LAST LIMIT 8
    """, params)

    forecast = []
    if fetch_one("SELECT to_regclass('gold.ml_forecast_monthly') IS NOT NULL AS ok")["ok"]:
        forecast = fetch_all("""
            SELECT month_start, actual_units, forecast_units, lower_80, upper_80, is_forecast
            FROM gold.ml_forecast_monthly
            WHERE category = %(cat)s
              AND month_start >= (SELECT MAX(month_start) FROM gold.ml_forecast_monthly) - interval '30 months'
            ORDER BY month_start
        """, {"cat": info["category"]})

    return {"info": info, "kpis": kpis, "monthly": monthly, "sizes": sizes, "colors": colors,
            "branches": branches, "category_forecast": forecast}


@router.get("/simulator/baseline")
def simulator_baseline(months: int = 12, branch: list[str] = Query(default=[]),
                       channel: list[str] = Query(default=[])):
    """Last N complete months per category: units, sales, cost and current discount.
    The simulator itself runs in the browser (instant slider updates)."""
    months = max(3, min(months, 36))
    where, params = build_where({"branch": "s.branch_id", "channel": "s.sales_channel"},
                                _filters(None, None, branch, channel))
    rows = fetch_all(f"""
        WITH last AS (SELECT MAX(month_start) AS m FROM gold.dim_date WHERE is_complete_month AND has_data)
        SELECT COALESCE(p.category, 'All categories') AS category,
               SUM(s.quantity - s.returned_units) AS units,
               SUM(s.net_sales_after_returns_egp) AS net_sales,
               SUM(s.net_sales_after_returns_egp - s.margin_after_returns_egp) AS cogs,
               SUM(s.margin_after_returns_egp) AS margin,
               SUM(s.discount_egp) / NULLIF(SUM(s.net_sales_egp + s.discount_egp), 0) AS current_discount,
               MIN(s.month_start) AS from_month, MAX(s.month_start) AS to_month
        FROM gold.fact_sales_line s
        JOIN gold.dim_product p ON p.sku_id = s.sku_id
        CROSS JOIN last
        WHERE s.month_start > last.m - make_interval(months => %(months)s) AND s.month_start <= last.m
          AND {where}
        GROUP BY ROLLUP (p.category)
        ORDER BY (p.category IS NULL) DESC, net_sales DESC
    """, {**params, "months": months})
    return {"months": months, "categories": rows}
