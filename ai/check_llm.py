# =============================================================================
# check_llm.py  -  Verify the AI setup BEFORE building anything with it
# -----------------------------------------------------------------------------
# Checks, in order:
#   1. the API key works and which models your key can use
#   2. the chat model answers
#   3. the embedding model returns vectors (and their size)
#   4. PostgreSQL has the pgvector extension
#
# Usage (project folder, venv active):
#     python ai/check_llm.py
# =============================================================================

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

key = os.getenv("LLM_API_KEY", "").split(",")[0].strip()      # first key if several
base_url = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
chat_model = os.getenv("LLM_CHAT_MODEL", "gemini-2.5-flash")
embed_model = os.getenv("LLM_EMBED_MODEL", "gemini-embedding-001")

if not key:
    sys.exit("LLM_API_KEY is missing in .env")

client = OpenAI(api_key=key, base_url=base_url, timeout=45, max_retries=0)   # fail fast
ok = True

print("1) Models available to your key (chat / embedding candidates):")
try:
    names = sorted(m.id for m in client.models.list())
    for n in names:
        if any(w in n for w in ("flash", "pro", "embedding", "grok", "gpt")):
            print("   -", n)
except Exception as e:
    print("   could not list models:", e)

fallbacks = [m.strip() for m in (os.getenv("LLM_FALLBACK_MODELS")
                                 or os.getenv("GEMINI_FALLBACK_MODELS", "")).split(",") if m.strip()]
chat_ok = False
for i, m in enumerate([chat_model, *fallbacks]):
    label = "Chat model" if i == 0 else "   fallback"
    print(f"\n2) {label} '{m}':" if i == 0 else f"{label} '{m}':", end=" ", flush=True)
    try:
        r = client.chat.completions.create(
            model=m, messages=[{"role": "user", "content": "Reply with the single word: OK"}])
        print("OK ->", (r.choices[0].message.content or "").strip()[:40])
        chat_ok = True
    except Exception as e:
        body = str(getattr(e, "body", None) or e)
        kind = ("PER-DAY quota used up (wait until tomorrow or use another key/model)" if "PerDay" in body
                else "per-minute limit (wait 1 minute)" if "PerMinute" in body else "")
        print("FAILED:", kind or body[:300])
if not chat_ok:
    ok = False
    print("   -> pick a model from the list above that contains 'flash' (e.g. gemini-flash-latest)")

print(f"\n3) Embedding model '{embed_model}':", end=" ")
try:
    r = client.embeddings.create(model=embed_model, input=["تيشيرت قطن رجالي"])
    print(f"OK -> vector size {len(r.data[0].embedding)}")
except Exception as e:
    ok = False
    body = str(getattr(e, "body", None) or e)
    print("FAILED:", "PER-DAY quota used up" if "PerDay" in body else body[:300])

print("4) pgvector in PostgreSQL:", end=" ")
try:
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"), port=int(os.getenv("POSTGRES_PORT", "5435")),
        dbname=os.getenv("POSTGRES_DB"), user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"), autocommit=True,
    ) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        v = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
        print("OK -> version", v)
except Exception as e:
    ok = False
    print("FAILED:", e)
    print("   -> use image pgvector/pgvector:pg16 in docker-compose.yml, then: docker compose up -d")

print("\nAll good - next: python ai/build_index.py" if ok else "\nFix the FAILED items above first.")