# Cottonil Data & AI Platform

A full data and AI platform for **Cottonil**, the Egyptian cotton apparel retailer (HVIA Task 3).
It turns 23 raw business tables and the product catalog into a clean data warehouse, 16 interactive
dashboards, a demand-forecasting model, and two AI assistants: a shopping chatbot for customers and
resellers, and a business analyst for management.

> **Data note:** the transactional data is partly generated, so some distributions are uniform by
> design. The dashboards and docs say so where it matters. The data files and generated reports are
> **not** part of this repository.

---

## What it does

| Area | What you get |
|---|---|
| **Data warehouse** | PostgreSQL medallion architecture (bronze -> silver -> gold), 64 data-quality checks, documented cleaning decisions, and automatic reconciliation of gold vs silver |
| **16 dashboards** | One YAML file per dashboard; shared filters (period, branches, channel); KPIs compared with the previous period; every chart has a table view and CSV export |
| **Demand forecast (ML)** | Holt-Winters per category, backtested against a seasonal-naive baseline; the forecast beats the baseline in every category |
| **Shopping Assistant** | Chatbot for customers and resellers: semantic product search (RAG + pgvector), search by photo, branches, store policy, and the logged-in customer's own orders and reorder suggestions |
| **Business Analyst** | Ask a question in Arabic or English, get the answer, a chart and the SQL. Uses schema RAG to pick the right tables and runs read-only SQL on gold only |
| **Extras** | Voice input and read-aloud, chat history plus long-term memory per user, product photos, Arabic UI support (RTL text) |

---

## Architecture

```
CSV files ──► BRONZE (raw text, as loaded)
                │  build_silver.sql   types, dates, clean text, keys
                ▼
             SILVER ──► quality_checks.sql ──► investigations.sql
                │  silver_fixes.sql   cleaning decisions D1-D4 + price index (no rows deleted)
                ▼
             GOLD   star schema: 7 dimensions, 10 facts, 4 marts + ML tables
                │
     ┌──────────┼───────────────┬───────────────────┐
     ▼          ▼               ▼                   ▼
  FastAPI    ML forecast    AI index (pgvector)   Business Analyst
  (YAML apps)                products / policies / (read-only role,
     │                       schema docs           gold only)
     ▼
  React dashboard + chat pages
```

**Stack:** PostgreSQL 16 + pgvector (Docker) · Python (pandas, SQLAlchemy, psycopg, statsmodels) ·
FastAPI · React + Vite + Recharts · Google Gemini via the OpenAI-compatible API.

---

## Repository layout

```
docker-compose.yml        PostgreSQL (pgvector) + pgAdmin
requirements.txt          Python packages for ETL / ML / AI scripts
.env.example              Settings template (copy to .env)

etl/                      Python runners for every pipeline step
  profile_data.py           profile the raw CSV files
  load_bronze.py            CSV -> bronze (COPY, all TEXT)
  build_silver.py           runs sql/build_silver.sql + sql/silver_fixes.sql
  check_quality.py          runs sql/quality_checks.sql  -> reports/quality_report.md
  investigate.py            runs sql/investigations.sql  -> reports/investigation_report.md
  build_gold.py             runs sql/build_gold.sql and prints the reconciliation
sql/                      All transformations, step by step ("-- @step:" blocks)
docs/                     project documentation (start with docs/README.md)
  architecture.md           components, schemas, technology, run order
  data_pipeline.md          bronze -> silver -> gold, quality checks, investigations, cleaning decisions
  data_model.md             every gold table and calculated column
  dashboards.md             the YAML app engine and the 16 dashboards
  ai_assistants.md          Shopping Assistant, Business Analyst, memory, security
  machine_learning.md       forecast method and evaluation, experiments not used
  data_limitations.md       known limits of the generated data and how they are handled
ml/
  forecast_demand.py        demand forecast used by the app
  run_ml.py                 runs the models used by the app
  experiments/              churn and anomaly experiments (not used, see docs)
ai/
  check_llm.py              checks the API key, models, embeddings and pgvector
  build_index.py            builds the RAG indexes + the read-only analyst role
  fetch_product_images.py   optional: product photos from the public website
  knowledge/                demo store-policy text for the chatbot
backend/                  FastAPI
  app/apps/*.yaml           one file per dashboard (KPIs + charts + SQL)
  app/engine.py             runs an app with the current filters
  app/chat/                 shopping assistant, business analyst, memory, image search
frontend/                 React app (dashboards + chat pages)
```

---

## Setup

**You need:** Docker Desktop, Python 3.11+, Node.js 18+, and a Google Gemini API key from
[aistudio.google.com](https://aistudio.google.com/apikey) (the free tier works).

### 1. Settings
```bash
cp .env.example .env        # then fill in the passwords and the API key
```

### 2. Database
```bash
docker compose up -d        # PostgreSQL on localhost:5435, pgAdmin on localhost:5055
```

### 3. Python environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 4. Data pipeline
Put the CSV files in `data/`, then:
```bash
python etl/load_bronze.py
python etl/build_silver.py
python etl/check_quality.py
python etl/investigate.py
python etl/build_gold.py     # prints the gold-vs-silver reconciliation (all PASS)
```

### 5. ML and AI
```bash
python ml/run_ml.py                    # demand forecast
python ai/check_llm.py                 # verify the API key and models
python ai/build_index.py               # RAG indexes + read-only role (a few minutes on the free tier)
python ai/fetch_product_images.py      # optional: product photos
```

### 6. Run the app
```bash
# terminal 1
cd backend
uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend
npm install
npm run dev                            # open http://localhost:5173
```

---

## Dashboards (16)

| Group | Dashboards |
|---|---|
| Overview | Executive Dashboard |
| Sales | Sales Performance · Channels & Wholesale · Price & Promotion Intelligence |
| Branches | Branch Performance & P&L · New Store Expansion & Site Selection |
| Customers & Marketing | Customers – Segments, Value & Churn · Marketing ROI & Campaigns |
| Products | Product Profitability & Margin · Size, Colour & Returns · Demand Forecasting & Product Planning |
| Inventory & Supply Chain | Inventory, Replenishment & Transfers · Procurement & Imports |
| Operations | Last-Mile Delivery · Workforce Productivity · Loss Prevention & Refund Risk |

To add a dashboard, add a YAML file in `backend/app/apps/`. No frontend code is needed.

---

## Data cleaning (summary)

No row is ever deleted. Unreliable source values are kept, and corrected columns and flags are added
next to them. See `docs/data_pipeline.md` for the evidence behind each decision and `docs/data_limitations.md` for the known limits of the data.

- **D1 – Refunds above item value:** refunds are capped at the value of the returned units (`refund_capped_egp`).
- **D2 – Opening dates:** branches sell before their reported opening date, so `effective_opening_date` = first real activity.
- **D3 – Duplicate branch names:** unique `branch_display_name`.
- **D4 – Order status vs returns:** the return status is derived from the returns table (`return_level`: none / partial / full).
- **F1 – Inflation:** a monthly price index; `real_*` columns are in 2026 catalog prices.
- **F7 – Partial months:** monthly charts use complete months only (`dim_date.is_complete_month`).

---

## AI assistants and security

**Shopping Assistant (customers and resellers)**
- The model never writes SQL. It can only call 7 fixed, parameterised tools.
- The customer id is injected by the server, never taken from the model, so a customer can only see their own orders.
- No tool exposes company sales, costs, employees, suppliers or other customers.
- Photo search: the vision model describes the photo, then the same semantic search runs. Photos are not stored.

**Business Analyst (management)**
- Schema RAG picks the relevant gold tables for each question.
- Generated SQL must be a single SELECT/WITH statement, with forbidden keywords rejected.
- It runs in a READ ONLY transaction with a 15-second timeout and at most 200 rows.
- It runs as the role `cottonil_reader`, which can read the **gold** schema only.

**Memory:** chat history and long-term memory live in schema `app`, keyed per customer (or per browser
for guests and the analyst). "New chat" summarises the chat into memory; "Forget" deletes it.

---

## Machine learning

| Model | Result | Decision |
|---|---|---|
| Demand forecast (Holt-Winters per category) | Clearly lower error than the seasonal-naive baseline in the backtest | **Used** in the Forecasting dashboard |
| Churn prediction (gradient boosting) | No better than random on this data | Not used; churn is shown rule-based (inactive 12+ months) |
| Sales anomalies (robust z-score) | Too noisy to give useful alerts | Not used |

Details are in `docs/machine_learning.md`. The experiment code is kept in `ml/experiments/`.

---

## Not in this repository
- `data/` – the source CSV files
- `reports/` – generated profiling, quality and investigation reports
- `.env` – passwords and the API key
