# Data pipeline

Each stage below gives the input, the output, and what the stage is for.

---

## 1. Profiling — `etl/profile_data.py`
- **Input:** the CSV files in `data/`.
- **Output:** `reports/profile_*`. For every file and column: type guess, nulls, distinct values,
  min / max, duplicates, spaces, numbers stored as text, date formats.
- **Why:** know the data before writing a single transformation, for example which columns use `MM/DD/YYYY` dates.

## 2. Bronze — `etl/load_bronze.py`
- **Input:** CSV files.
- **Output:** one `bronze.<table>` per file. Every column is TEXT, column names are cleaned to
  snake_case, and `_source_file` and `_loaded_at` are added. Loaded with PostgreSQL `COPY` (fast for millions of rows).
- **Why:** an exact, untouched copy. Nothing is interpreted yet, so nothing can be lost.

## 3. Silver phase 1 — `sql/build_silver.sql`
- **Input:** bronze.
- **Output:** `silver.<table>` with the **same number of rows** (checked by `etl/build_silver.py`).
- **What happens to every table:**
  1. Correct types: TEXT -> DATE / NUMERIC / INTEGER / BIGINT.
  2. One date type: both `YYYY-MM-DD` and `MM/DD/YYYY` are converted.
  3. Clean text: trim, collapse repeated spaces, empty string -> NULL.
  4. Primary keys, which also prove that ids are unique, plus indexes on join columns.
  5. A few derived columns.
- **Helper functions** (schema `etl`): `clean_text`, `to_num` (removes thousand separators), `to_int`,
  `to_bigint`, `to_date_iso`, `to_date_mdy`, `month_start` (`YYYY-MM` -> first day of the month).
- **Derived columns:**

| Table | Column | Meaning |
|---|---|---|
| sales_orders | `is_guest` | Order without a customer id = walk-in buyer (not an error) |
| delivery_shipments | `delivery_days` | delivery_date − ship_date |
| import_shipments | `landed_cost_usd` | customs value + freight + duty (NULL treated as 0) |
| operating_expenses | `cost_center_type` | The mixed id column split into branch / warehouse / department, so branch P&L only gets branch costs |
| monthly_stock | composite key | (month, location, category) |

- Money is kept as unrounded NUMERIC, so consistency checks are exact.

## 4. Quality checks — `sql/quality_checks.sql` -> `etl/check_quality.py`
- **Input:** silver.
- **Output:** `audit.data_quality_checks` and `reports/quality_report.md`.
- **Check categories:**

| Category | Examples |
|---|---|
| foreign_key | every order line points to an existing order, SKU, branch |
| consistency | order totals = sum of their lines; gross − discount = net; tax = 14% of net; refund ≤ value of returned units |
| validity | no negative quantities or prices, dates inside the data period |
| business | no sales before a branch opened; order status consistent with returns |
| coverage | which channels have shipments, customers without orders |
| distribution / date_range | uniform categorical columns, first and last date of each table |

- Each check has a severity (error / warning / info) and records failed rows and total rows.

## 5. Investigations — `sql/investigations.sql` -> `etl/investigate.py`
- **Input:** silver plus the failed checks.
- **Output:** `reports/investigation_report.md` (ids, counts, ratios and dates only).
- **Why:** a failed check says *what* is wrong. Before cleaning we must know *why*. Each query tests one hypothesis:

| # | Question | Hypothesis tested | Conclusion |
|---|---|---|---|
| 1 | Refunds larger than the value of the returned units | Refund includes 14% VAT (ratio would be ~1.14) | Ratios are spread around ~1.0 and do not cluster at 1.14. Same for every reason; almost all are full-line returns. So it is generator noise -> **D1** |
| 2 | Sales before the branch opening date | Online orders assigned to branches / opening date wrong | Every branch sells and receives stock from the first data day, in every channel. So the opening date is wrong -> **D2** |
| 3 | Two branches with the same name | Duplicate record | Different addresses, own employees and orders, so two real outlets -> **D3** |
| 4 | Order status vs returns table | Status reflects returns | Status does not match the returns table -> **D4** |
| 5 | Selling price ≠ catalog price × multiplier | Inflation over time (catalog = 2026 prices) | The price ratio rises every year -> **F1** |
| 6 | Channel vs customer segment | Wholesale orders come from B2B customers | Channel and segment are independent -> **F8** |
| 7 | Catalog vs public reference catalog | Products are real | All sold products exist in the public catalog -> **F2** |
| 8 | Partial months | First and last month incomplete | Confirmed -> **F7** |
| 9 | Customers without orders | Recent sign-ups | Mostly recent -> **F6** |

## 6. Silver phase 2 — `sql/silver_fixes.sql`
**Rule: no row is deleted.** The original value is kept, and corrected columns and flags are added next to it.

| ID | Issue | Decision | Columns added |
|---|---|---|---|
| D1 | Refund larger than the value of the returned units | Cap the refund at the net value of the returned units; KPIs use the capped value | `sales_returns.returned_value_egp`, `returned_cost_egp`, `refund_capped_egp`, `refund_exceeds_value` |
| D2 | Sales and transfers before the reported opening date | Effective opening = earliest of reported date, first sale, first transfer | `branches.first_sale_date`, `first_transfer_date`, `effective_opening_date`, `opening_date_conflict` |
| D3 | Two branches share a name | Unique display name = name + id | `branches.branch_display_name` |
| D4 | Order status does not match returns | Derive the return status from the returns table | `sales_orders.sold_units`, `returned_units`, `refund_egp`, `has_return`, `return_level` (none / partial / full) |
| F1 | Prices rise every year vs today's catalog | Monthly price index = average(selling price ÷ 2026 catalog price) | new table `silver.price_index_monthly`; later `real_value = value ÷ price_index` |

Unreliable source columns get a `COMMENT ON COLUMN` saying which column to use instead.

**Worked examples**
- *D1:* a line of 3 units worth 300; 1 unit returned, so returned value = 100. A reported refund of
  125 becomes a capped refund of 100, flag = true.
- *F1:* an item whose 2026 catalog price is 350 sold for 50 in an early month, so the index is 0.14.
  Sales of 1M that month are worth 1M ÷ 0.14 ≈ 7.1M in 2026 prices.

## 7. Findings (not errors, but they change how we analyse)

| ID | Finding | How it is used |
|---|---|---|
| F1 | Inflation is built into prices | Real (2026-price) values in Sales, Pricing and Inventory; the forecast uses units |
| F2 | All sold products are real catalog products | Product names, prices and links are real; transactions are generated |
| F3 | VAT is exactly 14% | Revenue KPIs use net before tax |
| F4 | No cancelled orders; partial and full returns exist | Net revenue = net sales − capped refunds |
| F5 | Shipments exist only for e-commerce orders | Delivery KPIs cover e-commerce only |
| F6 | Some customers never ordered (mostly recent sign-ups) | Shown as the "Never purchased" segment |
| F7 | First and last months are incomplete | `dim_date.is_complete_month`; monthly charts use complete months |
| F8 | Channel and customer segment are independent | Wholesale analysis uses `sales_channel` |
| F9 | Several categorical columns are almost perfectly uniform | Not presented as insights (see data_limitations.md) |

## 8. Gold — `sql/build_gold.sql` -> `etl/build_gold.py`
- **Input:** silver after the fixes.
- **Output:** star schema, marts and reconciliation (see data_model.md).

## 9. Reconciliation (last gold step)
Gold must give exactly the same totals as silver. The results are written to `audit.data_quality_checks`
(category `reconciliation`), and `build_gold.py` prints PASS / FAIL:

1. fact_sales_line rows = silver order-item rows
2. fact_orders rows = silver order rows
3. total net sales in gold = silver orders' net before tax
4. total refunds in gold = silver capped refunds
5. mart_sales_daily net sales = fact_sales_line
6. P&L gross margin = fact_sales_line margin after returns
7. P&L opex = all branch expenses
8. every order date exists in dim_date

The tolerance is less than 1 EGP (rounding of fractions).

## Logging
Every step writes to `audit.etl_log`: run id, step, rows before and after, duration and status. A
failed step stops the run with a clear message.
