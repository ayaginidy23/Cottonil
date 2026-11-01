# Cottonil Data & AI Platform

An end-to-end data and AI platform for **Cottonil**, the Egyptian cotton apparel brand (HVIA Task 3).

The idea in one line: take the company's raw data, make it clean and trustworthy, then put it in the
hands of managers and customers through dashboards and AI assistants.

```
Raw CSV files  ->  Data engineering (Bronze, Silver, Gold)  ->  Dashboards and forecasting  ->  AI assistants
```

> **Data note:** the transactional data is partly generated, so some distributions are uniform by
> design. The dashboards and docs say so where it matters. The data files and generated reports are
> **not** part of this repository.

---

## What it does

### Data engineering
- **Medallion architecture** on PostgreSQL: bronze (raw, as loaded) -> silver (typed, cleaned) -> gold (star schema and marts), built from 23 raw business tables and the product catalog
- **64 data-quality checks**, investigations and documented cleaning decisions; **no row is ever deleted**
- **Automatic reconciliation** of gold against silver, so every dashboard number can be traced to the source
- **Inflation-adjusted ("real") values** next to nominal EGP, to separate real growth from price increases

### Analytics and machine learning
- **16 dashboards**, one YAML file each, with shared filters (period, branches, channel), KPIs compared with the previous period, a table view and CSV export for every chart, and **Egypt maps** by governorate
- **Explain this page:** an AI summary of the page being viewed, in English and Egyptian Arabic, read aloud on request
- **Download PDF** of any dashboard or product page, with titles and the AI summary in both languages
- **Arabic / English interface** with right-to-left layout
- **Product Explorer** and a page per product (photo, sales, sizes, colours, best branches, category forecast)
- **What-if Simulator:** the effect of a discount on units, sales and gross margin, with the break-even discount
- **Demand forecast** (Holt-Winters per category), backtested against a seasonal baseline. Models with no real signal (churn, anomalies, market basket) were tested, documented and left out

### AI assistants
- **Shopping Assistant** (customers and resellers): semantic product search (RAG + pgvector), search by photo, size advice, product comparison, complete-the-look, current offers, a cart that applies the best offer and sends the order on WhatsApp, wholesale price quotes as bilingual PDF, branches, store policy, and the logged-in customer's own orders. Understands Arabic, English and Franco-Arabic
- **Business Analyst** (management): a question in Arabic or English -> schema RAG picks the tables -> safe read-only SQL -> answer, chart and the SQL. Hands-free **talk to your data** voice mode
- **Report Agent:** one topic -> a full management report with charts, in English and Egyptian Arabic, as PDF
- **Insight Scout:** finds what changed in the business (categories, branches, channels, margin, returns, customers, stock, forecast) and suggests the next step
- **Offers:** management adds, pauses and deletes offers; the chatbot announces them and the cart applies them
- **Security Log:** every blocked attempt (unsafe SQL, reading outside gold, another customer's order, company-data questions, prompt injection) is recorded and shown
- **Memory:** chat history plus long-term memory per user ("New chat" summarises, "Forget" deletes)

---

## Architecture

```
CSV files ──► BRONZE (raw text, as loaded)
                │  build_silver.sql   types, dates, clean text, keys
                ▼
             SILVER ──► quality_checks.sql ──► investigations.sql
                │  silver_fixes.sql   cleaning decisions D1-D4 + price index (no rows deleted)
                ▼
             GOLD   star schema: dimensions, facts, marts + ML tables
                │
     ┌──────────┼───────────────┬────────────────────┐
     ▼          ▼               ▼                    ▼
  FastAPI    ML forecast    AI index (pgvector)    AI assistants and tools
  (YAML apps,               products, policies,    (shopping tools only; analyst:
   products,                schema docs            read-only role on gold only)
   offers)
     │
     ▼
  React: dashboards, product pages, simulator, AI tools, chat pages, bilingual PDFs
```

**Stack:** PostgreSQL 16 + pgvector (Docker) · SQL · Python (pandas, SQLAlchemy, psycopg, statsmodels) ·
FastAPI · React + Vite + Recharts + Leaflet · Google Gemini via the OpenAI-compatible API (function calling,
embeddings, vision) · RAG · Web Speech API.

---

## Repository layout

```
docker-compose.yml        PostgreSQL + pgvector and pgAdmin
requirements.txt          Python packages for ETL / ML / AI scripts
.env.example              settings template (copy to .env)

etl/                      Python runners for every pipeline step
  profile_data.py           profile the raw CSV files
  load_bronze.py            CSV -> bronze (COPY, all TEXT)
  build_silver.py           runs sql/build_silver.sql + sql/silver_fixes.sql
  check_quality.py          runs sql/quality_checks.sql  -> reports/quality_report.md
  investigate.py            runs sql/investigations.sql  -> reports/investigation_report.md
  build_gold.py             runs sql/build_gold.sql and prints the reconciliation
sql/                      all transformations, step by step ("-- @step:" blocks)
ml/
  forecast_demand.py        demand forecast used by the app
  market_basket.py          "bought together" rules (tested; no real signal in this data)
  run_ml.py                 runs the models
  experiments/              churn and anomaly experiments (not used, see docs)
ai/
  check_llm.py              checks every API key, the models, embeddings and pgvector
  build_index.py            builds the RAG indexes + the read-only analyst role
  fetch_product_images.py   real product photos and links from the public store
  knowledge/                demo store-policy text for the chatbot
backend/                  FastAPI
  app/apps/*.yaml           one file per dashboard (KPIs + charts + SQL)
  app/engine.py             runs a dashboard with the current filters (parallel queries, cache)
  app/chat/                 shopping assistant + tools, business analyst, memory, image search,
                            explain page, insight scout, report agent
  app/promotions.py         offers
  app/security_log.py       records every time a safety rule fires
  app/routers/              apps, chat, ai_tools, products
frontend/                 React app
  src/pages/                dashboards, chat pages, AI tools, products, simulator, print pages
  src/components/           charts, map, KPI cards, cart, compare table, quote card, report view
  src/lib/                  API calls, filters, Arabic / English (i18n.jsx, labels_ar.json), speech
docs/                     project documentation (start with docs/README.md)
```

---

## Setup

**You need:** Docker Desktop, Python 3.11+, Node.js 18+, and a Google Gemini API key from
[aistudio.google.com](https://aistudio.google.com/apikey) (the free tier works).

### 1. Settings
```bash
cp .env.example .env        # fill in the passwords and the API key (several keys: key1,key2)
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
python ml/run_ml.py                    # demand forecast (+ market basket experiment)
python ai/check_llm.py                 # verify every API key and the models
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

The tables for chat memory, offers, quotes, reports and security events are created automatically the
first time they are used.

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
next to them. See `docs/data_pipeline.md` for the evidence behind each decision and
`docs/data_limitations.md` for the known limits of the data.

- **D1 – Refunds above item value:** refunds are capped at the value of the returned units (`refund_capped_egp`).
- **D2 – Opening dates:** branches sell before their reported opening date, so `effective_opening_date` = first real activity.
- **D3 – Duplicate branch names:** unique `branch_display_name`.
- **D4 – Order status vs returns:** the return status is derived from the returns table (`return_level`: none / partial / full).
- **F1 – Inflation:** a monthly price index; `real_*` columns are in 2026 catalog prices.
- **F7 – Partial months:** monthly charts use complete months only (`dim_date.is_complete_month`).

---

## AI security

**Shopping Assistant**
- The model never writes SQL. It can only call 14 fixed, parameterised tools.
- The customer id is injected by the server, never taken from the model, so a customer can only see their own orders.
- No tool returns company sales, costs, employees, suppliers or other customers.
- Photo search: the vision model describes the photo, then the same semantic search runs. Photos are not stored.

**Business Analyst and Report Agent**
- Schema RAG picks the relevant gold tables for each question.
- Generated SQL must be a single SELECT/WITH statement; forbidden keywords are rejected.
- It runs in a READ ONLY transaction with a 15-second timeout and at most 200 rows.
- It runs as the role `cottonil_reader`, which can read the **gold** schema only.

**Security Log:** every blocked attempt is recorded in `app.security_events` and shown on the Security Log page.

---

## Machine learning

| Model | Result | Decision |
|---|---|---|
| Demand forecast (Holt-Winters per category) | Lower error than the seasonal-naive baseline in the backtest, for the total and every category | **Used** in the Forecasting dashboard and product pages |
| Churn prediction (gradient boosting) | No better than random on this data | Not used; churn is shown rule-based (inactive 12+ months) |
| Sales anomalies (robust z-score) | Too noisy to give useful alerts | Not used |
| Market basket (association rules) | Lift about 1 for every pair: no real basket pattern | Not shown; the chatbot suggests matching items instead |

Details are in `docs/machine_learning.md`.

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | components, schemas, backend modules, technology, run order |
| [docs/data_pipeline.md](docs/data_pipeline.md) | bronze -> silver -> gold, quality checks, investigations, cleaning decisions |
| [docs/data_model.md](docs/data_model.md) | every gold and app table and calculated column |
| [docs/dashboards.md](docs/dashboards.md) | the YAML app engine, the 16 dashboards and the other pages |
| [docs/ai_assistants.md](docs/ai_assistants.md) | assistants, tools, offers, AI tools, memory, voice, security |
| [docs/machine_learning.md](docs/machine_learning.md) | forecast method and evaluation, experiments not used |
| [docs/data_limitations.md](docs/data_limitations.md) | known limits of the generated data and how they are handled |

---

## Not in this repository
- `data/` – the source CSV files
- `reports/` – generated profiling, quality and investigation reports
- `.env` – passwords and API keys

---

## Acknowledgements
Built as HVIA Task 3. Thank you to HVIA and Ayman for the guidance and support.
