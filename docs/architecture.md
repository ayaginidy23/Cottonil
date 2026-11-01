# Architecture

## Goal
Turn Cottonil's raw business data (23 tables plus the public product catalog) into:
1. a clean, documented, trustworthy data warehouse,
2. interactive dashboards for every business area,
3. a demand forecast,
4. AI assistants for customers / resellers and for management,
5. AI tools for management: page explanations, Insight Scout, Report Agent, offers, security log.

## Components

```
                     PostgreSQL 16 + pgvector (Docker)
 CSV files --load--> bronze --> silver --> gold        audit (logs, quality checks)
                                            |           etl (helper functions)
                                            |           ai  (vector indexes, product photos)
                                            |           app (chat memory, offers, quotes,
                                            |                reports, security events)
          +---------------+-----------------+-----------------+--------------------+
          v               v                 v                 v                    v
     ML scripts      FastAPI backend    AI index         Shopping Assistant   Business Analyst
     forecast,       YAML app engine,   embeddings       (14 fixed tools)     (read-only SQL on gold)
     market basket   products, offers,  -> ai.*                               + Report Agent,
     -> gold.ml_*    security log                                             Insight Scout,
                          |                                                   Explain this page
                          v
                    React frontend: dashboards, product pages, simulator, AI tools,
                    chat pages, bilingual print pages (PDF), Arabic / English UI
```

### Backend modules

| Module | Does |
|---|---|
| `engine.py`, `filters.py`, `registry.py` | run a YAML dashboard with the shared filters (queries in parallel, cached) |
| `routers/apps.py` | dashboards + "Explain this page" |
| `routers/products.py` | product explorer, product page, simulator baseline |
| `routers/chat.py` | Shopping Assistant, Business Analyst, memory, offers for the cart, quotes |
| `routers/ai_tools.py` | Insight Scout, Report Agent, Security Log, offers management |
| `chat/` | the assistants and their tools, memory, image search, explain, insight scout, report agent |
| `promotions.py`, `security_log.py` | offers (`app.promotions`) and safety events (`app.security_events`) |
| `llm.py` | one place for the AI provider: several keys, fallback models, clear errors |

## Database schemas

| Schema | Content | Written by |
|---|---|---|
| `bronze` | Raw copy of each CSV, every column TEXT, plus `_source_file` / `_loaded_at` | `etl/load_bronze.py` |
| `silver` | Typed, cleaned tables with primary keys; corrected columns and flags from the cleaning decisions; `price_index_monthly` | `sql/build_silver.sql`, `sql/silver_fixes.sql` |
| `gold` | Star schema (dimensions, facts), marts, ML output tables | `sql/build_gold.sql`, `ml/*.py` |
| `audit` | `etl_log` (every pipeline step with row counts and timing), `data_quality_checks` (checks and reconciliation) | ETL scripts |
| `etl` | Helper SQL functions (clean_text, to_num, to_date_iso, ...) | `sql/build_silver.sql` |
| `ai` | `product_embeddings`, `kb_chunks`, `schema_docs`, `product_images` | `ai/build_index.py`, `ai/fetch_product_images.py` |
| `app` | Chat sessions, messages and long-term memory, security events, B2B quotes, Report Agent reports | backend (created automatically) |

**Roles:** the owner role runs the pipeline and the backend. `cottonil_reader` is a read-only role with
SELECT on `gold` only. The Business Analyst's SQL runs under this role.

## Why a medallion architecture
- **Bronze** keeps the source exactly as received. Any later step can be re-run from it, and nothing is lost.
- **Silver** is where data becomes correct (types, formats, keys) and where cleaning decisions are
  applied as extra columns, so every decision stays visible and reversible.
- **Gold** is shaped for use (star schema plus pre-aggregated marts), so dashboards, ML and AI read
  simple, fast, consistent tables. Everything downstream reads gold only.

## Technology

| Layer | Technology | Why |
|---|---|---|
| Database | PostgreSQL 16 + pgvector, Docker Compose | One engine for SQL analytics and vector search; isolated, reproducible setup |
| Pipeline | SQL files run step by step by small Python runners (psycopg) | Transformations stay readable SQL; Python adds logging, timing and reports |
| ML | pandas, statsmodels (Holt-Winters), scikit-learn (experiments) | Simple, explainable models with a proper backtest |
| Backend | FastAPI, psycopg connection pool, YAML app definitions | One generic engine serves all dashboards; a new dashboard is one YAML file |
| Frontend | React + Vite, Recharts, Leaflet (maps), lucide icons | One generic page renders every app; table view and CSV export for every chart; Arabic / English with right-to-left layout; print layouts for bilingual PDFs |
| AI | Google Gemini via the OpenAI-compatible API (chat, vision, embeddings) | Free tier available; changing provider is a `.env` change |

## Run order

```
docker compose up -d
python etl/profile_data.py         (optional, profiling report)
python etl/load_bronze.py
python etl/build_silver.py         (build_silver.sql + silver_fixes.sql)
python etl/check_quality.py
python etl/investigate.py
python etl/build_gold.py           (ends with the reconciliation)
python ml/run_ml.py                (forecast + market basket)
python ai/check_llm.py
python ai/build_index.py
python ai/fetch_product_images.py  (optional)
uvicorn app.main:app --port 8000   (in backend/)
npm run dev                        (in frontend/)
```

Every step is **idempotent**: tables are dropped and rebuilt, so any step can be re-run safely.

## Design principles
1. **Never delete data.** Problems are measured, investigated, and fixed with extra columns and flags.
2. **Prove it.** Quality checks before cleaning; reconciliation after building gold.
3. **Document inside the database.** `COMMENT ON` every gold table and the unreliable source columns.
   pgAdmin shows these comments, and the AI Analyst reads them.
4. **Be honest about the data.** Uniform or contradictory generated fields are labelled, not sold as insights.
5. **Security by design for AI.** The customer bot can only call fixed tools. The analyst runs
   read-only SQL on gold only, enforced by the database role. Every blocked attempt is logged.
6. **Show a model only if it works.** Every model is compared with a simple baseline; models with no
   real signal are documented and left out of the app.
