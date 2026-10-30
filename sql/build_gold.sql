-- =============================================================================
-- build_gold.sql  -  silver (clean tables)  ->  gold (star schema + marts)
-- -----------------------------------------------------------------------------
-- Gold is what the dashboard, the API, the ML models and the AI assistant read.
--
--   dim_*   DIMENSIONS : the "who / what / where / when" (branch, product, date...)
--   fact_*  FACTS      : the events with numbers (sales lines, orders, expenses...)
--   mart_*  MARTS      : pre-aggregated tables for the heaviest dashboards
--
-- Star schema = one fact table in the middle, joined to small dimension tables
-- by their keys. It is the standard model for BI: simple joins, fast queries.
--
-- Conventions used everywhere:
--   *_egp            money in EGP, before VAT
--   net_sales_egp    gross - discount (before VAT, before returns)
--   *_after_returns  after subtracting capped refunds (decision D1)
--   real_*           inflation-adjusted to 2026 catalog prices (finding F1)
--   month_start      first day of the month, used to join to dim_date / price index
--
-- Executed step by step by etl/build_gold.py
-- =============================================================================


-- @step: setup
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS audit;
-- The reconciliation step writes here; create it in case check_quality.py has not run yet
CREATE TABLE IF NOT EXISTS audit.data_quality_checks (
    check_id    SERIAL PRIMARY KEY,
    run_at      TIMESTAMPTZ DEFAULT now(),
    category    TEXT,
    table_name  TEXT,
    check_name  TEXT,
    severity    TEXT,
    failed_rows BIGINT,
    total_rows  BIGINT,
    failed_pct  NUMERIC(7, 3),
    details     TEXT
);


-- =============================================================================
-- DIMENSIONS
-- =============================================================================

-- @step: dim_date
-- One row per calendar day covering the whole data period.
DROP TABLE IF EXISTS gold.dim_date;
CREATE TABLE gold.dim_date AS
WITH bounds AS (
    SELECT MIN(order_date) AS first_day, MAX(order_date) AS last_day FROM silver.sales_orders
),
-- Approximate Egyptian retail events (Ramadan / Eid dates can differ by +-1 day)
events (event_name, start_date, end_date) AS (
    VALUES
    ('Ramadan', DATE '2019-05-06', DATE '2019-06-03'), ('Eid al-Fitr', DATE '2019-06-04', DATE '2019-06-06'),
    ('Ramadan', DATE '2020-04-24', DATE '2020-05-23'), ('Eid al-Fitr', DATE '2020-05-24', DATE '2020-05-26'),
    ('Ramadan', DATE '2021-04-13', DATE '2021-05-12'), ('Eid al-Fitr', DATE '2021-05-13', DATE '2021-05-15'),
    ('Ramadan', DATE '2022-04-02', DATE '2022-05-01'), ('Eid al-Fitr', DATE '2022-05-02', DATE '2022-05-04'),
    ('Ramadan', DATE '2023-03-23', DATE '2023-04-20'), ('Eid al-Fitr', DATE '2023-04-21', DATE '2023-04-23'),
    ('Ramadan', DATE '2024-03-11', DATE '2024-04-09'), ('Eid al-Fitr', DATE '2024-04-10', DATE '2024-04-12'),
    ('Ramadan', DATE '2025-03-01', DATE '2025-03-29'), ('Eid al-Fitr', DATE '2025-03-30', DATE '2025-04-01'),
    ('Ramadan', DATE '2026-02-18', DATE '2026-03-19'), ('Eid al-Fitr', DATE '2026-03-20', DATE '2026-03-22'),
    ('Eid al-Adha', DATE '2019-08-11', DATE '2019-08-14'), ('Eid al-Adha', DATE '2020-07-31', DATE '2020-08-03'),
    ('Eid al-Adha', DATE '2021-07-20', DATE '2021-07-23'), ('Eid al-Adha', DATE '2022-07-09', DATE '2022-07-12'),
    ('Eid al-Adha', DATE '2023-06-28', DATE '2023-07-01'), ('Eid al-Adha', DATE '2024-06-16', DATE '2024-06-19'),
    ('Eid al-Adha', DATE '2025-06-06', DATE '2025-06-09'), ('Eid al-Adha', DATE '2026-05-27', DATE '2026-05-30')
),
days AS (
    SELECT d::DATE AS date_key
    FROM bounds,
         generate_series(date_trunc('month', first_day),
                         date_trunc('month', last_day) + INTERVAL '1 month - 1 day',
                         INTERVAL '1 day') AS d
)
SELECT
    d.date_key,
    EXTRACT(YEAR    FROM d.date_key)::INT              AS year,
    EXTRACT(QUARTER FROM d.date_key)::INT              AS quarter,
    EXTRACT(MONTH   FROM d.date_key)::INT              AS month,
    to_char(d.date_key, 'Mon')                         AS month_name,
    to_char(d.date_key, 'YYYY-MM')                     AS year_month,
    date_trunc('month', d.date_key)::DATE              AS month_start,
    EXTRACT(ISODOW  FROM d.date_key)::INT              AS day_of_week,     -- 1 = Monday ... 7 = Sunday
    to_char(d.date_key, 'Dy')                          AS day_name,
    EXTRACT(ISODOW  FROM d.date_key) IN (5, 6)         AS is_weekend,      -- Friday & Saturday in Egypt
    CASE WHEN EXTRACT(MONTH FROM d.date_key) IN (12, 1, 2) THEN 'Winter'
         WHEN EXTRACT(MONTH FROM d.date_key) IN (3, 4, 5)  THEN 'Spring'
         WHEN EXTRACT(MONTH FROM d.date_key) IN (6, 7, 8)  THEN 'Summer'
         ELSE 'Autumn' END                             AS season,
    COALESCE(e.event_name,
             CASE WHEN EXTRACT(MONTH FROM d.date_key) = 9 THEN 'Back to school' END) AS retail_event,
    -- Finding F7: first and last months of the data are incomplete
    (date_trunc('month', d.date_key) >  date_trunc('month', b.first_day - 1)
     AND date_trunc('month', d.date_key) + INTERVAL '1 month - 1 day' <= b.last_day) AS is_complete_month,
    (d.date_key BETWEEN b.first_day AND b.last_day)    AS has_data,
    pi.price_index
FROM days d
CROSS JOIN bounds b
LEFT JOIN events e ON d.date_key BETWEEN e.start_date AND e.end_date
LEFT JOIN silver.price_index_monthly pi ON pi.month_start = date_trunc('month', d.date_key);
ALTER TABLE gold.dim_date ADD PRIMARY KEY (date_key);
COMMENT ON TABLE gold.dim_date IS
    'Calendar: one row per day. is_complete_month=false for the partial first/last month. retail_event = Ramadan / Eid / Back to school (approximate dates). price_index: 1.0 = 2026 catalog prices.';

-- @step: dim_branch
DROP TABLE IF EXISTS gold.dim_branch;
CREATE TABLE gold.dim_branch AS
SELECT
    b.branch_id,
    b.branch_display_name,
    b.branch_name_ar,
    b.governorate_ar,
    b.city_ar,
    b.retail_location_type,
    b.effective_opening_date,
    b.opening_date            AS opening_date_reported,
    b.opening_date_conflict,
    (SELECT COUNT(*) FROM silver.employees e WHERE e.branch_id = b.branch_id) AS employees
FROM silver.branches b;
ALTER TABLE gold.dim_branch ADD PRIMARY KEY (branch_id);
COMMENT ON TABLE gold.dim_branch IS
    'Branches and reseller points of sale. Use branch_display_name for labels and effective_opening_date (reported opening date is unreliable).';

-- @step: dim_product
-- Grain: one row per SKU (product + size + colour)
DROP TABLE IF EXISTS gold.dim_product;
CREATE TABLE gold.dim_product AS
SELECT
    s.sku_id,
    s.product_id,
    p.product_name_ar,
    p.category_en                              AS category,
    p.audience,
    s.size,
    CASE WHEN s.size ~ '^[0-9]+$' THEN 'Kids (age)'          -- sizes 2,3,4... = kids ages
         WHEN s.size = 'Free'     THEN 'Free size'
         ELSE 'Adult' END                      AS size_group,
    s.color_ar,
    p.listed_price_egp,
    s.price_multiplier,
    p.listed_price_egp * s.price_multiplier    AS sku_list_price_egp,
    p.source_url
FROM silver.sku_variants s
JOIN silver.products_catalog p ON p.product_id = s.product_id;
ALTER TABLE gold.dim_product ADD PRIMARY KEY (sku_id);
CREATE INDEX ON gold.dim_product (product_id);
COMMENT ON TABLE gold.dim_product IS
    'One row per SKU (product + size + colour). Products, names and list prices are real (public Cottonil catalog, 2026 prices).';

-- @step: dim_customer
-- Guest orders get the special key 'GUEST' so every order joins to a customer row
-- (standard "unknown member" technique - avoids losing rows in joins).
DROP TABLE IF EXISTS gold.dim_customer;
CREATE TABLE gold.dim_customer AS
SELECT
    customer_id       AS customer_key,
    customer_id,
    customer_segment,
    governorate_ar,
    joined_date,
    age_band,
    FALSE             AS is_guest
FROM silver.customers
UNION ALL
SELECT 'GUEST', NULL, 'Guest', NULL, NULL, NULL, TRUE;
ALTER TABLE gold.dim_customer ADD PRIMARY KEY (customer_key);
COMMENT ON TABLE gold.dim_customer IS
    'Registered customers plus one GUEST row for walk-in orders without a customer id.';

-- @step: dim_location
-- Branches and warehouses in one list (stock and expenses can be at either)
DROP TABLE IF EXISTS gold.dim_location;
CREATE TABLE gold.dim_location AS
SELECT branch_id AS location_id, branch_display_name AS location_name, 'Branch' AS location_type,
       retail_location_type AS location_subtype, governorate_ar
FROM silver.branches
UNION ALL
SELECT warehouse_id, warehouse_label, 'Warehouse', warehouse_kind, governorate_ar
FROM silver.warehouses;
ALTER TABLE gold.dim_location ADD PRIMARY KEY (location_id);
COMMENT ON TABLE gold.dim_location IS 'All stock / cost locations: 80 branches + 12 warehouses.';

-- @step: dim_warehouse
DROP TABLE IF EXISTS gold.dim_warehouse;
CREATE TABLE gold.dim_warehouse AS
SELECT warehouse_id, warehouse_label, governorate_ar, warehouse_kind, capacity_units
FROM silver.warehouses;
ALTER TABLE gold.dim_warehouse ADD PRIMARY KEY (warehouse_id);

-- @step: dim_supplier
DROP TABLE IF EXISTS gold.dim_supplier;
CREATE TABLE gold.dim_supplier AS
SELECT supplier_id, supplier_name_ar, material_type, city_country, payment_terms_days
FROM silver.suppliers;
ALTER TABLE gold.dim_supplier ADD PRIMARY KEY (supplier_id);


-- =============================================================================
-- FACTS
-- =============================================================================

-- @step: fact_sales_line
-- Grain: one row per order line (1.1M). The main fact table of the project.
-- Returns are attached to the line they belong to (max one return per line).
DROP TABLE IF EXISTS gold.fact_sales_line;
CREATE TABLE gold.fact_sales_line AS
SELECT
    i.sales_line_id,
    i.sales_order_id,
    i.order_date,
    date_trunc('month', i.order_date)::DATE                        AS month_start,
    i.branch_id,
    COALESCE(o.customer_id, 'GUEST')                               AS customer_key,
    i.sku_id,
    i.product_id,
    o.sales_channel,
    i.quantity,
    i.unit_price_egp,
    i.gross_line_egp                                               AS gross_egp,
    i.discount_line_egp                                            AS discount_egp,
    i.net_line_egp                                                 AS net_sales_egp,
    i.quantity * i.unit_cost_egp                                   AS cogs_egp,
    i.margin_egp                                                   AS gross_margin_egp,
    COALESCE(r.return_quantity, 0)                                 AS returned_units,
    COALESCE(r.refund_capped_egp, 0)                               AS refund_egp,
    COALESCE(r.returned_cost_egp, 0)                               AS returned_cogs_egp,
    i.net_line_egp - COALESCE(r.refund_capped_egp, 0)              AS net_sales_after_returns_egp,
    -- a return gives back the refund but the item comes back to stock (cost recovered)
    i.margin_egp - (COALESCE(r.refund_capped_egp, 0) - COALESCE(r.returned_cost_egp, 0))
                                                                   AS margin_after_returns_egp,
    (i.net_line_egp - COALESCE(r.refund_capped_egp, 0)) / NULLIF(pi.price_index, 0)
                                                                   AS real_net_sales_egp
FROM silver.sales_order_items i
JOIN silver.sales_orders o            ON o.sales_order_id = i.sales_order_id
LEFT JOIN silver.sales_returns r      ON r.sales_line_id  = i.sales_line_id
LEFT JOIN silver.price_index_monthly pi ON pi.month_start = date_trunc('month', i.order_date);
ALTER TABLE gold.fact_sales_line ADD PRIMARY KEY (sales_line_id);
CREATE INDEX ON gold.fact_sales_line (order_date);
CREATE INDEX ON gold.fact_sales_line (month_start);
CREATE INDEX ON gold.fact_sales_line (branch_id);
CREATE INDEX ON gold.fact_sales_line (sku_id);
CREATE INDEX ON gold.fact_sales_line (customer_key);
CREATE INDEX ON gold.fact_sales_line (sales_order_id);
COMMENT ON TABLE gold.fact_sales_line IS
    'One row per sales order line. Money in EGP before VAT. net_sales_after_returns_egp and margin_after_returns_egp subtract capped refunds. real_net_sales_egp = inflation-adjusted to 2026 prices. Join: branch_id->dim_branch, sku_id->dim_product, customer_key->dim_customer, order_date->dim_date.';

-- @step: fact_orders
-- Grain: one row per order (540K), with delivery info for e-commerce orders
DROP TABLE IF EXISTS gold.fact_orders;
CREATE TABLE gold.fact_orders AS
SELECT
    o.sales_order_id,
    o.order_date,
    date_trunc('month', o.order_date)::DATE           AS month_start,
    o.branch_id,
    COALESCE(o.customer_id, 'GUEST')                  AS customer_key,
    o.is_guest,
    o.sales_channel,
    o.payment_method,
    o.items_count,
    o.sold_units,
    o.gross_egp,
    o.discount_egp,
    o.net_before_tax_egp                              AS net_sales_egp,
    o.tax_egp,
    o.paid_total_egp,
    o.returned_units,
    o.refund_egp,
    o.has_return,
    o.return_level,
    o.net_before_tax_egp - o.refund_egp               AS net_sales_after_returns_egp,
    l.cogs_egp,
    l.margin_after_returns_egp,
    l.real_net_sales_egp,
    d.shipment_id,
    d.carrier,
    d.ship_date,
    d.delivery_date,
    d.delivery_days,
    d.shipping_fee_egp,
    d.fulfillment_status,
    d.ship_to_governorate
FROM silver.sales_orders o
LEFT JOIN (
    SELECT sales_order_id,
           SUM(cogs_egp)                 AS cogs_egp,
           SUM(margin_after_returns_egp) AS margin_after_returns_egp,
           SUM(real_net_sales_egp)       AS real_net_sales_egp
    FROM gold.fact_sales_line
    GROUP BY sales_order_id
) l ON l.sales_order_id = o.sales_order_id
LEFT JOIN silver.delivery_shipments d ON d.sales_order_id = o.sales_order_id;
ALTER TABLE gold.fact_orders ADD PRIMARY KEY (sales_order_id);
CREATE INDEX ON gold.fact_orders (order_date);
CREATE INDEX ON gold.fact_orders (month_start);
CREATE INDEX ON gold.fact_orders (branch_id);
CREATE INDEX ON gold.fact_orders (customer_key);
COMMENT ON TABLE gold.fact_orders IS
    'One row per order. Use return_level (none/partial/full), not the source status. Delivery columns are filled only for E-commerce orders. customer_key = GUEST for walk-in orders.';

-- @step: fact_returns
DROP TABLE IF EXISTS gold.fact_returns;
CREATE TABLE gold.fact_returns AS
SELECT
    r.return_id,
    r.return_date,
    date_trunc('month', r.return_date)::DATE  AS month_start,
    r.sales_order_id,
    r.sales_line_id,
    i.order_date,
    r.return_date - i.order_date              AS days_to_return,
    i.branch_id,
    o.sales_channel,
    r.sku_id,
    i.product_id,
    r.return_quantity,
    r.returned_value_egp,
    r.refund_amount_egp                       AS refund_reported_egp,
    r.refund_capped_egp                       AS refund_egp,
    r.refund_exceeds_value,
    r.reason,
    r.refund_method
FROM silver.sales_returns r
JOIN silver.sales_order_items i ON i.sales_line_id  = r.sales_line_id
JOIN silver.sales_orders o      ON o.sales_order_id = r.sales_order_id;
ALTER TABLE gold.fact_returns ADD PRIMARY KEY (return_id);
CREATE INDEX ON gold.fact_returns (branch_id);
COMMENT ON TABLE gold.fact_returns IS
    'One row per return. refund_egp is capped at the value of the returned units. Reasons are uniformly distributed (generated) - avoid ranking them as an insight.';

-- @step: fact_inventory_monthly
DROP TABLE IF EXISTS gold.fact_inventory_monthly;
CREATE TABLE gold.fact_inventory_monthly AS
SELECT
    m.month_start,
    m.stock_location_id                                   AS location_id,
    m.stock_location_type                                 AS location_type,
    m.product_category                                    AS category,
    m.closing_units,
    m.closing_stock_value_egp,
    m.closing_stock_value_egp / NULLIF(pi.price_index, 0) AS real_closing_stock_value_egp,
    m.stockout_risk_score
FROM silver.monthly_stock m
LEFT JOIN silver.price_index_monthly pi ON pi.month_start = m.month_start;
ALTER TABLE gold.fact_inventory_monthly ADD PRIMARY KEY (month_start, location_id, category);
COMMENT ON TABLE gold.fact_inventory_monthly IS
    'Closing stock per month x location (branch or warehouse) x product category. location_id -> dim_location.';

-- @step: fact_transfers
DROP TABLE IF EXISTS gold.fact_transfers;
CREATE TABLE gold.fact_transfers AS
SELECT
    l.transfer_line_id,
    l.transfer_id,
    t.transfer_date,
    date_trunc('month', t.transfer_date)::DATE  AS month_start,
    t.source_warehouse_id,
    t.destination_branch_id,
    t.transfer_status,
    l.sku_id,
    l.quantity_units,
    -- the transport cost belongs to the whole transfer: split it across lines by quantity
    t.transport_cost_egp * l.quantity_units
        / NULLIF(SUM(l.quantity_units) OVER (PARTITION BY l.transfer_id), 0) AS transport_cost_allocated_egp
FROM silver.inventory_transfer_items l
JOIN silver.inventory_transfers t ON t.transfer_id = l.transfer_id;
ALTER TABLE gold.fact_transfers ADD PRIMARY KEY (transfer_line_id);
CREATE INDEX ON gold.fact_transfers (destination_branch_id);
COMMENT ON TABLE gold.fact_transfers IS
    'Warehouse -> branch stock transfers, one row per transfer line. Transport cost is split across lines by quantity.';

-- @step: fact_purchases
DROP TABLE IF EXISTS gold.fact_purchases;
CREATE TABLE gold.fact_purchases AS
SELECT
    i.po_line_id,
    i.po_id,
    p.po_date,
    date_trunc('month', p.po_date)::DATE  AS month_start,
    p.supplier_id,
    p.receiving_warehouse_id,
    p.po_status,
    p.po_purpose,
    p.payment_terms_days,
    i.sku_id,
    s.product_id,
    i.quantity,
    i.unit_cost_egp,
    i.line_cost_egp,
    i.delivery_date,
    i.delivery_date - p.po_date           AS lead_time_days
FROM silver.purchase_order_items i
JOIN silver.purchase_orders p    ON p.po_id = i.po_id
LEFT JOIN silver.sku_variants s  ON s.sku_id = i.sku_id;
ALTER TABLE gold.fact_purchases ADD PRIMARY KEY (po_line_id);
CREATE INDEX ON gold.fact_purchases (supplier_id);
COMMENT ON TABLE gold.fact_purchases IS
    'Purchase order lines with supplier, warehouse and lead time (delivery_date - po_date). All purchases are in EGP.';

-- @step: fact_imports
DROP TABLE IF EXISTS gold.fact_imports;
CREATE TABLE gold.fact_imports AS
SELECT
    s.import_shipment_id,
    s.shipment_date,
    date_trunc('month', s.shipment_date)::DATE  AS month_start,
    s.import_partner_id,
    p.partner_name,
    p.country,
    p.goods_category,
    p.shipping_terms,
    s.port_name,
    s.container_type,
    s.commodity_class,
    s.customs_value_usd,
    s.freight_usd,
    s.duty_and_tax_usd,
    s.landed_cost_usd,
    (s.freight_usd + s.duty_and_tax_usd) / NULLIF(s.customs_value_usd, 0) AS landed_cost_overhead_pct,
    s.destination_warehouse_id
FROM silver.import_shipments s
JOIN silver.import_partners p ON p.import_partner_id = s.import_partner_id;
ALTER TABLE gold.fact_imports ADD PRIMARY KEY (import_shipment_id);
COMMENT ON TABLE gold.fact_imports IS
    'Import shipments in USD. landed_cost_usd = customs value + freight + duty; landed_cost_overhead_pct = (freight + duty) / customs value.';

-- @step: fact_expenses
DROP TABLE IF EXISTS gold.fact_expenses;
CREATE TABLE gold.fact_expenses AS
SELECT
    expense_id,
    expense_date,
    date_trunc('month', expense_date)::DATE                       AS month_start,
    cost_center_id,
    cost_center_type,
    CASE WHEN cost_center_type = 'branch'    THEN cost_center_id END AS branch_id,
    CASE WHEN cost_center_type = 'warehouse' THEN cost_center_id END AS warehouse_id,
    expense_category,
    amount_egp,
    payment_method,
    vendor_name
FROM silver.operating_expenses;
ALTER TABLE gold.fact_expenses ADD PRIMARY KEY (expense_id);
CREATE INDEX ON gold.fact_expenses (branch_id);
COMMENT ON TABLE gold.fact_expenses IS
    'Operating expenses per branch or warehouse. Expense categories are uniformly distributed (generated).';

-- @step: fact_payroll
DROP TABLE IF EXISTS gold.fact_payroll;
CREATE TABLE gold.fact_payroll AS
SELECT
    p.payroll_id,
    p.pay_month                                        AS month_start,
    p.employee_id,
    e.branch_id,
    e.position_en,
    p.base_salary_egp,
    p.overtime_egp,
    p.bonus_egp,
    p.deductions_egp,
    p.net_paid_egp,
    p.base_salary_egp + p.overtime_egp + p.bonus_egp   AS gross_pay_egp     -- labour cost for the company
FROM silver.payroll p
JOIN silver.employees e ON e.employee_id = p.employee_id;
ALTER TABLE gold.fact_payroll ADD PRIMARY KEY (payroll_id);
CREATE INDEX ON gold.fact_payroll (branch_id);
COMMENT ON TABLE gold.fact_payroll IS
    'Monthly payroll per employee. gross_pay_egp (base + overtime + bonus) is used as labour cost.';

-- @step: fact_marketing
DROP TABLE IF EXISTS gold.fact_marketing;
CREATE TABLE gold.fact_marketing AS
SELECT
    campaign_id,
    start_date,
    end_date,
    date_trunc('month', start_date)::DATE                 AS month_start,
    end_date - start_date + 1                             AS duration_days,
    channel,
    target_audience,
    governorate_ar,
    budget_egp,
    spend_egp,
    spend_egp / NULLIF(budget_egp, 0)                     AS budget_utilization,
    impressions,
    clicks,
    orders_attributed,
    clicks::NUMERIC / NULLIF(impressions, 0)              AS ctr,
    orders_attributed::NUMERIC / NULLIF(clicks, 0)        AS conversion_rate,
    spend_egp / NULLIF(clicks, 0)                         AS cost_per_click_egp,
    spend_egp / NULLIF(orders_attributed, 0)              AS cost_per_order_egp
FROM silver.marketing_campaigns;
ALTER TABLE gold.fact_marketing ADD PRIMARY KEY (campaign_id);
COMMENT ON TABLE gold.fact_marketing IS
    'Marketing campaigns with CTR, conversion rate, cost per click and cost per attributed order.';


-- =============================================================================
-- MARTS (pre-aggregated for fast dashboards)
-- =============================================================================

-- @step: mart_sales_daily
-- Grain: day x branch x channel. Base for trends, seasonality and forecasting.
DROP TABLE IF EXISTS gold.mart_sales_daily;
CREATE TABLE gold.mart_sales_daily AS
SELECT
    order_date,
    month_start,
    branch_id,
    sales_channel,
    COUNT(DISTINCT sales_order_id)        AS orders,
    SUM(quantity)                         AS units,
    SUM(quantity - returned_units)        AS net_units,
    SUM(net_sales_egp)                    AS net_sales_egp,
    SUM(refund_egp)                       AS refunds_egp,
    SUM(net_sales_after_returns_egp)      AS net_sales_after_returns_egp,
    SUM(margin_after_returns_egp)         AS margin_after_returns_egp,
    SUM(real_net_sales_egp)               AS real_net_sales_egp,
    SUM(discount_egp)                     AS discount_egp
FROM gold.fact_sales_line
GROUP BY order_date, month_start, branch_id, sales_channel;
ALTER TABLE gold.mart_sales_daily ADD PRIMARY KEY (order_date, branch_id, sales_channel);
CREATE INDEX ON gold.mart_sales_daily (month_start);
COMMENT ON TABLE gold.mart_sales_daily IS
    'Daily sales per branch and channel (after returns, real = inflation-adjusted). Use for trends and forecasting.';

-- @step: mart_sku_monthly
DROP TABLE IF EXISTS gold.mart_sku_monthly;
CREATE TABLE gold.mart_sku_monthly AS
SELECT
    month_start,
    sku_id,
    SUM(quantity)                         AS units,
    SUM(returned_units)                   AS returned_units,
    SUM(net_sales_egp)                    AS net_sales_egp,
    SUM(net_sales_after_returns_egp)      AS net_sales_after_returns_egp,
    SUM(margin_after_returns_egp)         AS margin_after_returns_egp,
    SUM(discount_egp)                     AS discount_egp,
    COUNT(DISTINCT sales_order_id)        AS orders
FROM gold.fact_sales_line
GROUP BY month_start, sku_id;
ALTER TABLE gold.mart_sku_monthly ADD PRIMARY KEY (month_start, sku_id);
COMMENT ON TABLE gold.mart_sku_monthly IS
    'Monthly performance per SKU: units, returns, sales, margin, discount. sku_id -> dim_product.';

-- @step: mart_branch_pnl_monthly
-- The "real profit per branch" table (insight #1):
-- gross margin after returns - operating expenses - payroll - transfer transport cost
DROP TABLE IF EXISTS gold.mart_branch_pnl_monthly;
CREATE TABLE gold.mart_branch_pnl_monthly AS
WITH s AS (
    SELECT month_start, branch_id,
           SUM(orders) AS orders, SUM(net_units) AS net_units,
           SUM(net_sales_egp) AS net_sales_egp, SUM(refunds_egp) AS refunds_egp,
           SUM(net_sales_after_returns_egp) AS net_sales_after_returns_egp,
           SUM(margin_after_returns_egp) AS gross_margin_egp,
           SUM(real_net_sales_egp) AS real_net_sales_egp
    FROM gold.mart_sales_daily GROUP BY month_start, branch_id
),
e AS (SELECT month_start, branch_id, SUM(amount_egp) AS opex_egp
      FROM gold.fact_expenses WHERE branch_id IS NOT NULL GROUP BY 1, 2),
p AS (SELECT month_start, branch_id, SUM(gross_pay_egp) AS payroll_egp, COUNT(DISTINCT employee_id) AS paid_employees
      FROM gold.fact_payroll GROUP BY 1, 2),
t AS (SELECT month_start, destination_branch_id AS branch_id, SUM(transport_cost_allocated_egp) AS transfer_cost_egp
      FROM gold.fact_transfers GROUP BY 1, 2),
-- every month that has sales OR costs (so no expense is lost outside the sales period)
months AS (
    SELECT month_start FROM s UNION SELECT month_start FROM e
    UNION SELECT month_start FROM p UNION SELECT month_start FROM t
)
SELECT
    m.month_start,
    b.branch_id,
    COALESCE(s.orders, 0)                      AS orders,
    COALESCE(s.net_units, 0)                   AS net_units,
    COALESCE(s.net_sales_egp, 0)               AS net_sales_egp,
    COALESCE(s.refunds_egp, 0)                 AS refunds_egp,
    COALESCE(s.net_sales_after_returns_egp, 0) AS net_sales_after_returns_egp,
    COALESCE(s.gross_margin_egp, 0)            AS gross_margin_egp,
    COALESCE(e.opex_egp, 0)                    AS opex_egp,
    COALESCE(p.payroll_egp, 0)                 AS payroll_egp,
    COALESCE(t.transfer_cost_egp, 0)           AS transfer_cost_egp,
    COALESCE(s.gross_margin_egp, 0) - COALESCE(e.opex_egp, 0)
      - COALESCE(p.payroll_egp, 0) - COALESCE(t.transfer_cost_egp, 0) AS operating_profit_egp,
    COALESCE(s.real_net_sales_egp, 0)          AS real_net_sales_egp,
    COALESCE(p.paid_employees, 0)              AS paid_employees
FROM months m
CROSS JOIN gold.dim_branch b
LEFT JOIN s ON s.month_start = m.month_start AND s.branch_id = b.branch_id
LEFT JOIN e ON e.month_start = m.month_start AND e.branch_id = b.branch_id
LEFT JOIN p ON p.month_start = m.month_start AND p.branch_id = b.branch_id
LEFT JOIN t ON t.month_start = m.month_start AND t.branch_id = b.branch_id;
ALTER TABLE gold.mart_branch_pnl_monthly ADD PRIMARY KEY (month_start, branch_id);
COMMENT ON TABLE gold.mart_branch_pnl_monthly IS
    'Monthly P&L per branch: net sales after returns, gross margin after returns, opex, payroll, transfer cost and operating_profit_egp (= margin - opex - payroll - transfer cost).';

-- @step: mart_customer_rfm
-- RFM = Recency (how recently), Frequency (how often), Monetary (how much).
-- NTILE(5) splits customers into 5 equal groups -> score 1 (worst) to 5 (best).
DROP TABLE IF EXISTS gold.mart_customer_rfm;
CREATE TABLE gold.mart_customer_rfm AS
WITH ref AS (SELECT MAX(order_date) AS ref_date FROM gold.fact_orders),
agg AS (
    SELECT customer_key,
           MIN(order_date)                    AS first_order_date,
           MAX(order_date)                    AS last_order_date,
           COUNT(*)                           AS orders,
           SUM(net_sales_after_returns_egp)   AS monetary_egp,
           SUM(real_net_sales_egp)            AS real_monetary_egp,
           AVG(net_sales_egp)                 AS avg_order_value_egp,
           SUM(CASE WHEN has_return THEN 1 ELSE 0 END) AS orders_with_return
    FROM gold.fact_orders
    WHERE customer_key <> 'GUEST'
    GROUP BY customer_key
),
scored AS (
    SELECT a.*,
           r.ref_date - a.last_order_date                        AS recency_days,
           a.last_order_date - a.first_order_date                AS active_span_days,
           NTILE(5) OVER (ORDER BY r.ref_date - a.last_order_date DESC) AS r_score,
           NTILE(5) OVER (ORDER BY a.orders)                     AS f_score,
           NTILE(5) OVER (ORDER BY a.monetary_egp)               AS m_score
    FROM agg a CROSS JOIN ref r
)
SELECT
    c.customer_key,
    c.customer_segment,
    c.governorate_ar,
    c.age_band,
    c.joined_date,
    s.first_order_date,
    s.last_order_date,
    COALESCE(s.orders, 0)          AS orders,
    COALESCE(s.monetary_egp, 0)    AS monetary_egp,
    COALESCE(s.real_monetary_egp, 0) AS real_monetary_egp,
    s.avg_order_value_egp,
    COALESCE(s.orders_with_return, 0) AS orders_with_return,
    s.recency_days,
    s.active_span_days,
    s.r_score, s.f_score, s.m_score,
    CASE
        WHEN s.customer_key IS NULL                 THEN 'Never purchased'
        WHEN s.r_score >= 4 AND s.f_score >= 4      THEN 'Champions'
        WHEN s.r_score >= 3 AND s.f_score >= 3      THEN 'Loyal'
        WHEN s.r_score >= 4 AND s.f_score <= 2      THEN 'New / Promising'
        WHEN s.r_score <= 2 AND s.f_score >= 3      THEN 'At risk'
        WHEN s.r_score <= 2 AND s.f_score <= 2      THEN 'Hibernating'
        ELSE 'Needs attention'
    END                            AS rfm_segment
FROM gold.dim_customer c
LEFT JOIN scored s ON s.customer_key = c.customer_key
WHERE NOT c.is_guest;
ALTER TABLE gold.mart_customer_rfm ADD PRIMARY KEY (customer_key);
CREATE INDEX ON gold.mart_customer_rfm (rfm_segment);
COMMENT ON TABLE gold.mart_customer_rfm IS
    'One row per registered customer with RFM scores (1-5) and rfm_segment (Champions, Loyal, New / Promising, At risk, Hibernating, Needs attention, Never purchased).';


-- =============================================================================
-- RECONCILIATION: gold must give exactly the same totals as silver
-- =============================================================================

-- @step: reconciliation
DELETE FROM audit.data_quality_checks WHERE category = 'reconciliation';

INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows, details)
SELECT 'reconciliation', 'fact_sales_line', 'rows = silver.sales_order_items rows', 'error',
       CASE WHEN g = s THEN 0 ELSE 1 END, 1, 'difference = ' || (g - s)
FROM (SELECT (SELECT COUNT(*) FROM gold.fact_sales_line) AS g,
             (SELECT COUNT(*) FROM silver.sales_order_items) AS s) x
UNION ALL
SELECT 'reconciliation', 'fact_orders', 'rows = silver.sales_orders rows', 'error',
       CASE WHEN g = s THEN 0 ELSE 1 END, 1, 'difference = ' || (g - s)
FROM (SELECT (SELECT COUNT(*) FROM gold.fact_orders) AS g,
             (SELECT COUNT(*) FROM silver.sales_orders) AS s) x
UNION ALL
SELECT 'reconciliation', 'fact_sales_line', 'total net sales = silver orders net_before_tax', 'error',
       CASE WHEN abs(g - s) < 1 THEN 0 ELSE 1 END, 1, 'difference = ' || round(g - s, 2)
FROM (SELECT (SELECT SUM(net_sales_egp) FROM gold.fact_sales_line) AS g,
             (SELECT SUM(net_before_tax_egp) FROM silver.sales_orders) AS s) x
UNION ALL
SELECT 'reconciliation', 'fact_sales_line', 'total refunds = silver capped refunds', 'error',
       CASE WHEN abs(g - s) < 1 THEN 0 ELSE 1 END, 1, 'difference = ' || round(g - s, 2)
FROM (SELECT (SELECT SUM(refund_egp) FROM gold.fact_sales_line) AS g,
             (SELECT SUM(refund_capped_egp) FROM silver.sales_returns) AS s) x
UNION ALL
SELECT 'reconciliation', 'mart_sales_daily', 'total net sales = fact_sales_line', 'error',
       CASE WHEN abs(g - s) < 1 THEN 0 ELSE 1 END, 1, 'difference = ' || round(g - s, 2)
FROM (SELECT (SELECT SUM(net_sales_egp) FROM gold.mart_sales_daily) AS g,
             (SELECT SUM(net_sales_egp) FROM gold.fact_sales_line) AS s) x
UNION ALL
SELECT 'reconciliation', 'mart_branch_pnl_monthly', 'gross margin = fact_sales_line margin after returns', 'error',
       CASE WHEN abs(g - s) < 1 THEN 0 ELSE 1 END, 1, 'difference = ' || round(g - s, 2)
FROM (SELECT (SELECT SUM(gross_margin_egp) FROM gold.mart_branch_pnl_monthly) AS g,
             (SELECT SUM(margin_after_returns_egp) FROM gold.fact_sales_line) AS s) x
UNION ALL
SELECT 'reconciliation', 'mart_branch_pnl_monthly', 'opex = all branch expenses', 'error',
       CASE WHEN abs(g - s) < 1 THEN 0 ELSE 1 END, 1, 'difference = ' || round(g - s, 2)
FROM (SELECT (SELECT SUM(opex_egp) FROM gold.mart_branch_pnl_monthly) AS g,
             (SELECT SUM(amount_egp) FROM gold.fact_expenses WHERE branch_id IS NOT NULL) AS s) x
UNION ALL
SELECT 'reconciliation', 'mart_customer_rfm', 'rows = registered customers', 'error',
       CASE WHEN g = s THEN 0 ELSE 1 END, 1, 'difference = ' || (g - s)
FROM (SELECT (SELECT COUNT(*) FROM gold.mart_customer_rfm) AS g,
             (SELECT COUNT(*) FROM silver.customers) AS s) x
UNION ALL
SELECT 'reconciliation', 'dim_date', 'every order date exists in dim_date', 'error',
       COUNT(*) FILTER (WHERE d.date_key IS NULL), COUNT(*), NULL
FROM gold.fact_orders o LEFT JOIN gold.dim_date d ON d.date_key = o.order_date;

-- @step: analyze
ANALYZE;