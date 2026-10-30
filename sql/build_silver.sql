-- =============================================================================
-- build_silver.sql  -  bronze (raw text)  ->  silver (typed, clean, enriched)
-- -----------------------------------------------------------------------------
-- What silver does to every table:
--   1. Correct data types: TEXT -> DATE / NUMERIC / INTEGER
--   2. Unify date formats: 'YYYY-MM-DD' and 'MM/DD/YYYY' -> one DATE type
--   3. Clean text: trim spaces, collapse double spaces, '' -> NULL
--   4. Primary keys (also proves the IDs are unique) + indexes for fast joins
--   5. A few helpful derived columns (is_guest, delivery_days, landed_cost_usd, ...)
--   6. NO rows are deleted here. Problems are measured in quality_checks.sql first.
--
-- Money columns use plain NUMERIC (no fixed scale) so values stay EXACTLY as in
-- the source - rounding here would break the consistency checks later.
--
-- This file is executed step by step by etl/build_silver.py.
-- Every "-- @step: name" line starts a new step (one table = one step).
-- =============================================================================


-- @step: setup
-- Helper functions live in their own schema "etl" so they don't mix with data.
-- IMMUTABLE = same input always gives same output (lets Postgres optimize).
CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS silver;

-- Trim, collapse repeated spaces, and turn empty text into NULL
CREATE OR REPLACE FUNCTION etl.clean_text(v TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT NULLIF(regexp_replace(trim(v), '\s+', ' ', 'g'), '')
$$;

-- Text -> NUMERIC (removes thousand separators like 1,200)
CREATE OR REPLACE FUNCTION etl.to_num(v TEXT) RETURNS NUMERIC
LANGUAGE sql IMMUTABLE AS $$
    SELECT NULLIF(replace(trim(v), ',', ''), '')::NUMERIC
$$;

-- Text -> INTEGER
CREATE OR REPLACE FUNCTION etl.to_int(v TEXT) RETURNS INTEGER
LANGUAGE sql IMMUTABLE AS $$
    SELECT etl.to_num(v)::INTEGER
$$;

-- Text -> BIGINT (for very large counts like impressions)
CREATE OR REPLACE FUNCTION etl.to_bigint(v TEXT) RETURNS BIGINT
LANGUAGE sql IMMUTABLE AS $$
    SELECT etl.to_num(v)::BIGINT
$$;

-- 'YYYY-MM-DD' (optionally followed by a time) -> DATE
CREATE OR REPLACE FUNCTION etl.to_date_iso(v TEXT) RETURNS DATE
LANGUAGE sql IMMUTABLE AS $$
    SELECT NULLIF(left(trim(v), 10), '')::DATE
$$;

-- 'MM/DD/YYYY' (optionally followed by a time) -> DATE
CREATE OR REPLACE FUNCTION etl.to_date_mdy(v TEXT) RETURNS DATE
LANGUAGE sql IMMUTABLE AS $$
    SELECT to_date(NULLIF(split_part(trim(v), ' ', 1), ''), 'MM/DD/YYYY')
$$;

-- 'YYYY-MM' -> first day of that month as a DATE (2018-10 -> 2018-10-01)
CREATE OR REPLACE FUNCTION etl.month_start(v TEXT) RETURNS DATE
LANGUAGE sql IMMUTABLE AS $$
    SELECT to_date(NULLIF(trim(v), '') || '-01', 'YYYY-MM-DD')
$$;


-- =============================================================================
-- DIMENSION-LIKE TABLES (small reference tables) - built first
-- =============================================================================

-- @step: branches
DROP TABLE IF EXISTS silver.branches;
CREATE TABLE silver.branches AS
SELECT
    etl.clean_text(branch_id)            AS branch_id,
    etl.clean_text(branch_name_ar)       AS branch_name_ar,
    etl.clean_text(governorate_ar)       AS governorate_ar,
    etl.clean_text(city_ar)              AS city_ar,
    etl.clean_text(address_ar)           AS address_ar,
    etl.clean_text(retail_location_type) AS retail_location_type,
    etl.to_date_mdy(opening_date)        AS opening_date,      -- source is MM/DD/YYYY
    _source_file,
    now()                                AS _silver_built_at
FROM bronze.branches;
ALTER TABLE silver.branches ADD PRIMARY KEY (branch_id);

-- @step: warehouses
DROP TABLE IF EXISTS silver.warehouses;
CREATE TABLE silver.warehouses AS
SELECT
    etl.clean_text(warehouse_id)    AS warehouse_id,
    etl.clean_text(warehouse_label) AS warehouse_label,
    etl.clean_text(governorate_ar)  AS governorate_ar,
    etl.clean_text(warehouse_kind)  AS warehouse_kind,
    etl.to_int(capacity_units)      AS capacity_units,
    _source_file,
    now()                           AS _silver_built_at
FROM bronze.warehouses;
ALTER TABLE silver.warehouses ADD PRIMARY KEY (warehouse_id);

-- @step: customers
DROP TABLE IF EXISTS silver.customers;
CREATE TABLE silver.customers AS
SELECT
    etl.clean_text(customer_id)      AS customer_id,
    etl.clean_text(customer_segment) AS customer_segment,
    etl.clean_text(customer_name_ar) AS customer_name_ar,
    etl.clean_text(governorate_ar)   AS governorate_ar,
    etl.to_date_mdy(joined_date)     AS joined_date,          -- source is MM/DD/YYYY
    etl.clean_text(age_band)         AS age_band,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.customers;
ALTER TABLE silver.customers ADD PRIMARY KEY (customer_id);

-- @step: products_catalog
DROP TABLE IF EXISTS silver.products_catalog;
CREATE TABLE silver.products_catalog AS
SELECT
    etl.clean_text(product_id)       AS product_id,
    etl.clean_text(product_name_ar)  AS product_name_ar,
    etl.clean_text(category_en)      AS category_en,
    etl.clean_text(audience)         AS audience,
    etl.to_num(listed_price_egp)     AS listed_price_egp,
    etl.clean_text(source_url)       AS source_url,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.products_catalog;
ALTER TABLE silver.products_catalog ADD PRIMARY KEY (product_id);

-- @step: product_catalog_public_reference
DROP TABLE IF EXISTS silver.product_catalog_public_reference;
CREATE TABLE silver.product_catalog_public_reference AS
SELECT
    etl.clean_text(product_id)       AS product_id,
    etl.clean_text(product_name_ar)  AS product_name_ar,
    etl.clean_text(category)         AS category,
    etl.to_num(listed_price_egp)     AS listed_price_egp,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.product_catalog_public_reference;
ALTER TABLE silver.product_catalog_public_reference ADD PRIMARY KEY (product_id);

-- @step: sku_variants
DROP TABLE IF EXISTS silver.sku_variants;
CREATE TABLE silver.sku_variants AS
SELECT
    etl.clean_text(sku_id)           AS sku_id,
    etl.clean_text(product_id)       AS product_id,
    etl.clean_text(size)             AS size,
    etl.clean_text(color_ar)         AS color_ar,
    etl.to_num(price_multiplier)     AS price_multiplier,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.sku_variants;
ALTER TABLE silver.sku_variants ADD PRIMARY KEY (sku_id);
CREATE INDEX ON silver.sku_variants (product_id);

-- @step: suppliers
DROP TABLE IF EXISTS silver.suppliers;
CREATE TABLE silver.suppliers AS
SELECT
    etl.clean_text(supplier_id)      AS supplier_id,
    etl.clean_text(supplier_name_ar) AS supplier_name_ar,
    etl.clean_text(material_type)    AS material_type,
    etl.clean_text(city_country)     AS city_country,
    etl.to_int(payment_terms_days)   AS payment_terms_days,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.suppliers;
ALTER TABLE silver.suppliers ADD PRIMARY KEY (supplier_id);

-- @step: factories
DROP TABLE IF EXISTS silver.factories;
CREATE TABLE silver.factories AS
SELECT
    etl.clean_text(factory_id)       AS factory_id,
    etl.clean_text(factory_name_ar)  AS factory_name_ar,
    etl.clean_text(governorate_ar)   AS governorate_ar,
    etl.clean_text(production_focus) AS production_focus,   -- constant column, kept anyway
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.factories;
ALTER TABLE silver.factories ADD PRIMARY KEY (factory_id);

-- @step: import_partners
DROP TABLE IF EXISTS silver.import_partners;
CREATE TABLE silver.import_partners AS
SELECT
    etl.clean_text(import_partner_id) AS import_partner_id,
    etl.clean_text(partner_name)      AS partner_name,
    etl.clean_text(country)           AS country,
    etl.clean_text(goods_category)    AS goods_category,
    etl.clean_text(shipping_terms)    AS shipping_terms,
    _source_file,
    now()                             AS _silver_built_at
FROM bronze.import_partners;
ALTER TABLE silver.import_partners ADD PRIMARY KEY (import_partner_id);

-- @step: employees
DROP TABLE IF EXISTS silver.employees;
CREATE TABLE silver.employees AS
SELECT
    etl.clean_text(employee_id)        AS employee_id,
    etl.clean_text(employee_name_ar)   AS employee_name_ar,
    etl.clean_text(branch_id)          AS branch_id,
    etl.clean_text(position_en)        AS position_en,
    etl.to_date_mdy(hire_date)         AS hire_date,          -- source is MM/DD/YYYY
    etl.to_num(salary_base_egp_2026)   AS salary_base_egp_2026,
    _source_file,
    now()                              AS _silver_built_at
FROM bronze.employees;
ALTER TABLE silver.employees ADD PRIMARY KEY (employee_id);
CREATE INDEX ON silver.employees (branch_id);


-- =============================================================================
-- SALES (the core - biggest tables)
-- =============================================================================

-- @step: sales_orders
DROP TABLE IF EXISTS silver.sales_orders;
CREATE TABLE silver.sales_orders AS
SELECT
    etl.clean_text(sales_order_id)   AS sales_order_id,
    etl.to_date_iso(order_date)      AS order_date,
    etl.clean_text(branch_id)        AS branch_id,
    etl.clean_text(customer_id)      AS customer_id,
    -- 19% of orders have no customer -> walk-in / unregistered buyers, not an error
    (etl.clean_text(customer_id) IS NULL) AS is_guest,
    etl.clean_text(sales_channel)    AS sales_channel,
    etl.clean_text(payment_method)   AS payment_method,
    etl.to_int(items_count)          AS items_count,
    etl.to_num(gross_egp)            AS gross_egp,
    etl.to_num(discount_egp)         AS discount_egp,
    etl.to_num(net_before_tax_egp)   AS net_before_tax_egp,
    etl.to_num(tax_egp)              AS tax_egp,
    etl.to_num(paid_total_egp)       AS paid_total_egp,
    etl.clean_text(status)           AS status,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.sales_orders;
ALTER TABLE silver.sales_orders ADD PRIMARY KEY (sales_order_id);
CREATE INDEX ON silver.sales_orders (order_date);
CREATE INDEX ON silver.sales_orders (branch_id);
CREATE INDEX ON silver.sales_orders (customer_id);

-- @step: sales_order_items
DROP TABLE IF EXISTS silver.sales_order_items;
CREATE TABLE silver.sales_order_items AS
SELECT
    etl.clean_text(sales_line_id)    AS sales_line_id,
    etl.clean_text(sales_order_id)   AS sales_order_id,
    etl.to_date_iso(order_date)      AS order_date,
    etl.clean_text(branch_id)        AS branch_id,
    etl.clean_text(sku_id)           AS sku_id,
    etl.clean_text(product_id)       AS product_id,
    etl.to_int(quantity)             AS quantity,
    etl.to_num(unit_price_egp)       AS unit_price_egp,
    etl.to_num(gross_line_egp)       AS gross_line_egp,
    etl.to_num(discount_line_egp)    AS discount_line_egp,
    etl.to_num(net_line_egp)         AS net_line_egp,
    etl.to_num(unit_cost_egp)        AS unit_cost_egp,
    etl.to_num(margin_egp)           AS margin_egp,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.sales_order_items;
ALTER TABLE silver.sales_order_items ADD PRIMARY KEY (sales_line_id);
CREATE INDEX ON silver.sales_order_items (sales_order_id);
CREATE INDEX ON silver.sales_order_items (sku_id);
CREATE INDEX ON silver.sales_order_items (order_date);

-- @step: sales_payments
DROP TABLE IF EXISTS silver.sales_payments;
CREATE TABLE silver.sales_payments AS
SELECT
    etl.clean_text(payment_id)       AS payment_id,
    etl.clean_text(sales_order_id)   AS sales_order_id,
    etl.to_date_iso(payment_date)    AS payment_date,
    etl.clean_text(payment_method)   AS payment_method,
    etl.to_num(amount_egp)           AS amount_egp,
    etl.clean_text(status)           AS status,              -- constant column, kept anyway
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.sales_payments;
ALTER TABLE silver.sales_payments ADD PRIMARY KEY (payment_id);
CREATE INDEX ON silver.sales_payments (sales_order_id);

-- @step: sales_returns
DROP TABLE IF EXISTS silver.sales_returns;
CREATE TABLE silver.sales_returns AS
SELECT
    etl.clean_text(return_id)        AS return_id,
    etl.clean_text(sales_order_id)   AS sales_order_id,
    etl.clean_text(sales_line_id)    AS sales_line_id,
    etl.to_date_iso(return_date)     AS return_date,
    etl.clean_text(sku_id)           AS sku_id,
    etl.to_int(return_quantity)      AS return_quantity,
    etl.to_num(refund_amount_egp)    AS refund_amount_egp,
    etl.clean_text(reason)           AS reason,
    etl.clean_text(refund_method)    AS refund_method,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.sales_returns;
ALTER TABLE silver.sales_returns ADD PRIMARY KEY (return_id);
CREATE INDEX ON silver.sales_returns (sales_line_id);
CREATE INDEX ON silver.sales_returns (sales_order_id);

-- @step: delivery_shipments
DROP TABLE IF EXISTS silver.delivery_shipments;
CREATE TABLE silver.delivery_shipments AS
SELECT
    etl.clean_text(shipment_id)          AS shipment_id,
    etl.clean_text(sales_order_id)       AS sales_order_id,
    etl.to_date_iso(ship_date)           AS ship_date,
    etl.to_date_iso(delivery_date)       AS delivery_date,
    -- DATE - DATE in Postgres = number of days between them
    etl.to_date_iso(delivery_date) - etl.to_date_iso(ship_date) AS delivery_days,
    etl.clean_text(ship_to_governorate)  AS ship_to_governorate,
    etl.clean_text(carrier)              AS carrier,
    etl.to_num(shipping_fee_egp)         AS shipping_fee_egp,
    etl.clean_text(fulfillment_status)   AS fulfillment_status,
    _source_file,
    now()                                AS _silver_built_at
FROM bronze.delivery_shipments;
ALTER TABLE silver.delivery_shipments ADD PRIMARY KEY (shipment_id);
CREATE INDEX ON silver.delivery_shipments (sales_order_id);


-- =============================================================================
-- INVENTORY
-- =============================================================================

-- @step: monthly_stock
DROP TABLE IF EXISTS silver.monthly_stock;
CREATE TABLE silver.monthly_stock AS
SELECT
    etl.month_start(year_month)            AS month_start,     -- 2018-10 -> 2018-10-01
    etl.clean_text(stock_location_id)      AS stock_location_id,
    etl.clean_text(stock_location_type)    AS stock_location_type,
    etl.clean_text(product_category)       AS product_category,
    etl.to_int(closing_units)              AS closing_units,
    etl.to_num(closing_stock_value_egp)    AS closing_stock_value_egp,
    etl.to_num(stockout_risk_score)        AS stockout_risk_score,
    _source_file,
    now()                                  AS _silver_built_at
FROM bronze.monthly_stock;
-- No single ID column: the key is month + location + category together (composite key)
ALTER TABLE silver.monthly_stock ADD PRIMARY KEY (month_start, stock_location_id, product_category);

-- @step: inventory_transfers
DROP TABLE IF EXISTS silver.inventory_transfers;
CREATE TABLE silver.inventory_transfers AS
SELECT
    etl.clean_text(transfer_id)            AS transfer_id,
    etl.to_date_iso(transfer_date)         AS transfer_date,
    etl.clean_text(source_warehouse_id)    AS source_warehouse_id,
    etl.clean_text(destination_branch_id)  AS destination_branch_id,
    etl.clean_text(transfer_status)        AS transfer_status,
    etl.to_num(transport_cost_egp)         AS transport_cost_egp,
    _source_file,
    now()                                  AS _silver_built_at
FROM bronze.inventory_transfers;
ALTER TABLE silver.inventory_transfers ADD PRIMARY KEY (transfer_id);

-- @step: inventory_transfer_items
DROP TABLE IF EXISTS silver.inventory_transfer_items;
CREATE TABLE silver.inventory_transfer_items AS
SELECT
    etl.clean_text(transfer_line_id)  AS transfer_line_id,
    etl.clean_text(transfer_id)       AS transfer_id,
    etl.clean_text(sku_id)            AS sku_id,
    etl.to_int(quantity_units)        AS quantity_units,
    _source_file,
    now()                             AS _silver_built_at
FROM bronze.inventory_transfer_items;
ALTER TABLE silver.inventory_transfer_items ADD PRIMARY KEY (transfer_line_id);
CREATE INDEX ON silver.inventory_transfer_items (transfer_id);


-- =============================================================================
-- PURCHASING & IMPORTS
-- =============================================================================

-- @step: purchase_orders
DROP TABLE IF EXISTS silver.purchase_orders;
CREATE TABLE silver.purchase_orders AS
SELECT
    etl.clean_text(po_id)                   AS po_id,
    etl.to_date_iso(po_date)                AS po_date,
    etl.clean_text(supplier_id)             AS supplier_id,
    etl.clean_text(receiving_warehouse_id)  AS receiving_warehouse_id,
    etl.clean_text(po_status)               AS po_status,
    etl.clean_text(currency)                AS currency,     -- constant column, kept anyway
    etl.to_num(po_subtotal_egp)             AS po_subtotal_egp,
    etl.to_int(payment_terms_days)          AS payment_terms_days,
    etl.clean_text(po_purpose)              AS po_purpose,
    _source_file,
    now()                                   AS _silver_built_at
FROM bronze.purchase_orders;
ALTER TABLE silver.purchase_orders ADD PRIMARY KEY (po_id);

-- @step: purchase_order_items
DROP TABLE IF EXISTS silver.purchase_order_items;
CREATE TABLE silver.purchase_order_items AS
SELECT
    etl.clean_text(po_line_id)       AS po_line_id,
    etl.clean_text(po_id)            AS po_id,
    etl.clean_text(sku_id)           AS sku_id,
    etl.to_int(quantity)             AS quantity,
    etl.to_num(unit_cost_egp)        AS unit_cost_egp,
    etl.to_num(line_cost_egp)        AS line_cost_egp,
    etl.to_date_iso(delivery_date)   AS delivery_date,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.purchase_order_items;
ALTER TABLE silver.purchase_order_items ADD PRIMARY KEY (po_line_id);
CREATE INDEX ON silver.purchase_order_items (po_id);

-- @step: import_shipments
DROP TABLE IF EXISTS silver.import_shipments;
CREATE TABLE silver.import_shipments AS
SELECT
    etl.clean_text(import_shipment_id)        AS import_shipment_id,
    etl.clean_text(import_partner_id)         AS import_partner_id,
    etl.to_date_mdy(shipment_date)            AS shipment_date,    -- source is MM/DD/YYYY
    etl.clean_text(port_name)                 AS port_name,
    etl.clean_text(container_type)            AS container_type,
    etl.clean_text(commodity_class)           AS commodity_class,
    etl.to_num(customs_value_usd)             AS customs_value_usd,
    etl.to_num(freight_usd)                   AS freight_usd,
    etl.to_num(duty_and_tax_usd)              AS duty_and_tax_usd,
    -- landed cost = what the goods really cost once they arrive
    COALESCE(etl.to_num(customs_value_usd), 0)
      + COALESCE(etl.to_num(freight_usd), 0)
      + COALESCE(etl.to_num(duty_and_tax_usd), 0)  AS landed_cost_usd,
    etl.clean_text(destination_warehouse_id)  AS destination_warehouse_id,
    _source_file,
    now()                                     AS _silver_built_at
FROM bronze.import_shipments;
ALTER TABLE silver.import_shipments ADD PRIMARY KEY (import_shipment_id);


-- =============================================================================
-- COSTS, PEOPLE & MARKETING
-- =============================================================================

-- @step: operating_expenses
DROP TABLE IF EXISTS silver.operating_expenses;
CREATE TABLE silver.operating_expenses AS
SELECT
    etl.clean_text(e.expense_id)               AS expense_id,
    etl.to_date_iso(e.expense_date)            AS expense_date,
    etl.clean_text(e.branch_or_department_id)  AS cost_center_id,
    -- split the mixed id column: is it a branch, a warehouse, or a head-office department?
    CASE
        WHEN EXISTS (SELECT 1 FROM silver.branches b
                     WHERE b.branch_id = etl.clean_text(e.branch_or_department_id)) THEN 'branch'
        WHEN EXISTS (SELECT 1 FROM silver.warehouses w
                     WHERE w.warehouse_id = etl.clean_text(e.branch_or_department_id)) THEN 'warehouse'
        ELSE 'department'
    END                                        AS cost_center_type,
    etl.clean_text(e.expense_category)         AS expense_category,
    etl.to_num(e.amount_egp)                   AS amount_egp,
    etl.clean_text(e.payment_method)           AS payment_method,
    etl.clean_text(e.vendor_name)              AS vendor_name,
    e._source_file,
    now()                                      AS _silver_built_at
FROM bronze.operating_expenses e;
ALTER TABLE silver.operating_expenses ADD PRIMARY KEY (expense_id);
CREATE INDEX ON silver.operating_expenses (cost_center_id);

-- @step: payroll
DROP TABLE IF EXISTS silver.payroll;
CREATE TABLE silver.payroll AS
SELECT
    etl.clean_text(payroll_id)       AS payroll_id,
    etl.clean_text(employee_id)      AS employee_id,
    etl.month_start(pay_month)       AS pay_month,          -- 2024-03 -> 2024-03-01
    etl.to_num(base_salary_egp)      AS base_salary_egp,
    etl.to_num(overtime_egp)         AS overtime_egp,
    etl.to_num(bonus_egp)            AS bonus_egp,
    etl.to_num(deductions_egp)       AS deductions_egp,
    etl.to_num(net_paid_egp)         AS net_paid_egp,
    _source_file,
    now()                            AS _silver_built_at
FROM bronze.payroll;
ALTER TABLE silver.payroll ADD PRIMARY KEY (payroll_id);
CREATE INDEX ON silver.payroll (employee_id);

-- @step: marketing_campaigns
DROP TABLE IF EXISTS silver.marketing_campaigns;
CREATE TABLE silver.marketing_campaigns AS
SELECT
    etl.clean_text(campaign_id)       AS campaign_id,
    etl.to_date_iso(start_date)       AS start_date,
    etl.to_date_iso(end_date)         AS end_date,
    etl.clean_text(channel)           AS channel,
    etl.clean_text(target_audience)   AS target_audience,
    etl.clean_text(governorate_ar)    AS governorate_ar,
    etl.to_num(budget_egp)            AS budget_egp,
    etl.to_num(spend_egp)             AS spend_egp,
    etl.to_bigint(impressions)        AS impressions,
    etl.to_bigint(clicks)             AS clicks,
    etl.to_int(orders_attributed)     AS orders_attributed,
    _source_file,
    now()                             AS _silver_built_at
FROM bronze.marketing_campaigns;
ALTER TABLE silver.marketing_campaigns ADD PRIMARY KEY (campaign_id);


-- @step: analyze
-- Refresh the statistics Postgres uses to plan fast queries on the new tables
ANALYZE;