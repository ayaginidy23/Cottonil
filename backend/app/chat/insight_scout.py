# =============================================================================
# chat/insight_scout.py  -  Insight Scout: finds what changed, without being asked
# -----------------------------------------------------------------------------
# A manager should not have to know which question to ask. The scout runs a fixed
# set of "probes" (safe, pre-written SQL on gold) that compare the latest complete
# months with the past, then turns the findings into short cards in English and
# Egyptian Arabic, each with a suggested action and a follow-up question for the
# Business Analyst.
#
#   probe               compares
#   category_momentum   units per category, last 3 months vs the same 3 months a year ago
#   branch_momentum     real (2026-price) sales per branch, same comparison
#   channel_mix         share of sales per channel, same comparison
#   margin_trend        gross margin % per category, last 6 months vs the 6 before
#   high_returns        products whose return rate is far above the company average
#   discount_depth      average discount, last 3 months vs a year ago
#   customers_at_risk   RFM "At risk" customers and their past spend
#   stock_risk          categories with the highest stock-out risk (latest month)
#   forecast_next       forecast for next month vs the same month last year
#
# Units and real (inflation-adjusted) values are used for growth, never nominal EGP.
# The numbers come from SQL; the model only writes the words. If the AI quota is
# used up, simple bilingual template cards are returned instead.
# =============================================================================

import json
import threading
import time

from ..db import fetch_all, fetch_one
from ..llm import chat_completion, parse_json

CACHE_SECONDS = 6 * 3600
_cache: dict = {"at": 0, "data": None}
_lock = threading.Lock()                 # two visitors at once -> calculated only once

LAST = "(SELECT MAX(month_start) FROM gold.dim_date WHERE is_complete_month AND has_data)"
RECENT3 = f"s.month_start > {LAST} - interval '3 months' AND s.month_start <= {LAST}"
YEARAGO3 = (f"s.month_start > {LAST} - interval '15 months' "
            f"AND s.month_start <= {LAST} - interval '12 months'")
# only read the months the probes compare (uses the month_start index, much faster)
WINDOW15 = f"s.month_start > {LAST} - interval '15 months' AND s.month_start <= {LAST}"
WINDOW12 = f"s.month_start > {LAST} - interval '12 months' AND s.month_start <= {LAST}"

PROBES = {
    "category_momentum": f"""
        SELECT p.category,
               SUM(s.quantity - s.returned_units) FILTER (WHERE {RECENT3})  AS recent_units,
               SUM(s.quantity - s.returned_units) FILTER (WHERE {YEARAGO3}) AS year_ago_units
        FROM gold.fact_sales_line s JOIN gold.dim_product p ON p.sku_id = s.sku_id
        WHERE {WINDOW15}
        GROUP BY 1
        HAVING SUM(s.quantity - s.returned_units) FILTER (WHERE {YEARAGO3}) > 0""",
    "branch_momentum": f"""
        SELECT b.branch_display_name AS branch,
               round(SUM(s.real_net_sales_egp) FILTER (WHERE {RECENT3}))  AS recent_real_sales,
               round(SUM(s.real_net_sales_egp) FILTER (WHERE {YEARAGO3})) AS year_ago_real_sales
        FROM gold.mart_sales_daily s JOIN gold.dim_branch b ON b.branch_id = s.branch_id
        WHERE {WINDOW15}
        GROUP BY 1
        HAVING SUM(s.real_net_sales_egp) FILTER (WHERE {YEARAGO3}) > 0
           AND SUM(s.real_net_sales_egp) FILTER (WHERE {RECENT3}) > 0""",
    "channel_mix": f"""
        SELECT s.sales_channel AS channel,
               SUM(s.net_sales_after_returns_egp) FILTER (WHERE {RECENT3})
                 / NULLIF(SUM(SUM(s.net_sales_after_returns_egp) FILTER (WHERE {RECENT3})) OVER (), 0) AS recent_share,
               SUM(s.net_sales_after_returns_egp) FILTER (WHERE {YEARAGO3})
                 / NULLIF(SUM(SUM(s.net_sales_after_returns_egp) FILTER (WHERE {YEARAGO3})) OVER (), 0) AS year_ago_share
        FROM gold.mart_sales_daily s WHERE {WINDOW15} GROUP BY 1""",
    "margin_trend": f"""
        SELECT p.category,
               SUM(s.margin_after_returns_egp) FILTER (WHERE s.month_start > {LAST} - interval '6 months'
                                                         AND s.month_start <= {LAST})
                 / NULLIF(SUM(s.net_sales_after_returns_egp) FILTER (WHERE s.month_start > {LAST} - interval '6 months'
                                                                    AND s.month_start <= {LAST}), 0) AS recent_margin,
               SUM(s.margin_after_returns_egp) FILTER (WHERE s.month_start > {LAST} - interval '12 months'
                                                         AND s.month_start <= {LAST} - interval '6 months')
                 / NULLIF(SUM(s.net_sales_after_returns_egp) FILTER (WHERE s.month_start > {LAST} - interval '12 months'
                                                                    AND s.month_start <= {LAST} - interval '6 months'), 0) AS previous_margin
        FROM gold.fact_sales_line s JOIN gold.dim_product p ON p.sku_id = s.sku_id
        WHERE {WINDOW12}
        GROUP BY 1""",
    "high_returns": f"""
        WITH recent AS (
            SELECT s.product_id, SUM(s.quantity) AS units, SUM(s.returned_units) AS returned
            FROM gold.fact_sales_line s
            WHERE s.month_start > {LAST} - interval '6 months' AND s.month_start <= {LAST}
            GROUP BY 1
        ), avg AS (SELECT SUM(returned)::numeric / NULLIF(SUM(units), 0) AS company_rate FROM recent)
        SELECT MIN(p.product_name_ar) AS product, r.product_id, r.units,
               round(r.returned::numeric / NULLIF(r.units, 0), 4) AS return_rate,
               round(avg.company_rate, 4) AS company_rate
        FROM recent r CROSS JOIN avg JOIN gold.dim_product p ON p.product_id = r.product_id
        WHERE r.units >= 50
        GROUP BY r.product_id, r.units, r.returned, avg.company_rate
        ORDER BY return_rate DESC LIMIT 3""",
    "discount_depth": f"""
        SELECT SUM(s.discount_egp) FILTER (WHERE {RECENT3})
                 / NULLIF(SUM(s.net_sales_egp + s.discount_egp) FILTER (WHERE {RECENT3}), 0) AS recent_discount,
               SUM(s.discount_egp) FILTER (WHERE {YEARAGO3})
                 / NULLIF(SUM(s.net_sales_egp + s.discount_egp) FILTER (WHERE {YEARAGO3}), 0) AS year_ago_discount
        FROM gold.mart_sales_daily s WHERE {WINDOW15}""",
    "customers_at_risk": """
        SELECT COUNT(*) FILTER (WHERE rfm_segment = 'At risk') AS at_risk_customers,
               COUNT(*) AS customers,
               round(SUM(real_monetary_egp) FILTER (WHERE rfm_segment = 'At risk')) AS at_risk_real_spend,
               SUM(real_monetary_egp) FILTER (WHERE rfm_segment = 'At risk')
                 / NULLIF(SUM(real_monetary_egp), 0) AS at_risk_spend_share
        FROM gold.mart_customer_rfm WHERE customer_key <> 'GUEST'""",
    "stock_risk": """
        SELECT category, round(AVG(stockout_risk_score)::numeric, 3) AS avg_risk,
               COUNT(DISTINCT location_id) AS locations
        FROM gold.fact_inventory_monthly
        WHERE month_start = (SELECT MAX(month_start) FROM gold.fact_inventory_monthly)
        GROUP BY 1 ORDER BY avg_risk DESC LIMIT 3""",
    "forecast_next": """
        WITH nxt AS (SELECT MIN(month_start) AS m FROM gold.ml_forecast_monthly WHERE is_forecast)
        SELECT f.category, f.month_start, round(f.forecast_units) AS forecast_units,
               round(h.actual_units) AS same_month_last_year
        FROM gold.ml_forecast_monthly f CROSS JOIN nxt
        LEFT JOIN gold.ml_forecast_monthly h
               ON h.category = f.category AND h.month_start = (nxt.m - interval '12 months')::date
        WHERE f.is_forecast AND f.month_start = nxt.m""",
}


def _f(v):
    return float(v) if v is not None else None


def _pct(v):
    return f"{v * 100:+.1f}%" if v is not None else "-"


def _facts() -> dict:
    """Run every probe; keep only a few numbers per probe (the model sees these only)."""
    facts = {}
    last = fetch_one(f"SELECT {LAST} AS m")["m"]
    facts["_period"] = {"latest_complete_month": str(last)}
    for name, sql in PROBES.items():
        try:
            rows = fetch_all(sql)
        except Exception:
            continue                                   # e.g. no forecast table yet
        if not rows:
            continue
        if name in ("category_momentum", "branch_momentum"):
            a, b = ("recent_units", "year_ago_units") if name == "category_momentum" \
                else ("recent_real_sales", "year_ago_real_sales")
            label = "category" if name == "category_momentum" else "branch"
            scored = [{label: r[label], "recent": _f(r[a]), "year_ago": _f(r[b]),
                       "change": _f(r[a]) / _f(r[b]) - 1} for r in rows if r[a] and r[b]]
            if len(scored) >= 2:
                scored.sort(key=lambda r: r["change"])
                facts[name] = {"biggest_rise": scored[-1], "biggest_drop": scored[0],
                               "compared": "last 3 complete months vs the same 3 months a year earlier"
                                           + (" (net units)" if label == "category" else
                                              " (real sales at 2026 prices)")}
        elif name == "channel_mix":
            ch = [{"channel": r["channel"], "recent_share": _f(r["recent_share"]),
                   "year_ago_share": _f(r["year_ago_share"])} for r in rows
                  if r["recent_share"] is not None and r["year_ago_share"] is not None]
            for c in ch:
                c["change_pp"] = (c["recent_share"] - c["year_ago_share"]) * 100
            if ch:
                facts[name] = {"channels": ch, "biggest_shift": max(ch, key=lambda c: abs(c["change_pp"]))}
        elif name == "margin_trend":
            m = [{"category": r["category"], "recent": _f(r["recent_margin"]),
                  "previous": _f(r["previous_margin"])} for r in rows
                 if r["recent_margin"] is not None and r["previous_margin"] is not None]
            for c in m:
                c["change_pp"] = (c["recent"] - c["previous"]) * 100
            if m:
                facts[name] = {"biggest_decline": min(m, key=lambda c: c["change_pp"]),
                               "biggest_improvement": max(m, key=lambda c: c["change_pp"]),
                               "compared": "gross margin %, last 6 complete months vs the 6 before"}
        elif name == "high_returns":
            facts[name] = {"products": [{k: (_f(v) if k in ("units", "return_rate", "company_rate") else v)
                                         for k, v in r.items()} for r in rows],
                           "period": "last 6 complete months, products with 50+ units"}
        elif name == "forecast_next":
            tot = next((r for r in rows if r["category"] == "TOTAL"), None)
            cats = [r for r in rows if r["category"] != "TOTAL" and r["same_month_last_year"]]
            facts[name] = {
                "month": str(rows[0]["month_start"]),
                "total": {"forecast": _f(tot["forecast_units"]), "same_month_last_year": _f(tot["same_month_last_year"])}
                if tot else None,
                "categories": [{"category": r["category"], "forecast": _f(r["forecast_units"]),
                                "same_month_last_year": _f(r["same_month_last_year"])} for r in cats][:8]}
        else:
            facts[name] = [{k: (_f(v) if isinstance(v, (int, float)) or hasattr(v, "is_finite") else v)
                            for k, v in r.items()} for r in rows]
    return facts


PROMPT = """You are the Insight Scout of Cottonil (Egyptian apparel retailer). Below are findings that
pre-written SQL probes found in the company data. Write 4 to 7 insight cards for top management,
most important first. Use ONLY these numbers. Skip findings that are small or not meaningful
(e.g. changes under 3% or under 1 pp). Shares and margins are fractions (0.25 = 25%).

Return ONLY JSON:
{"cards": [{
  "probe": "the probe name it comes from",
  "severity": "warning" | "good" | "info",
  "title_en": "max 8 words", "title_ar": "same in Egyptian Arabic",
  "insight_en": "1-2 sentences with the key numbers", "insight_ar": "same in Egyptian Arabic",
  "action_en": "one concrete next step", "action_ar": "same in Egyptian Arabic",
  "ask_en": "a follow-up question the manager can send to the Business Analyst",
  "ask_ar": "same question in Egyptian Arabic"
}]}
Money is EGP. No markdown.
"""


def _template_cards(facts: dict) -> list[dict]:
    """Used only when the AI is not available: plain bilingual cards from the numbers."""
    cards = []
    cm = facts.get("category_momentum")
    if cm:
        up, dn = cm["biggest_rise"], cm["biggest_drop"]
        cards.append({"probe": "category_momentum", "severity": "warning" if dn["change"] < -0.03 else "info",
                      "title_en": "Category demand: winners and losers",
                      "title_ar": "طلب الأقسام: مين طالع ومين نازل",
                      "insight_en": f"{up['category']} {_pct(up['change'])} units vs a year ago; "
                                    f"{dn['category']} {_pct(dn['change'])}.",
                      "insight_ar": f"{up['category']} اتغير {_pct(up['change'])} في عدد القطع عن نفس الفترة السنة اللي فاتت، "
                                    f"و{dn['category']} اتغير {_pct(dn['change'])}.",
                      "action_en": f"Check stock and promotions for {dn['category']}.",
                      "action_ar": f"راجع المخزون والعروض بتاعة {dn['category']}.",
                      "ask_en": f"Why did {dn['category']} units change in the last 3 months?",
                      "ask_ar": f"ليه عدد القطع في {dn['category']} اتغير آخر 3 شهور؟"})
    bm = facts.get("branch_momentum")
    if bm:
        dn = bm["biggest_drop"]
        cards.append({"probe": "branch_momentum", "severity": "warning" if dn["change"] < -0.05 else "info",
                      "title_en": "Branch with the biggest drop", "title_ar": "الفرع اللي نزل أكتر",
                      "insight_en": f"{dn['branch']}: real sales {_pct(dn['change'])} vs a year ago.",
                      "insight_ar": f"{dn['branch']}: المبيعات الحقيقية {_pct(dn['change'])} عن السنة اللي فاتت.",
                      "action_en": "Review this branch's traffic, staff and stock.",
                      "action_ar": "راجع زحمة الفرع والموظفين والمخزون.",
                      "ask_en": f"Show monthly real sales of {dn['branch']} for the last 2 years",
                      "ask_ar": f"وريني المبيعات الحقيقية الشهرية لفرع {dn['branch']} آخر سنتين"})
    mt = facts.get("margin_trend")
    if mt:
        d = mt["biggest_decline"]
        cards.append({"probe": "margin_trend", "severity": "warning" if d["change_pp"] < -1 else "info",
                      "title_en": "Margin pressure", "title_ar": "ضغط على هامش الربح",
                      "insight_en": f"{d['category']} margin {d['change_pp']:+.1f} pp in the last 6 months.",
                      "insight_ar": f"هامش {d['category']} اتغير {d['change_pp']:+.1f} نقطة آخر 6 شهور.",
                      "action_en": "Check discounts and cost prices for this category.",
                      "action_ar": "راجع الخصومات وتكلفة القسم ده.",
                      "ask_en": f"Why did the gross margin of {d['category']} change?",
                      "ask_ar": f"ليه هامش {d['category']} اتغير؟"})
    hr = facts.get("high_returns")
    if hr and hr["products"]:
        p = hr["products"][0]
        cards.append({"probe": "high_returns", "severity": "warning",
                      "title_en": "Product with the highest returns", "title_ar": "أكتر منتج بيرجع",
                      "insight_en": f"{p['product']}: {p['return_rate'] * 100:.1f}% returned vs "
                                    f"{p['company_rate'] * 100:.1f}% company average.",
                      "insight_ar": f"{p['product']}: نسبة المرتجع {p['return_rate'] * 100:.1f}% "
                                    f"مقابل {p['company_rate'] * 100:.1f}% متوسط الشركة.",
                      "action_en": "Check its size fit and quality.", "action_ar": "راجع المقاسات والجودة بتاعته.",
                      "ask_en": f"Return rate by size for {p['product']}",
                      "ask_ar": f"نسبة المرتجع حسب المقاس لـ {p['product']}"})
    fn = facts.get("forecast_next")
    if fn and fn.get("total") and fn["total"]["same_month_last_year"]:
        t = fn["total"]
        ch = t["forecast"] / t["same_month_last_year"] - 1
        cards.append({"probe": "forecast_next", "severity": "info",
                      "title_en": "Next month's demand", "title_ar": "طلب الشهر الجاي",
                      "insight_en": f"Forecast {t['forecast']:,.0f} units ({_pct(ch)} vs the same month last year).",
                      "insight_ar": f"التوقع {t['forecast']:,.0f} قطعة ({_pct(ch)} عن نفس الشهر السنة اللي فاتت).",
                      "action_en": "Plan stock with the forecast range.", "action_ar": "خطط المخزون على مدى التوقع.",
                      "ask_en": "Forecast for next month by category", "ask_ar": "توقع الشهر الجاي لكل قسم"})
    return cards


def scout(refresh: bool = False) -> dict:
    if not refresh and _cache["data"] and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    with _lock:
        started = time.time()
        if not refresh and _cache["data"] and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]                     # calculated while we were waiting
        if refresh and _cache["data"] and _cache["at"] >= started - 5:
            return _cache["data"]
        return _scout()


def _scout() -> dict:
    facts = _facts()
    source, cards = "ai", []
    try:
        resp = chat_completion(
            messages=[{"role": "system", "content": PROMPT},
                      {"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=str)}],
            temperature=0.3,
        )
        cards = [c for c in parse_json(resp.choices[0].message.content or "").get("cards", [])
                 if isinstance(c, dict) and c.get("title_en")][:8]
    except Exception as e:
        print(f"Insight Scout: AI not available ({str(e)[:120]}), using template cards")
    if not cards:
        source, cards = "template", _template_cards(facts)
    order = {"warning": 0, "good": 1, "info": 2}
    cards.sort(key=lambda c: order.get(c.get("severity"), 3))
    data = {"generated_at": time.strftime("%Y-%m-%d %H:%M"), "source": source,
            "latest_complete_month": facts["_period"]["latest_complete_month"],
            "cards": cards, "facts": facts}
    _cache.update(at=time.time(), data=data)
    return data