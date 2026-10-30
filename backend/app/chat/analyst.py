# =============================================================================
# chat/analyst.py  -  Business Analyst for management (text-to-SQL on gold)
# -----------------------------------------------------------------------------
# Flow for one question:
#   1. Schema RAG: find the gold tables most related to the question
#      (pgvector over ai.schema_docs; falls back to all gold tables)
#   2. Give the model those table descriptions + business rules + one tool: run_sql
#   3. The model writes a SELECT, we run it SAFELY, it reads the result
#      (it may fix and retry if the query fails), then answers in words
#   4. We return the answer + the SQL + the result rows (the UI draws a chart)
#
# Safety layers for run_sql:
#   - only one statement, must start with SELECT or WITH, no write/DDL keywords
#   - runs in a READ ONLY transaction with a 15 s timeout
#   - runs as the role "cottonil_reader", which can only read the gold schema
#   - at most MAX_ROWS rows are returned
# =============================================================================

import json
import re

from ..db import fetch_all, fetch_one, pool
from ..llm import chat_completion, embed, to_pgvector
from .memory import memory_prompt

MAX_STEPS = 6
MAX_ROWS = 200
READER_ROLE = "cottonil_reader"

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|copy|call|do|"
    r"vacuum|analyze|refresh|reindex|cluster|comment|security|set|reset|lock|listen|notify|"
    r"pg_sleep|pg_read|pg_write|lo_import|lo_export|dblink)\b",
    re.IGNORECASE,
)

BUSINESS_RULES = """
Business rules (always follow):
- Money is EGP before VAT. "Sales"/"revenue" = net_sales_after_returns_egp (after capped refunds).
- "Profit" for a branch = operating_profit_egp in gold.mart_branch_pnl_monthly.
  "Gross margin" = margin_after_returns_egp.
- real_* columns are inflation-adjusted to 2026 prices. Prices rose ~7x from 2018 to 2026,
  so for growth over years show real values (or units) next to nominal values.
- For monthly trends, join gold.dim_date and keep is_complete_month = true
  (first and last months of the data are incomplete).
- Returns: use return_level / has_return / returned_units, NOT any status column.
- Customers: customer_key = 'GUEST' means walk-in orders without a customer; exclude it
  when counting customers. RFM segments are in gold.mart_customer_rfm.
- Branch labels: use dim_branch.branch_display_name. Opening dates: effective_opening_date.
- Return reasons, age bands, carriers and expense categories are almost uniform (generated);
  do not present small differences between them as insights.
- The data covers 2018-10-19 to the last order date (see gold.dim_date where has_data).
"""

SYSTEM_PROMPT = """You are the Business Analyst assistant of Cottonil (Egyptian apparel retailer).
Managers ask business questions; you answer from the company data using PostgreSQL.

How to work:
1. Write ONE PostgreSQL SELECT (or WITH ... SELECT) over the gold schema and call run_sql.
   Always use schema-qualified names like gold.fact_orders. Aggregate in SQL; never select
   raw rows without a LIMIT. Round money to 0 decimals and ratios to 3.
2. If the query fails, read the error, fix it and call run_sql again.
3. Then answer: the direct answer first (numbers formatted, e.g. EGP 12.4M, 18.2%),
   then 2-4 short bullet insights, then any assumption you made.
Reply in the user's language (Egyptian Arabic if they write Arabic). Never invent numbers.
For a chart-friendly result, return a label/date column first and 1-3 numeric columns.
Product photos: the app shows a photo for every row that has a product_id column. So when the
user asks to SEE products / photos / pictures, include p.product_id (from gold.dim_product) in
the SELECT and say "the photos are shown below". Never say photos are unavailable.
"""

RUN_SQL_SPEC = [{
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": "Run one read-only PostgreSQL SELECT on the gold schema and get the rows back.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A single SELECT / WITH query"}},
            "required": ["query"],
        },
    },
}]


# ---------------------------------------------------------------------------
# Schema context
# ---------------------------------------------------------------------------
def _all_table_docs() -> dict[str, str]:
    """One text block per gold table: name, COMMENT and columns with types."""
    rows = fetch_all("""
        SELECT c.relname AS table_name,
               obj_description(c.oid, 'pg_class') AS comment,
               string_agg(a.attname || ' ' || format_type(a.atttypid, a.atttypmod), ', '
                          ORDER BY a.attnum) AS columns
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'gold'
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        WHERE c.relkind IN ('r', 'v', 'm')
        GROUP BY c.relname, c.oid
        ORDER BY c.relname
    """)
    return {r["table_name"]: f"gold.{r['table_name']}: {r['comment'] or ''}\n  columns: {r['columns']}"
            for r in rows}


CORE_TABLES = ("dim_date", "dim_branch", "dim_product", "fact_orders")


def _relevant_tables(question: str, docs: dict[str, str], k: int = 8) -> list[str]:
    """Schema RAG: pick the k tables closest in meaning to the question."""
    try:
        rows = fetch_all("""
            SELECT table_name FROM ai.schema_docs
            ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s
        """, {"q": to_pgvector(embed([question])[0]), "k": k})
        names = [r["table_name"] for r in rows if r["table_name"] in docs]
        for must in CORE_TABLES:                         # almost every question needs these
            if must in docs and must not in names:
                names.append(must)
        return names or list(docs)
    except Exception:
        return list(docs)                                 # no index yet -> send everything


# ---------------------------------------------------------------------------
# Safe SQL execution
# ---------------------------------------------------------------------------
def _check_sql(query: str) -> str | None:
    q = query.strip().rstrip(";").strip()
    if ";" in q:
        return "Only one statement is allowed."
    if not re.match(r"^(select|with)\b", q, re.IGNORECASE):
        return "Only SELECT / WITH queries are allowed."
    if FORBIDDEN.search(q):
        return "The query contains a forbidden keyword (only reading is allowed)."
    return None


def run_sql(query: str) -> dict:
    problem = _check_sql(query)
    if problem:
        return {"error": problem}
    q = query.strip().rstrip(";")
    try:
        with pool.connection() as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                conn.execute("SET LOCAL statement_timeout = '15s'")
                try:
                    # nested transaction = SAVEPOINT: if the role doesn't exist yet,
                    # only this statement is rolled back, not the whole transaction
                    with conn.transaction():
                        conn.execute(f"SET LOCAL ROLE {READER_ROLE}")  # gold-only permissions
                except Exception:
                    pass
                cur = conn.execute(q)
                cols = [d.name for d in cur.description] if cur.description else []
                rows = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        return {"columns": cols, "rows": rows[:MAX_ROWS], "row_count": min(len(rows), MAX_ROWS),
                "truncated": truncated}
    except Exception as e:
        return {"error": str(e).split("\n")[0][:400]}


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------
def _product_images(columns: list[str], rows: list[dict], limit: int = 12) -> list[dict]:
    """If the result has product_id, attach the product photos (from ai.product_images).
    Done by the server, not by the model's SQL: the read-only role only sees gold."""
    if "product_id" not in columns or not rows:
        return []
    try:
        if not fetch_one("SELECT to_regclass('ai.product_images') IS NOT NULL AS ok")["ok"]:
            return []
        ids = list(dict.fromkeys(str(r["product_id"]) for r in rows if r.get("product_id")))[:limit]
        found = {r["product_id"]: r for r in fetch_all("""
            SELECT i.product_id, i.image_url, MIN(p.product_name_ar) AS name, MIN(p.source_url) AS url
            FROM ai.product_images i JOIN gold.dim_product p ON p.product_id = i.product_id
            WHERE i.product_id = ANY(%(ids)s) GROUP BY i.product_id, i.image_url
        """, {"ids": ids})}
        return [found[i] for i in ids if i in found]          # keep the result's order
    except Exception:
        return []                                             # photos are a bonus, never an error


def chat(messages: list[dict], memory: str = "") -> dict:
    question = messages[-1]["content"]
    docs = _all_table_docs()
    tables = _relevant_tables(question, docs)
    schema = "\n".join(docs[t] for t in tables)
    others = ", ".join(f"gold.{t}" for t in docs if t not in tables)
    if others:
        schema += f"\nOther gold tables (columns not shown - only use if really needed): {others}"

    convo = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n{BUSINESS_RULES}{memory_prompt(memory)}\nRelevant tables:\n{schema}"},
        *[{"role": m["role"], "content": m["content"]} for m in messages[-10:]],
    ]
    last_ok, queries = None, []

    for _ in range(MAX_STEPS):
        resp = chat_completion(
            messages=convo, tools=RUN_SQL_SPEC, temperature=0.1,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {
                "reply": msg.content or "",
                "sql": last_ok["sql"] if last_ok else None,
                "columns": last_ok["columns"] if last_ok else [],
                "rows": last_ok["rows"] if last_ok else [],
                "tables_used": tables,
                "attempts": queries,
                "images": _product_images(last_ok["columns"], last_ok["rows"]) if last_ok else [],
            }
        convo.append({
            "role": "assistant", "content": msg.content or "",
            # model_dump keeps EVERYTHING the model sent, including Gemini 3's
            # "thought_signature" (extra_content); Gemini 3 rejects the next turn
            # with error 400 if that signature is not sent back.
            "tool_calls": [tc.model_dump(exclude_none=True) for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            try:
                query = json.loads(tc.function.arguments or "{}").get("query", "")
            except json.JSONDecodeError:
                query = ""
            result = run_sql(query)
            queries.append({"sql": query, "ok": "error" not in result,
                            "error": result.get("error")})
            if "error" not in result:
                last_ok = {"sql": query, "columns": result["columns"], "rows": result["rows"]}
            # the model sees at most 60 rows - enough to read the answer
            shown = dict(result)
            if "rows" in shown:
                shown["rows"] = shown["rows"][:60]
            convo.append({"role": "tool", "tool_call_id": tc.id,
                          "content": json.dumps(shown, ensure_ascii=False, default=str)})

    return {"reply": "I could not finish this analysis - please rephrase or narrow the question.",
            "sql": last_ok["sql"] if last_ok else None,
            "columns": last_ok["columns"] if last_ok else [], "rows": last_ok["rows"] if last_ok else [],
            "tables_used": tables, "attempts": queries}