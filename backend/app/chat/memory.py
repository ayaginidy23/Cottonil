# =============================================================================
# chat/memory.py  -  Chat history + long-term memory for both assistants
# -----------------------------------------------------------------------------
# Two kinds of memory, like ChatGPT:
#
#   1. Conversation (short-term): every message of the current chat is saved in
#      app.chat_messages, so refreshing the page does not lose the chat, and the
#      model always sees the recent turns.
#
#   2. Long-term memory: when the user clicks "New chat", the finished chat is
#      summarised by the model into a few bullet points ("prefers size L",
#      "focuses on Alexandria branches") and merged into app.chat_memory.
#      Every new chat starts with that memory in the system prompt, so the
#      assistant still "knows" the user even though the screen is empty.
#
# Who owns a memory ("owner"):
#   shop + logged in  -> cust:<customer_id>   (each customer has their own memory)
#   shop + guest      -> guest:<browser id>
#   analyst           -> analyst:<browser id>
# The owner is built on the SERVER from the customer id / browser id, so one
# customer can never load another customer's memory.
#
# The tables live in schema "app", which the Business Analyst's read-only role
# (cottonil_reader) cannot read - so chats never leak into its SQL answers.
# =============================================================================

import json
import re
import uuid

from ..db import fetch_all, fetch_one, pool
from ..llm import chat_completion

MEMORY_MAX_CHARS = 1200
_ready = False

DDL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.chat_sessions (
    session_id  UUID PRIMARY KEY,
    assistant   TEXT NOT NULL,                 -- 'shop' or 'analyst'
    owner_key   TEXT NOT NULL,
    title       TEXT,
    closed      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_sessions_owner_idx ON app.chat_sessions (assistant, owner_key, updated_at DESC);
CREATE TABLE IF NOT EXISTS app.chat_messages (
    message_id  BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES app.chat_sessions ON DELETE CASCADE,
    role        TEXT NOT NULL,                 -- 'user' or 'assistant'
    content     TEXT NOT NULL,
    payload     JSONB,                         -- product cards, SQL, chart rows... (to redraw the chat)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON app.chat_messages (session_id, message_id);
CREATE TABLE IF NOT EXISTS app.chat_memory (
    assistant   TEXT NOT NULL,
    owner_key   TEXT NOT NULL,
    memory      TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (assistant, owner_key)
);
"""


def _ensure_tables() -> None:
    """Create the tables the first time they are needed."""
    global _ready
    if not _ready:
        with pool.connection() as conn:
            conn.execute(DDL)
        _ready = True


def _execute(query: str, params: dict) -> None:
    with pool.connection() as conn:
        conn.execute(query, params)


def _valid_uuid(value: str | None) -> str | None:
    """Ignore session ids that are not real UUIDs (bad or tampered input)."""
    try:
        return str(uuid.UUID(str(value))) if value else None
    except ValueError:
        return None


def owner_key(assistant: str, client_id: str, customer_id: str | None = None) -> str:
    client_id = re.sub(r"[^A-Za-z0-9-]", "", client_id or "")[:64] or "anonymous"
    if assistant == "shop" and customer_id:
        return f"cust:{customer_id}"
    return f"{'guest' if assistant == 'shop' else 'analyst'}:{client_id}"


# ---------------------------------------------------------------------------
# Long-term memory
# ---------------------------------------------------------------------------
def get_memory(assistant: str, owner: str) -> str:
    _ensure_tables()
    row = fetch_one("SELECT memory FROM app.chat_memory WHERE assistant = %(a)s AND owner_key = %(o)s",
                    {"a": assistant, "o": owner})
    return row["memory"] if row else ""


def clear_memory(assistant: str, owner: str) -> None:
    _ensure_tables()
    _execute("DELETE FROM app.chat_memory WHERE assistant = %(a)s AND owner_key = %(o)s",
             {"a": assistant, "o": owner})


def memory_prompt(memory: str) -> str:
    """The text added to the system prompt (empty when there is no memory yet)."""
    if not memory:
        return ""
    return ("\nLong-term memory about this user from previous conversations (use it to personalise "
            "answers, but the current request always wins):\n" + memory)


SUMMARY_PROMPT = {
    "shop": "a shopping assistant. Keep durable facts about the CUSTOMER: sizes, who they buy for "
            "(kids, wife...), styles/colours/categories they like, budget, preferred branch or city, "
            "language, and requests still open.",
    "analyst": "a business analyst for the management. Keep durable facts about the MANAGER: the topics, "
               "branches, categories and KPIs they care about, how they like answers (language, units, "
               "charts, level of detail), and questions still open. Do NOT copy result numbers.",
}


def _summarise(assistant: str, old_memory: str, messages: list[dict]) -> str:
    transcript = "\n".join(f"{m['role'].upper()}: {m['content'][:600]}" for m in messages[-30:])
    resp = chat_completion(
        messages=[
            {"role": "system", "content":
                f"You maintain the long-term memory of {SUMMARY_PROMPT[assistant]}\n"
                "Merge the OLD MEMORY with anything new and lasting from the CONVERSATION. "
                "Drop small talk and one-off details. Never store passwords, phone numbers or "
                "payment details. Write at most 8 short bullet points starting with '- ', in English. "
                "If there is nothing worth remembering, return the old memory unchanged."},
            {"role": "user", "content": f"OLD MEMORY:\n{old_memory or '(empty)'}\n\nCONVERSATION:\n{transcript}"},
        ],
        temperature=0.2,
    )
    text = (resp.choices[0].message.content or "").strip()
    return text[:MEMORY_MAX_CHARS] if text else old_memory


# ---------------------------------------------------------------------------
# Sessions (the visible chat)
# ---------------------------------------------------------------------------
def save_turn(assistant: str, owner: str, session_id: str | None,
              user_text: str, reply: str, payload: dict | None) -> str:
    """Save the user's message and the reply; create the session if needed. Returns the session id."""
    _ensure_tables()
    sid = None
    session_id = _valid_uuid(session_id)
    if session_id:
        row = fetch_one("""SELECT session_id FROM app.chat_sessions
                           WHERE session_id = %(s)s AND assistant = %(a)s AND owner_key = %(o)s
                             AND NOT closed""",
                        {"s": session_id, "a": assistant, "o": owner})      # must belong to this owner
        sid = str(row["session_id"]) if row else None
    if not sid:
        sid = str(uuid.uuid4())
        _execute("""INSERT INTO app.chat_sessions (session_id, assistant, owner_key, title)
                    VALUES (%(s)s, %(a)s, %(o)s, %(t)s)""",
                 {"s": sid, "a": assistant, "o": owner, "t": user_text[:80]})
    with pool.connection() as conn:
        conn.execute("""INSERT INTO app.chat_messages (session_id, role, content) VALUES (%(s)s, 'user', %(c)s)""",
                     {"s": sid, "c": user_text})
        conn.execute("""INSERT INTO app.chat_messages (session_id, role, content, payload)
                        VALUES (%(s)s, 'assistant', %(c)s, %(p)s)""",
                     {"s": sid, "c": reply, "p": json.dumps(payload, ensure_ascii=False, default=str)
                      if payload else None})
        conn.execute("UPDATE app.chat_sessions SET updated_at = now() WHERE session_id = %(s)s", {"s": sid})
    return sid


def current_session(assistant: str, owner: str) -> dict | None:
    """The last open chat of this owner (to restore it after a page refresh)."""
    _ensure_tables()
    s = fetch_one("""SELECT session_id FROM app.chat_sessions
                     WHERE assistant = %(a)s AND owner_key = %(o)s AND NOT closed
                     ORDER BY updated_at DESC LIMIT 1""", {"a": assistant, "o": owner})
    if not s:
        return None
    msgs = fetch_all("""SELECT role, content, payload FROM app.chat_messages
                        WHERE session_id = %(s)s ORDER BY message_id""", {"s": s["session_id"]})
    return {"session_id": str(s["session_id"]), "messages": msgs}


def new_chat(assistant: str, owner: str, session_id: str | None) -> dict:
    """Close the current chat and fold it into the long-term memory."""
    _ensure_tables()
    memory = get_memory(assistant, owner)
    warning = None
    session_id = _valid_uuid(session_id)
    if session_id:
        msgs = fetch_all("""SELECT m.role, m.content FROM app.chat_messages m
                            JOIN app.chat_sessions s USING (session_id)
                            WHERE m.session_id = %(s)s AND s.assistant = %(a)s AND s.owner_key = %(o)s
                            ORDER BY m.message_id""",
                         {"s": session_id, "a": assistant, "o": owner})
        if msgs:
            try:
                new_memory = _summarise(assistant, memory, msgs)
                if new_memory and new_memory != memory:
                    _execute("""INSERT INTO app.chat_memory (assistant, owner_key, memory)
                                VALUES (%(a)s, %(o)s, %(m)s)
                                ON CONFLICT (assistant, owner_key)
                                DO UPDATE SET memory = EXCLUDED.memory, updated_at = now()""",
                             {"a": assistant, "o": owner, "m": new_memory})
                    memory = new_memory
            except Exception as e:                   # quota etc.: start the new chat anyway
                warning = f"Memory was not updated this time ({str(e)[:120]})"
        _execute("""UPDATE app.chat_sessions SET closed = TRUE
                    WHERE session_id = %(s)s AND assistant = %(a)s AND owner_key = %(o)s""",
                 {"s": session_id, "a": assistant, "o": owner})
    return {"memory": memory, "warning": warning}