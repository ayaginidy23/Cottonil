# =============================================================================
# chat/explain.py  -  "Explain this page": AI summary of a dashboard page
# -----------------------------------------------------------------------------
# 1. Run the page with the current filters (same result the user is looking at,
#    usually straight from the engine cache).
# 2. Shrink it to a short text: every KPI with its change, and for every chart
#    only the useful numbers (first / last / highest / lowest point of a trend,
#    top rows of a ranking). The model never sees the raw tables.
# 3. Ask the model for a short summary for a non-technical manager, in English
#    AND Egyptian Arabic, as JSON (both are shown on screen and printed in the PDF).
# The model gets numbers only from step 2, so it cannot invent other numbers.
# =============================================================================

import json
from datetime import date
from decimal import Decimal

from ..engine import run_app
from ..filters import Filters
from ..llm import chat_completion, parse_json

_CACHE: dict[tuple, dict] = {}

PROMPT = """You explain one page of the Cottonil management dashboard (Egyptian apparel retailer)
to a busy, non-technical manager. Use ONLY the numbers in the page data below.

Return ONLY a JSON object, no other text:
{
  "en": {"headline": "one sentence with the main message",
         "points": ["3 to 5 short points: what the numbers say, with the numbers"],
         "watch": ["1 or 2 things to watch or do next"]},
  "ar": {"headline": "...", "points": ["..."], "watch": ["..."]}
}
"ar" is the same content in clear Egyptian Arabic (عامية مصرية مفهومة), keeping numbers,
EGP and % as they are. Format money like EGP 12.4M. Percentage-point changes are "pp".
Rules: money is EGP before VAT; prices rose a lot since 2018 (inflation), so EGP growth over
years is not real growth unless the page shows real (2026-price) values or units; return
reasons, age bands and carriers are almost uniform in this data - do not call small
differences between them insights. Do not repeat the page title. No markdown.
"""


def _num(v):
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return round(v, 4) if abs(v) < 10 else round(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def _chart_digest(c: dict) -> dict:
    data = c.get("data") or []
    out = {"title": c.get("title"), "type": c.get("type"), "format": c.get("format"), "rows": len(data)}
    if c.get("error") or not data:
        out["note"] = "no data"
        return out
    x = c.get("x")
    keys = [s["key"] for s in c.get("series", [])]
    if c.get("type") in ("line", "area") and x and keys:
        trend = {}
        for s in c.get("series", []):
            pts = [(r.get(x), r.get(s["key"])) for r in data if r.get(s["key"]) is not None]
            if not pts:
                continue
            hi = max(pts, key=lambda p: float(p[1]))
            lo = min(pts, key=lambda p: float(p[1]))
            trend[s.get("label", s["key"])] = {
                "first": [_num(pts[0][0]), _num(pts[0][1])], "last": [_num(pts[-1][0]), _num(pts[-1][1])],
                "highest": [_num(hi[0]), _num(hi[1])], "lowest": [_num(lo[0]), _num(lo[1])]}
        out["trend"] = trend
    else:
        cols = [t["key"] for t in c.get("table_columns", [])] or ([x] + keys if x else list(data[0])[:6])
        out["top_rows"] = [{k: _num(r.get(k)) for k in cols if k in r} for r in data[:8]]
    return out


def page_digest(result: dict, f: Filters) -> dict:
    return {
        "page": result["title"],
        "description": result.get("description"),
        "filters": {"from": _num(f.date_from) or "start of data", "to": _num(f.date_to) or "end of data",
                    "branches": list(f.branches) or "all", "channels": list(f.channels) or "all"},
        "kpis": [{"label": k["label"], "value": _num(k.get("value")), "format": k.get("format"),
                  "change": _num(k.get("change_pct")),
                  "change_unit": "pp" if k.get("change_unit") == "pp" else "relative (0.12 = +12%)"}
                 for k in result["kpis"] if not k.get("error")],
        "charts": [_chart_digest(c) for c in result["charts"]],
    }


def explain_app(app: dict, f: Filters) -> dict:
    key = (app["id"], f.cache_key())
    if key in _CACHE:
        return _CACHE[key]
    result = run_app(app, f)
    digest = page_digest(result, f)
    text = json.dumps(digest, ensure_ascii=False, default=str)[:12000]
    resp = chat_completion(
        messages=[{"role": "system", "content": PROMPT},
                  {"role": "user", "content": f"Page data:\n{text}"}],
        temperature=0.2,
    )
    parsed = parse_json(resp.choices[0].message.content or "")
    out = {}
    for lang in ("en", "ar"):
        part = parsed.get(lang) or {}
        out[lang] = {"headline": str(part.get("headline", "")),
                     "points": [str(p) for p in part.get("points", [])][:6],
                     "watch": [str(p) for p in part.get("watch", [])][:3]}
    out["app_id"] = app["id"]
    out["title"] = result["title"]
    _CACHE[key] = out
    if len(_CACHE) > 200:
        _CACHE.pop(next(iter(_CACHE)))
    return out
