# =============================================================================
# build_index.py  -  Build the RAG indexes in PostgreSQL (pgvector)
# -----------------------------------------------------------------------------
# RAG = Retrieval-Augmented Generation: before the model answers, we RETRIEVE
# the most relevant pieces of our own data and give them to it, so it answers
# from facts instead of inventing.
#
# This script creates schema "ai" with two tables:
#   ai.product_embeddings : one row per product (the 139 real catalog products):
#                           a text description + its embedding vector
#   ai.kb_chunks          : the knowledge base (ai/knowledge/*.md) split by
#                           "## " headings, each with its embedding
#   ai.schema_docs        : one description per gold table (comment + columns),
#                           used by the Business Analyst to pick the right tables
#                           ("schema RAG")
# It also creates the read-only role "cottonil_reader" (SELECT on gold only),
# which the Business Analyst uses to run its SQL.
#
# Search later = "ORDER BY embedding <=> query_vector" (<=> = cosine distance:
# the smaller, the closer in meaning).
#
# Re-run it whenever the catalog or the knowledge files change.
# Usage:  python ai/build_index.py
# =============================================================================

import os
import re
import sys
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = Path(__file__).resolve().parent / "knowledge"
load_dotenv(ROOT / ".env")

client = OpenAI(api_key=os.getenv("LLM_API_KEY"),
                base_url=os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
                timeout=60, max_retries=2)
EMBED_MODEL = os.getenv("LLM_EMBED_MODEL", "gemini-embedding-001")


# Free tier limit: ~100 embedding texts per MINUTE (each text counts as one request).
# So we send small batches, pause between them, and if Google still says "429 quota",
# we wait and retry instead of crashing.
BATCH = 20
PAUSE_SECONDS = 15          # 20 texts every 15 s = 80 per minute (under the 100 limit)


def embed(texts):
    out = []
    for i in range(0, len(texts), BATCH):
        chunk = texts[i:i + BATCH]
        for attempt in range(6):
            try:
                r = client.embeddings.create(model=EMBED_MODEL, input=chunk)
                break
            except RateLimitError:
                wait = 30 + 10 * attempt
                print(f"   rate limit reached - waiting {wait}s and retrying...")
                time.sleep(wait)
        else:
            sys.exit("Still rate-limited after several retries - try again in a few minutes.")
        out.extend(d.embedding for d in r.data)
        print(f"   embedded {min(i + BATCH, len(texts))}/{len(texts)}")
        if i + BATCH < len(texts):
            time.sleep(PAUSE_SECONDS)
    return out


def vec(v):
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


# One descriptive text per product, built from gold (Arabic name + English facts).
# The richer the text, the better the semantic search.
PRODUCT_DOCS_SQL = """
SELECT p.product_id,
       MIN(p.product_name_ar)                                   AS name_ar,
       MIN(p.category)                                          AS category,
       MIN(p.audience)                                          AS audience,
       string_agg(DISTINCT p.size, ', ')                        AS sizes,
       string_agg(DISTINCT p.color_ar, '، ')                    AS colors,
       MIN(p.sku_list_price_egp)                                AS min_price,
       MAX(p.sku_list_price_egp)                                AS max_price,
       MIN(p.source_url)                                        AS url,
       COALESCE((SELECT SUM(m.units) FROM gold.mart_sku_monthly m
                 JOIN gold.dim_product d2 ON d2.sku_id = m.sku_id
                 WHERE d2.product_id = p.product_id), 0)        AS units_sold
FROM gold.dim_product p
GROUP BY p.product_id
ORDER BY p.product_id
"""


def product_text(r):
    return (f"{r['name_ar']}. Category: {r['category']}. For: {r['audience']}. "
            f"Sizes: {r['sizes']}. Colours: {r['colors']}. "
            f"Price: {r['min_price']:.0f} to {r['max_price']:.0f} EGP.")


def kb_chunks():
    chunks = []
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for part in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:   # split on "## " headings
            title, _, body = part.partition("\n")
            chunks.append({"source": path.name, "title": title.strip(), "content": body.strip()})
    return chunks


def main():
    if not os.getenv("LLM_API_KEY"):
        sys.exit("LLM_API_KEY is missing in .env (run ai/check_llm.py first)")

    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"), port=int(os.getenv("POSTGRES_PORT", "5435")),
        dbname=os.getenv("POSTGRES_DB"), user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"), autocommit=True,
        row_factory=dict_row,
    ) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("CREATE SCHEMA IF NOT EXISTS ai")

        # ---------------- products ----------------
        rows = conn.execute(PRODUCT_DOCS_SQL).fetchall()
        print(f"Products: {len(rows)}")
        texts = [product_text(r) for r in rows]
        vectors = embed(texts)
        dim = len(vectors[0])                                  # vector size depends on the model

        with conn.transaction():
            conn.execute("DROP TABLE IF EXISTS ai.product_embeddings")
            conn.execute(f"""
                CREATE TABLE ai.product_embeddings (
                    product_id  TEXT PRIMARY KEY,
                    name_ar     TEXT,
                    category    TEXT,
                    audience    TEXT,
                    sizes       TEXT,
                    colors      TEXT,
                    min_price   NUMERIC,
                    max_price   NUMERIC,
                    url         TEXT,
                    units_sold  BIGINT,
                    content     TEXT,
                    embedding   vector({dim})
                )""")
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO ai.product_embeddings VALUES
                       (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)""",
                    [(r["product_id"], r["name_ar"], r["category"], r["audience"], r["sizes"],
                      r["colors"], r["min_price"], r["max_price"], r["url"], r["units_sold"],
                      t, vec(v)) for r, t, v in zip(rows, texts, vectors)],
                )

        # ---------------- knowledge base ----------------
        chunks = kb_chunks()
        print(f"Knowledge chunks: {len(chunks)}")
        kvecs = embed([f"{c['title']}\n{c['content']}" for c in chunks])
        with conn.transaction():
            conn.execute("DROP TABLE IF EXISTS ai.kb_chunks")
            conn.execute(f"""
                CREATE TABLE ai.kb_chunks (
                    chunk_id  SERIAL PRIMARY KEY,
                    source    TEXT,
                    title     TEXT,
                    content   TEXT,
                    embedding vector({len(kvecs[0])})
                )""")
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO ai.kb_chunks (source, title, content, embedding) VALUES (%s, %s, %s, %s::vector)",
                    [(c["source"], c["title"], c["content"], vec(v)) for c, v in zip(chunks, kvecs)],
                )

        # ---------------- gold schema docs (for the Business Analyst) ----------------
        tables = conn.execute("""
            SELECT c.relname AS table_name,
                   COALESCE(obj_description(c.oid, 'pg_class'), '') AS comment,
                   string_agg(a.attname, ', ' ORDER BY a.attnum) AS columns
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'gold'
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
            WHERE c.relkind IN ('r', 'v', 'm')
            GROUP BY c.relname, c.oid ORDER BY c.relname
        """).fetchall()
        print(f"Gold tables: {len(tables)}")
        tdocs = [f"Table gold.{t['table_name']}. {t['comment']} Columns: {t['columns']}" for t in tables]
        tvecs = embed(tdocs)
        with conn.transaction():
            conn.execute("DROP TABLE IF EXISTS ai.schema_docs")
            conn.execute(f"""
                CREATE TABLE ai.schema_docs (
                    table_name TEXT PRIMARY KEY,
                    content    TEXT,
                    embedding  vector({len(tvecs[0])})
                )""")
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO ai.schema_docs VALUES (%s, %s, %s::vector)",
                    [(t["table_name"], d, vec(v)) for t, d, v in zip(tables, tdocs, tvecs)],
                )

        # ---------------- read-only role for the Business Analyst ----------------
        conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cottonil_reader') THEN
                    CREATE ROLE cottonil_reader NOLOGIN;
                END IF;
            END $$;
        """)
        conn.execute("GRANT USAGE ON SCHEMA gold TO cottonil_reader")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA gold TO cottonil_reader")
        # tables created later in gold (pipeline re-runs) get the same permission automatically
        conn.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO cottonil_reader")
        conn.execute(f"GRANT cottonil_reader TO CURRENT_USER")

        print(f"\nDone: {len(rows)} products, {len(chunks)} knowledge chunks and "
              f"{len(tables)} gold tables indexed (vector size {dim}); role cottonil_reader ready.")


if __name__ == "__main__":
    main()
