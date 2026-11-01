# AI assistants

Two assistants with very different security models:

| | Shopping Assistant | Business Analyst |
|---|---|---|
| Users | Customers and resellers | Management |
| What the model may do | Call 14 fixed tools | Write SQL (read-only, gold only) |
| Data it can reach | Public catalog, store policy, branches, current offers, the logged-in customer's own orders | The gold schema (read-only) |
| Code | `backend/app/chat/shop_assistant.py`, `shop_tools.py`, `image_search.py` | `backend/app/chat/analyst.py` (+ `report_agent.py`, `insight_scout.py`, `explain.py`) |

Both use `backend/app/llm.py` (OpenAI-compatible client for Gemini) and `backend/app/chat/memory.py`.
The AI tools for management (Explain this page, Insight Scout, Report Agent) and the Offers and
Security Log pages are described further down.

---

## LLM setup (`llm.py`)
- One client for chat, vision and embeddings; changing the provider is a `.env` change
  (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_CHAT_MODEL`, `LLM_FALLBACK_MODELS`, `LLM_EMBED_MODEL`).
- **Resilience on the free tier:** every request tries each API key (`LLM_API_KEY` can hold several,
  comma-separated) × each model (main model, then fallbacks). If everything was rate-limited (HTTP 429),
  it waits once and retries. The final error names what each model answered (per-minute limit,
  per-day quota, not found...), and the API turns a quota problem into a clear HTTP 429 message.
- Single-question embeddings are cached, so a repeated question costs no quota.
- **Gemini 3 "thought signatures":** when the model calls a tool, the request is sent back exactly as
  received (`tool_call.model_dump()`). Gemini 3 rejects the next turn if the signature is missing.
- `ai/check_llm.py` lists the models available to the key and tests the chat models, embeddings and pgvector.

## RAG indexes (`ai/build_index.py`)
RAG = Retrieval-Augmented Generation: before answering, retrieve the most relevant pieces of our own
data and give them to the model, so it answers from facts.

| Index | Content | Used by |
|---|---|---|
| `ai.product_embeddings` | one descriptive text per product (Arabic name, category, audience, sizes, colours, price range) + vector | product search |
| `ai.kb_chunks` | `ai/knowledge/*.md` split by `## ` headings + vectors (demo store policy) | policy questions |
| `ai.schema_docs` | one description per gold table (comment + columns) + vector | the analyst's table selection |

Search = `ORDER BY embedding <=> query_vector` (cosine distance in pgvector), so the results are
close in **meaning**, not just in words. Embedding calls are throttled for the free tier. The script
also creates the read-only role `cottonil_reader`.

---

## Shopping Assistant

### One turn
1. The frontend sends the conversation and the demo login (`customer_id`), plus a browser id and a session id.
2. The server builds the system prompt (rules + who the user is + long-term memory) and sends it with the last 12 messages and the tool list.
3. The model either answers, or asks for tool calls (function calling).
4. The server runs the tools and sends the results back. This repeats up to 5 rounds.
5. The reply comes back with product cards (photo, price range, sizes, link) and the names of the tools used. The turn is saved.

### Tools

| Tool | Does | Login |
|---|---|---|
| `search_products` | semantic search in the catalog, optional max price and size | no |
| `compare_products` | 2-4 products side by side (category, audience, sizes, colours, price, photo) | no |
| `bought_together` | "complete the look": products bought in the same orders (market basket, `gold.ml_product_pairs`); if there is no strong pattern, matching items of other categories for the same audience | no |
| `size_advice` | recommends a size from height / weight / waist (or the child's age) and checks that the product is made in that size. **Demo size chart** (Cottonil publishes no official one) | no |
| `current_offers` | the offers running today, from `app.promotions` (managed on the **Offers** page) | no |
| `add_to_cart` / `remove_from_cart` | checks the product and size exist and returns the real SKU and price; the cart lives in the browser | no |
| `b2b_quote` | wholesale price quote: list prices, **demo** volume-discount tiers (24+ / 100+ / 300+ units), total; saved in `app.b2b_quotes` and downloadable as a bilingual PDF | no |
| `find_branches` | branches in a governorate (lists covered governorates if none) | no |
| `store_policy` | returns, exchange, delivery, payment (demo knowledge base) | no |
| `my_orders` | the customer's recent orders | yes |
| `track_order` | status / delivery of one of the customer's orders | yes |
| `reorder_suggestions` | for resellers: what they buy most | yes |
| `purchase_summary` | the customer's purchases per year | yes |

**Franco-Arabic:** the system prompt teaches the model Arabizi ("3ayez boxer a2tan size L":
3 = ع, 7 = ح, 2 = ء ...). It answers in Egyptian Arabic and translates the request into normal
Arabic / English words before calling a tool, so the semantic search still works.

**Cart and WhatsApp order:** the bot fills the cart with `add_to_cart`; the cart is sent back with
every message so "remove the boxer" works. "WhatsApp order" opens WhatsApp with the order written out
(items, sizes, quantities, total). `WHATSAPP_NUMBER` in `.env` sets the shop's number; without it the
customer picks the chat. There is no online payment in the demo.

**Offers (`promotions.py`, page *Offers*):** management adds offers: a discount on one category, one
audience, or the whole order with N+ pieces, with start and end dates, and can pause or delete them. The
first run creates three demo offers from real catalog categories (marked "demo"). The bot tells customers
about running offers (`current_offers`, never invented), and the cart tries every running offer and applies
the one that saves the most - offers are not combined. It also hints "add 1 more piece to get 10% off".
Wholesale quotes keep their own volume tiers.

### Security
- The model never writes SQL. Tools run fixed, parameterised queries.
- `customer_id` is injected by the server and removed from the model's arguments, so a customer can
  only reach their own data.
- An order of another customer gets the same "not found" answer as a non-existent order, so nothing leaks.
- No tool returns company sales, profit, costs, employees, suppliers or other customers. Even a
  successful prompt injection has no path to that data. ("Complete the look" only returns product
  cards, never counts.)

### Security log (`security_log.py`, page *Security Log*)
Every time a protection fires it is written to `app.security_events` (schema `app`, not readable by the
analyst role). Logging never blocks or breaks a chat.

| Kind | Severity | When |
|---|---|---|
| `blocked_sql` | high | the analyst generated SQL that is not one read-only SELECT |
| `permission_denied` | high | a query tried to read outside `gold` (stopped by the database role) |
| `customer_id_override` | high | the model passed another customer's id to a tool (ignored) |
| `prompt_injection` | high | "ignore your instructions", "show the system prompt"... |
| `other_customer_order` | medium | a customer asked for an order that exists on another account |
| `sensitive_question` | medium | a customer asked about sales, profit, salaries, suppliers... |
| `login_required` | low | a guest asked for orders / purchase history |

The keyword lists only decide what is *logged*; the refusal itself comes from the rules and from the
fact that no tool can return such data.

### Search by photo (`image_search.py`)
The browser resizes the photo (max 1024 px JPEG, which also removes EXIF / location). A vision model
describes the main garment as a short phrase ("men's white cotton crew-neck t-shirt"), or says it is
not clothing. The same semantic product search then runs. Photos are not stored. Only PNG / JPG / WEBP
data URLs under a size limit are accepted.

### Product photos (optional)
`ai/fetch_product_images.py` reads each product's public page as JSON (the store runs on Shopify:
page URL + `.json`) and stores only the first image **URL** in `ai.product_images`. It sends one polite
request at a time and only for catalog products.

---

## Business Analyst (Text-to-SQL)

### One question
1. **Schema RAG:** embed the question, take the 8 closest gold tables from `ai.schema_docs`, and add the
   core tables (dim_date, dim_branch, dim_product, fact_orders). Their comments and columns go into the prompt.
2. **Business rules** in the prompt make answers match the dashboards: which column is "sales", where
   profit comes from, use complete months, and so on.
3. The model writes one SQL query and calls `run_sql`. If it fails, the model sees the error and fixes it.
   A multi-part question should be one query with CTEs (at most 3 queries in total).
4. The model answers: direct answer, short insights, assumptions.
5. The frontend shows the answer, an **automatic chart** (line for dates, bar otherwise, with a table view),
   the **SQL** for verification, and product photos when the result has `product_id`.
6. If the step limit is reached, the model must answer with the results it already has instead of giving up.

### Five layers of protection
1. Only a single `SELECT` / `WITH` statement is accepted.
2. Forbidden keywords (INSERT, UPDATE, DELETE, DROP, ALTER, GRANT, COPY, pg_sleep, ...) are rejected.
3. `SET TRANSACTION READ ONLY`.
4. `SET LOCAL statement_timeout = '15s'` and at most 200 rows returned.
5. `SET LOCAL ROLE cottonil_reader`: the database itself only allows SELECT on `gold`. Silver, `ai` and
   `app` (chat memory) are not readable.

Protection is enforced by the **database**, not only by the prompt.

### Data privacy note
The analyst sends a sample of the query result (up to 60 rows) to the LLM provider to write the answer.
For confidential data, point `.env` to a local model (any OpenAI-compatible server such as Ollama);
no code change is needed.

---

## AI tools for management

### Explain this page (`chat/explain.py`, `POST /api/apps/{id}/explain`)
The page is run with the current filters, then shrunk to a short digest: every KPI with its change, and
for every chart only first / last / highest / lowest point (trends) or the top rows (rankings). The model
writes a headline, 3-5 points and 1-2 things to watch, in **English and Egyptian Arabic** (JSON). It never
sees raw tables, so it cannot invent other numbers. Results are cached per page and filters.

### Download PDF (every dashboard and product page)
The browser's print-to-PDF with a print layout: logo, title in both languages, the filters and date, the
AI summary in English **and** Arabic, and every KPI / chart title in both languages. The browser renders
the Arabic text, so it is always joined and right-to-left (server PDF libraries often break Arabic).

### Insight Scout (`chat/insight_scout.py`, `GET /api/insights`)
Nine fixed, read-only SQL probes compare the latest complete months with the past: category units, branch
real sales, channel mix, category margin, products with high returns, discount depth, at-risk customers,
stock-out risk and next month's forecast. Growth uses **units or real (2026-price) values**, never nominal
EGP. The model turns the findings into 4-7 cards (EN + AR) with a next step and a follow-up question that
opens the Business Analyst. Without AI quota, simple bilingual template cards are built from the numbers.
Cached for 6 hours ("Refresh" re-runs).

### Report Agent (`chat/report_agent.py`, `POST /api/analyst/report`)
An agent: it plans the angles of a topic, runs 3-6 queries through the **same safe `run_sql`** as the
analyst (read-only role, gold only, timeout, row limit), then writes the report as JSON in English and
Egyptian Arabic: summary, sections, recommendations, notes. Each section points to the number of the query
whose result it shows, so **chart data comes from the database, not from the model's text**. Reports are
saved in `app.analyst_reports`; `/print/report/<id>` is the bilingual PDF page.

### Talk to your data (analyst page)
Hands-free mode: the mic listens, the question is sent when the manager stops talking, the answer is read
aloud, then the mic listens again. Silence ends the mode. Browser Web Speech API (Chrome / Edge).

---

## Memory (`memory.py`)

| Kind | How |
|---|---|
| Conversation | Every message is saved in `app.chat_messages`, so a page refresh restores the chat (cards, charts, SQL) |
| Long-term memory | "New chat" asks the model to merge the finished chat into at most 8 bullet points of durable facts (sizes, preferences, topics, preferred answer style). The bullets are stored in `app.chat_memory` and added to the system prompt of every new chat |
| Forget | Deletes the long-term memory |

- **Owner** (built on the server): `cust:<id>` for a logged-in customer, `guest:<browser id>` for guests,
  `analyst:<browser id>` for the analyst. Session ids are validated (UUID) and must belong to the owner.
- Memory never stores passwords, phone numbers or payment details. Summarising happens once per "New chat"
  to save quota, and a failure never blocks the new chat.

## Voice
Browser Web Speech API: microphone -> text in the input box (Egyptian Arabic or English, best in
Chrome / Edge), and read-aloud of replies (`speechSynthesis`). Free, with no server or API key.
