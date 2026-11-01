# =============================================================================
# chat/report_agent.py  -  Report Agent: one request -> a full bilingual report
# -----------------------------------------------------------------------------
# The manager types a topic ("Alexandria branches performance in 2025") and gets
# a short management report with sections, numbers, charts and recommendations,
# in English AND Egyptian Arabic, ready to download as a PDF.
#
# It is an agent: it plans the angles itself and runs several queries.
#   1. same schema RAG + business rules + safe run_sql as the Business Analyst
#      (read-only, gold only, timeout, row limit - see analyst.py)
#   2. the model runs 3-6 queries, each successful result gets a number
#   3. it writes the report as JSON; every section points to the number of the
#      query whose result it shows, so the CHART DATA COMES FROM THE DATABASE,
#      not from the model's text
#   4. the report is saved in app.analyst_reports, so the print page can load it
# =============================================================================

import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from ..db import fetch_one, pool
from ..llm import chat_completion, parse_json
from .analyst import (BUSINESS_RULES, RUN_SQL_SPEC, _all_table_docs, _product_images,
                      _relevant_tables, run_sql)
from .memory import _valid_uuid

MAX_STEPS = 10
MAX_QUERIES = 6
ROWS_IN_REPORT = 40

DDL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.analyst_reports (
    report_id   UUID PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    owner_key   TEXT,
    topic       TEXT NOT NULL,
    report      JSONB NOT NULL
);
"""

PROMPT = """You are the Report Agent of Cottonil (Egyptian apparel retailer). You write a short
management report about the topic the manager gives, from the company data (PostgreSQL, gold schema).

Step 1 - research: call run_sql 3 to 6 times, each time ONE SELECT/WITH query that looks at a
different angle of the topic (trend over time, comparison between groups, top/bottom items,
profitability...). Always schema-qualify tables (gold.x), aggregate in SQL, LIMIT long results,
round money to 0 decimals and ratios to 3. For a chart, return a label/date column first and
1-3 numeric columns. Each successful result is numbered (query_number). If a query fails, fix it.

Step 2 - write: when you have enough, answer with ONLY this JSON (no markdown, no other text):
{
  "title_en": "...", "title_ar": "...",
  "summary_en": "3-4 sentence executive summary with the key numbers",
  "summary_ar": "same in Egyptian Arabic",
  "sections": [
    {"query_number": 1, "chart": "line" | "bar" | "hbar" | "table",
     "heading_en": "...", "heading_ar": "...",
     "text_en": "2-3 sentences: what this result shows, with numbers",
     "text_ar": "same in Egyptian Arabic"}
  ],
  "recommendations_en": ["2-4 concrete actions"],
  "recommendations_ar": ["same in Egyptian Arabic"],
  "notes_en": "assumptions / data limits (one sentence)", "notes_ar": "same in Egyptian Arabic"
}
Use "line" for monthly trends, "hbar" for rankings, "bar" for a few groups, "table" otherwise.
Use only numbers from the query results. Egyptian Arabic = clear عامية مصرية, numbers unchanged.
"""

def _json_default(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


TEXT_FIELDS = ("title_en", "title_ar", "summary_en", "summary_ar", "notes_en", "notes_ar")


def _ensure():
    with pool.connection() as conn:
        conn.execute(DDL)


def _build(parsed: dict, results: dict[int, dict], topic: str) -> dict:
    report = {k: str(parsed.get(k) or "") for k in TEXT_FIELDS}
    report["title_en"] = report["title_en"] or topic
    report["title_ar"] = report["title_ar"] or topic
    report["recommendations_en"] = [str(x) for x in parsed.get("recommendations_en", [])][:6]
    report["recommendations_ar"] = [str(x) for x in parsed.get("recommendations_ar", [])][:6]
    sections = []
    for s in parsed.get("sections", [])[:8]:
        if not isinstance(s, dict):
            continue
        n = s.get("query_number")
        res = results.get(int(n)) if str(n).isdigit() else None
        section = {k: str(s.get(k) or "") for k in ("heading_en", "heading_ar", "text_en", "text_ar")}
        section["chart"] = s.get("chart") if s.get("chart") in ("line", "bar", "hbar", "table") else "table"
        if res:
            section.update(sql=res["sql"], columns=res["columns"], rows=res["rows"][:ROWS_IN_REPORT],
                           images=_product_images(res["columns"], res["rows"], limit=6))
        sections.append(section)
    report["sections"] = sections
    return report


def make_report(topic: str, owner: str | None = None) -> dict:
    docs = _all_table_docs()
    tables = _relevant_tables(topic, docs, k=10)
    schema = "\n".join(docs[t] for t in tables)
    convo = [
        {"role": "system", "content": f"{PROMPT}\n{BUSINESS_RULES}\nRelevant tables:\n{schema}"},
        {"role": "user", "content": f"Report topic: {topic}"},
    ]
    results: dict[int, dict] = {}
    attempts = []
    parsed = None

    for _ in range(MAX_STEPS):
        force = len(results) >= MAX_QUERIES
        resp = chat_completion(messages=convo, tools=RUN_SQL_SPEC, temperature=0.2,
                               **({"tool_choice": "none"} if force else {}))
        msg = resp.choices[0].message
        if not msg.tool_calls:
            try:
                parsed = parse_json(msg.content or "")
                break
            except ValueError:
                convo.append({"role": "assistant", "content": msg.content or ""})
                convo.append({"role": "user", "content": "Answer with the report JSON only."})
                continue
        convo.append({"role": "assistant", "content": msg.content or "",
                      "tool_calls": [tc.model_dump(exclude_none=True) for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                query = json.loads(tc.function.arguments or "{}").get("query", "")
            except json.JSONDecodeError:
                query = ""
            result = run_sql(query, owner)
            attempts.append({"sql": query, "ok": "error" not in result, "error": result.get("error")})
            shown = dict(result)
            if "error" not in result:
                n = len(results) + 1
                results[n] = {"sql": query, "columns": result["columns"], "rows": result["rows"]}
                shown = {"query_number": n, **shown, "rows": result["rows"][:60]}
            convo.append({"role": "tool", "tool_call_id": tc.id,
                          "content": json.dumps(shown, ensure_ascii=False, default=str)})

    if parsed is None:                                  # out of steps: ask for the JSON now
        convo.append({"role": "user", "content": "Stop querying. Write the report JSON now from the results above."})
        resp = chat_completion(messages=convo, tools=RUN_SQL_SPEC, tool_choice="none", temperature=0.2)
        parsed = parse_json(resp.choices[0].message.content or "")

    report = _build(parsed, results, topic)
    report.update(topic=topic, attempts=attempts, tables_used=tables)
    report_id = str(uuid.uuid4())
    report["report_id"] = report_id
    try:
        _ensure()
        with pool.connection() as conn:
            conn.execute("INSERT INTO app.analyst_reports (report_id, owner_key, topic, report) "
                         "VALUES (%(i)s, %(o)s, %(t)s, %(r)s::jsonb)",
                         {"i": report_id, "o": owner, "t": topic[:300],
                          "r": json.dumps(report, ensure_ascii=False, default=_json_default)})
    except Exception as e:
        print(f"WARNING: report not saved: {e}")
    return json.loads(json.dumps(report, default=_json_default))   # decimals -> numbers, dates -> text


def get_report(report_id: str) -> dict | None:
    if not _valid_uuid(report_id):
        return None
    try:
        row = fetch_one("SELECT report, created_at FROM app.analyst_reports WHERE report_id = %(i)s",
                        {"i": report_id})
    except Exception:
        return None
    if not row:
        return None
    return {**row["report"], "created_at": str(row["created_at"])[:16]}
