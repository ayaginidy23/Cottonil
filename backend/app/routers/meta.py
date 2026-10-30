# =============================================================================
# routers/meta.py  -  Health check + the values the filter bar needs
# =============================================================================

from fastapi import APIRouter

from ..db import fetch_all, fetch_one

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health():
    """Quick check that the API and the database both answer."""
    row = fetch_one("SELECT COUNT(*) AS orders FROM gold.fact_orders")
    return {"status": "ok", "orders_in_gold": row["orders"]}


@router.get("/meta/filters")
def filter_options():
    """Everything the frontend filter bar needs: branches, channels, date limits,
    and a sensible default period (the last 12 complete months)."""
    branches = fetch_all("""
        SELECT branch_id, branch_display_name, governorate_ar, retail_location_type
        FROM gold.dim_branch ORDER BY branch_id
    """)
    channels = [r["sales_channel"] for r in fetch_all(
        "SELECT DISTINCT sales_channel FROM gold.mart_sales_daily ORDER BY 1")]
    dates = fetch_one("""
        SELECT MIN(date_key) FILTER (WHERE has_data)          AS data_from,
               MAX(date_key) FILTER (WHERE has_data)          AS data_to,
               MIN(date_key) FILTER (WHERE is_complete_month) AS complete_from,
               MAX(date_key) FILTER (WHERE is_complete_month) AS complete_to
        FROM gold.dim_date
    """)
    default_to = dates["complete_to"]
    default_from = fetch_one(
        "SELECT (date_trunc('month', %(d)s::date) - INTERVAL '11 months')::date AS d",
        {"d": default_to},
    )["d"] if default_to else None

    return {
        "branches": branches,
        "channels": channels,
        "dates": dates,
        "default_period": {"date_from": default_from, "date_to": default_to},
    }
