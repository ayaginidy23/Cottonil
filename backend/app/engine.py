# =============================================================================
# engine.py  -  Runs one app definition with the current filters
# -----------------------------------------------------------------------------
# For each KPI:   run its SQL (must return one column named "value"),
#                 run it again for the previous period, compute the change:
#                 relative % for amounts, percentage points (pp) for KPIs that
#                 are already a % (14% -> 16% is "+2.0 pp", not "+14%").
#                 No comparison when the previous period starts before the data
#                 does (e.g. "All time"): comparing with an empty period gives
#                 meaningless numbers like +175,000%.
# For each chart: run its SQL and return the rows as-is (the frontend draws them).
# One broken query returns an "error" field instead of breaking the whole page.
# Results are cached in memory: the data only changes when the pipeline re-runs.
# =============================================================================

from collections import OrderedDict

from .db import fetch_all
from .filters import Filters, build_where, previous_period

_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_CACHE_SIZE = 300
_DATA_START = None


def _data_start():
    """First date that has data (read once, then remembered)."""
    global _DATA_START
    if _DATA_START is None:
        row = fetch_all("SELECT MIN(date_key) AS d FROM gold.dim_date WHERE has_data")
        _DATA_START = row[0]["d"] if row else None
    return _DATA_START


def _render(item: dict, app: dict, f: Filters) -> tuple[str, dict]:
    """Put the filter condition into the item's SQL ({where} placeholder)."""
    columns = item.get("columns", app["columns"])     # item-level override, else app default
    where, params = build_where(columns, f)
    # psycopg treats "%" as the start of a placeholder, so a literal % in the YAML
    # (e.g. 'Top 10%') is doubled first; the filter placeholders are added after.
    query = item["sql"].replace("%", "%%").replace("{where}", where)
    return query, params


def _run_kpi(kpi: dict, app: dict, f: Filters) -> dict:
    out = {k: kpi.get(k) for k in ("id", "label", "format", "hint")}
    out["good"] = kpi.get("good", "up")               # is "up" good (sales) or bad (returns)?
    try:
        query, params = _render(kpi, app, f)
        row = fetch_all(query, params)
        out["value"] = row[0]["value"] if row else None

        prev = previous_period(f) if kpi.get("compare", True) else None
        start = _data_start()
        if prev and start and prev.date_from < start:  # previous period is (partly) before the data
            prev = None
        out["previous"] = None
        out["change_pct"] = None
        out["change_unit"] = "pp" if kpi.get("format") == "pct" else "pct"
        if prev:
            q2, p2 = _render(kpi, app, prev)
            r2 = fetch_all(q2, p2)
            out["previous"] = r2[0]["value"] if r2 else None
            if out["value"] is not None and out["previous"] is not None:
                cur, old = float(out["value"]), float(out["previous"])
                if out["change_unit"] == "pp":
                    out["change_pct"] = cur - old                  # difference in percentage points
                elif old:
                    out["change_pct"] = (cur - old) / abs(old)     # relative change
    except Exception as e:
        out["error"] = str(e)
    return out


def _run_chart(chart: dict, app: dict, f: Filters) -> dict:
    out = {k: v for k, v in chart.items() if k not in ("sql", "columns")}   # send the spec, not the SQL
    try:
        query, params = _render(chart, app, f)
        out["data"] = fetch_all(query, params)
    except Exception as e:
        out["data"] = []
        out["error"] = str(e)
    return out


def run_app(app: dict, f: Filters) -> dict:
    key = (app["id"], f.cache_key())
    if key in _CACHE:
        _CACHE.move_to_end(key)                       # mark as recently used
        return _CACHE[key]

    result = {
        "id": app["id"],
        "title": app["title"],
        "group": app["group"],
        "description": app["description"],
        "insights": app.get("insights", []),
        "kpis": [_run_kpi(k, app, f) for k in app["kpis"]],
        "charts": [_run_chart(c, app, f) for c in app["charts"]],
    }

    has_error = any("error" in x for x in result["kpis"] + result["charts"])
    if not has_error:                                 # never cache a broken result
        _CACHE[key] = result
        if len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)                # drop the least recently used
    return result


def clear_cache() -> None:
    global _DATA_START
    _CACHE.clear()
    _DATA_START = None