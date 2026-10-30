# Data model (gold)

A **star schema**: fact tables (events with numbers) in the middle, joined to small dimension tables
(who / what / where / when) by their keys. Marts are pre-aggregated tables for fast dashboards. Every
table has a `COMMENT`, which the AI Analyst also reads.

## Conventions

| Pattern | Meaning |
|---|---|
| `*_egp` | Money in EGP, **before VAT** |
| `net_sales_egp` | gross − discount (before VAT, before returns) |
| `*_after_returns_egp` | after subtracting the **capped** refunds (D1) |
| `real_*` | inflation-adjusted to 2026 catalog prices (F1): value ÷ price_index |
| `month_start` | first day of the month; joins to `dim_date` and the price index |
| `customer_key = 'GUEST'` | order without a registered customer |

---

## Dimensions

| Table | Grain | Key columns / notes |
|---|---|---|
| `dim_date` | one row per day of the data period | year, quarter, month, month_name, day_of_week (1 = Mon), `is_weekend` (Fri and Sat in Egypt), season, `retail_event` (Ramadan, Eid al-Fitr, Eid al-Adha from a date list; September = Back to school), `is_complete_month`, `has_data`, `price_index` |
| `dim_branch` | one row per branch / reseller point | `branch_display_name` (D3), governorate, city, `retail_location_type`, `effective_opening_date` (D2), reported date, conflict flag, `employees` |
| `dim_product` | one row per **SKU** (product + size + colour) | product_id, Arabic name, category, audience, size, `size_group` (numeric size = Kids (age), Free = Free size, else Adult), colour, list price × size multiplier, source URL |
| `dim_customer` | one row per registered customer + one `GUEST` row | segment (Retail / B2B reseller), governorate, joined date, age band, is_guest. The GUEST row is the "unknown member" technique, so guest orders never drop out of joins |
| `dim_location` | branches + warehouses | location_type Branch / Warehouse (stock and expenses can be at either) |
| `dim_warehouse` | one row per warehouse | kind, governorate, `capacity_units` |
| `dim_supplier` | one row per supplier | material type, city / country, payment terms |

**`is_complete_month`:** a month is complete when it starts after the month of (first data day − 1)
and ends on or before the last data day. If the data started on the 1st of a month, that first month
counts as complete.

---

## Facts

### `fact_sales_line` (main fact) — one row per order line
Built from order items + order (channel, customer) + the line's return (if any) + the price index.

| Column | Formula |
|---|---|
| `cogs_egp` | quantity × unit cost |
| `gross_margin_egp` | source margin (net − cogs) |
| `returned_units`, `refund_egp`, `returned_cogs_egp` | from the return, using the capped refund |
| `net_sales_after_returns_egp` | net_sales − capped refund |
| `margin_after_returns_egp` | margin − (capped refund − returned cost) |
| `real_net_sales_egp` | net_sales_after_returns ÷ price_index |

**Why add back the returned cost?** The returned item goes back to stock, so its cost is not lost.
*Example:* 2 units at 200 = 400, cost 100 each, so margin 200. One unit is returned: refund 200,
returned cost 100. Margin after returns = 200 − (200 − 100) = 100, which is exactly the margin of the one
unit kept (200 − 100).

### Other facts

| Table | Grain | Important columns |
|---|---|---|
| `fact_orders` | one row per order | channel, payment, totals, `return_level`, `net_sales_after_returns_egp`; cogs / margin / real summed from `fact_sales_line` (so both tables agree); delivery columns for e-commerce orders (LEFT JOIN) |
| `fact_returns` | one row per return | `days_to_return` = return date − order date; reported **and** capped refund + flag; reason; refund method |
| `fact_inventory_monthly` | month × location × category | closing units, closing value, `real_closing_stock_value_egp`, source stock-out risk score |
| `fact_transfers` | one row per transfer line | `transport_cost_allocated_egp` = transfer cost × line units ÷ transfer units (window function; the lines add up to the transfer cost) |
| `fact_purchases` | one row per PO line | `lead_time_days` = delivery date − PO date; supplier, warehouse, payment terms |
| `fact_imports` | one row per import shipment (USD) | `landed_cost_overhead_pct` = (freight + duty) ÷ customs value |
| `fact_expenses` | one row per expense | `branch_id` / `warehouse_id` filled from the cost-center type |
| `fact_payroll` | employee × month | `gross_pay_egp` = base + overtime + bonus (labour cost for the company) |
| `fact_marketing` | one row per campaign | CTR = clicks ÷ impressions; conversion = orders ÷ clicks; cost per click / per attributed order; budget utilisation |

Every division uses `NULLIF(x, 0)`, so a zero denominator gives NULL instead of an error.

---

## Marts

| Table | Grain | Used by |
|---|---|---|
| `mart_sales_daily` | day × branch × channel: orders, units, net units, sales, refunds, margin, real sales, discount | Sales trends, seasonality, the forecast model, P&L |
| `mart_sku_monthly` | month × SKU | Product popularity for the chatbot index |
| `mart_branch_pnl_monthly` | month × branch | Branch P&L (see below) |
| `mart_customer_rfm` | one row per registered customer | Customer segments, value, inactivity, demo logins |

### `mart_branch_pnl_monthly` — the profit of every branch
```
operating_profit = gross margin after returns − operating expenses − payroll − transfer transport cost
```
- **Months:** the union of all months that have sales **or** costs, so no expense is lost.
- **CROSS JOIN** with all branches, so every branch has a row every month (missing values = 0).

### `mart_customer_rfm`
- `recency_days` = last data date − customer's last order. Also: frequency (orders), monetary
  (sales after returns), real monetary, AOV, first and last order, active span.
- **Scores:** `NTILE(5)` splits customers into 5 equal groups per measure (1 = worst, 5 = best).
  Recency is ordered descending, so the most recent buyers get 5.
- **Segments:**

| Rule | Segment |
|---|---|
| no orders | Never purchased |
| R ≥ 4 and F ≥ 4 | Champions |
| R ≥ 3 and F ≥ 3 | Loyal |
| R ≥ 4 and F ≤ 2 | New / Promising |
| R ≤ 2 and F ≥ 3 | At risk |
| R ≤ 2 and F ≤ 2 | Hibernating |
| otherwise | Needs attention |

---

## ML and AI tables

| Table | Content |
|---|---|
| `gold.ml_forecast_monthly` | month × category (+ TOTAL): actual units, forecast, 80% interval, `is_forecast`, method |
| `gold.ml_model_metrics` | backtest metrics of the forecast vs the baseline |
| `ai.product_embeddings` | one row per product: description text + embedding vector |
| `ai.kb_chunks` | store-policy knowledge base split by heading + embeddings |
| `ai.schema_docs` | one description per gold table + embedding (schema RAG) |
| `ai.product_images` | product id -> image URL (optional) |
| `app.chat_sessions`, `app.chat_messages`, `app.chat_memory` | chat history and long-term memory |
