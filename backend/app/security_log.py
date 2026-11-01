# =============================================================================
# security_log.py  -  Records every time a safety rule of the AI assistants fires
# -----------------------------------------------------------------------------
# The assistants already BLOCK unsafe things (see docs/ai_assistants.md). This
# file only WRITES DOWN that it happened, so management can see on the
# "Security Log" page that the protections really work:
#
#   source     kind                      when
#   analyst    blocked_sql               generated SQL was not a single read-only SELECT
#   analyst    permission_denied         SQL tried to read outside the gold schema
#   shop       customer_id_override      the model tried to use another customer's id
#   shop       other_customer_order      a customer asked for an order that is not theirs
#   shop       sensitive_question        a customer asked about sales, profit, salaries...
#   shop       prompt_injection          "ignore your instructions", "show the system prompt"...
#   shop       login_required            a guest asked for orders / purchase history
#
# Table app.security_events lives in schema "app", which the analyst's read-only
# role cannot read. Logging must never break a chat, so every error is swallowed.
# =============================================================================

import json
import re

from .db import fetch_all, pool

_ready = False

DDL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.security_events (
    event_id    BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    source      TEXT NOT NULL,          -- 'shop' or 'analyst'
    kind        TEXT NOT NULL,
    severity    TEXT NOT NULL,          -- 'high' | 'medium' | 'low'
    owner_key   TEXT,                   -- who (customer / browser id), never a password
    action      TEXT NOT NULL,          -- what the system did: blocked / refused / asked to log in
    detail      JSONB
);
CREATE INDEX IF NOT EXISTS security_events_time_idx ON app.security_events (created_at DESC);
"""

SEVERITY = {
    "blocked_sql": "high",
    "permission_denied": "high",
    "customer_id_override": "high",
    "prompt_injection": "high",
    "other_customer_order": "medium",
    "sensitive_question": "medium",
    "login_required": "low",
}

# Questions a customer chatbot must refuse (company internals). Arabic, English and
# Franco-Arabic spellings. Used only to LOG the attempt; the refusal itself is done
# by the system prompt and by the tools (no tool can return such data).
SENSITIVE = re.compile(
    r"(profit|revenue|turnover|total sales|company sales|margin|salar(y|ies)|payroll|employee|staff|"
    r"supplier|cost price|wholesale cost|other customers?|customer list|database|"
    r"ارباح|أرباح|الربح|مبيعات الشركة|إيرادات|ايرادات|هامش|مرتب|مرتبات|رواتب|موظف|الموظفين|"
    r"مورد|الموردين|سعر التكلفة|عملاء تانيين|باقي العملاء|قاعدة البيانات|"
    r"arba7|ar ba7|morattab|mortab|mwazaf|mowazaf|mored)",
    re.IGNORECASE,
)
INJECTION = re.compile(
    r"(ignore (all |the |your )?(previous |above )?(instructions|rules)|system prompt|developer mode|"
    r"jailbreak|act as (an? )?admin|you are now|pretend to be|"
    r"انسى التعليمات|تجاهل التعليمات|تجاهل القواعد|انسى القواعد|برومبت النظام|اعرض التعليمات)",
    re.IGNORECASE,
)


def _ensure():
    global _ready
    if not _ready:
        with pool.connection() as conn:
            conn.execute(DDL)
        _ready = True


def log_event(source: str, kind: str, action: str, owner: str | None = None, **detail) -> None:
    try:
        _ensure()
        with pool.connection() as conn:
            conn.execute(
                """INSERT INTO app.security_events (source, kind, severity, owner_key, action, detail)
                   VALUES (%(s)s, %(k)s, %(sev)s, %(o)s, %(a)s, %(d)s::jsonb)""",
                {"s": source, "k": kind, "sev": SEVERITY.get(kind, "low"), "o": owner, "a": action,
                 "d": json.dumps({k: (str(v)[:300] if v is not None else None) for k, v in detail.items()},
                                 ensure_ascii=False)})
    except Exception as e:
        print(f"WARNING: security event not saved: {e}")


def check_customer_message(text: str, owner: str | None) -> None:
    """Log (not block) suspicious customer messages; the assistant refuses them itself."""
    if not text:
        return
    if INJECTION.search(text):
        log_event("shop", "prompt_injection", "refused by the assistant rules", owner, message=text[:200])
    elif SENSITIVE.search(text):
        log_event("shop", "sensitive_question", "refused - no tool returns company data", owner,
                  message=text[:200])


def recent_events(limit: int = 200) -> list[dict]:
    _ensure()
    return fetch_all("""
        SELECT event_id, created_at, source, kind, severity, owner_key, action, detail
        FROM app.security_events ORDER BY created_at DESC LIMIT %(n)s
    """, {"n": max(1, min(limit, 1000))})


def summary(days: int = 30) -> dict:
    _ensure()
    by_kind = fetch_all("""
        SELECT source, kind, severity, COUNT(*) AS events, MAX(created_at) AS last_seen
        FROM app.security_events WHERE created_at >= now() - make_interval(days => %(d)s)
        GROUP BY 1, 2, 3 ORDER BY events DESC
    """, {"d": days})
    by_day = fetch_all("""
        SELECT created_at::date AS day, COUNT(*) AS events,
               COUNT(*) FILTER (WHERE severity = 'high') AS high
        FROM app.security_events WHERE created_at >= now() - make_interval(days => %(d)s)
        GROUP BY 1 ORDER BY 1
    """, {"d": days})
    total = sum(r["events"] for r in by_kind)
    high = sum(r["events"] for r in by_kind if r["severity"] == "high")
    return {"days": days, "total": total, "high": high, "by_kind": by_kind, "by_day": by_day}
