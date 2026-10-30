-- =============================================================================
-- quality_checks.sql  -  Data quality checks on the silver layer
-- -----------------------------------------------------------------------------
-- Every check writes ONE row into audit.data_quality_checks:
--   category    : foreign_key / consistency / validity / business / coverage /
--                 distribution / date_range
--   severity    : error   = the data is wrong and must be fixed or excluded
--                 warning = suspicious, needs a decision
--                 info    = not wrong, just useful to know
--   failed_rows : how many rows break the rule (0 = check passed)
--   total_rows  : how many rows were tested
--   details     : extra text (value lists, date ranges, ...)
--
-- Pattern used a lot below:
--   COUNT(*) FILTER (WHERE condition)  = count only the rows where condition is true
--   LEFT JOIN + "IS NULL"              = rows that have NO match in the other table
--   CROSS JOIN LATERAL (VALUES ...)    = turn one row of many counts into many rows
--                                        (so one scan of a big table feeds many checks)
--
-- Executed step by step by etl/check_quality.py
-- =============================================================================


-- @step: setup
CREATE SCHEMA IF NOT EXISTS audit;

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

-- Keep only the latest run (history of runs is in audit.etl_log)
TRUNCATE audit.data_quality_checks RESTART IDENTITY;

-- Money values are compared with a small tolerance to ignore rounding noise
-- (e.g. 10.004 vs 10.00). Temp table = lives only during this connection.
DROP TABLE IF EXISTS tmp_items_per_order;
CREATE TEMP TABLE tmp_items_per_order AS
SELECT
    sales_order_id,
    COUNT(*)                  AS n_lines,
    SUM(gross_line_egp)       AS gross,
    SUM(discount_line_egp)    AS discount,
    SUM(net_line_egp)         AS net,
    MIN(order_date)           AS min_date,
    MAX(order_date)           AS max_date,
    COUNT(DISTINCT branch_id) AS n_branches,
    MIN(branch_id)            AS branch_id
FROM silver.sales_order_items
GROUP BY sales_order_id;
CREATE INDEX ON tmp_items_per_order (sales_order_id);


-- =============================================================================
-- 1) FOREIGN KEYS: does every id point to a row that really exists?
-- =============================================================================

-- @step: foreign_keys
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'foreign_key', 'sales_orders', 'branch_id exists in branches', 'error',
       COUNT(*) FILTER (WHERE b.branch_id IS NULL), COUNT(*)
FROM silver.sales_orders o LEFT JOIN silver.branches b ON b.branch_id = o.branch_id
UNION ALL
SELECT 'foreign_key', 'sales_orders', 'customer_id exists in customers (non-guest orders)', 'error',
       COUNT(*) FILTER (WHERE o.customer_id IS NOT NULL AND c.customer_id IS NULL), COUNT(o.customer_id)
FROM silver.sales_orders o LEFT JOIN silver.customers c ON c.customer_id = o.customer_id
UNION ALL
SELECT 'foreign_key', 'sales_order_items', 'sales_order_id exists in sales_orders', 'error',
       COUNT(*) FILTER (WHERE o.sales_order_id IS NULL), COUNT(*)
FROM silver.sales_order_items i LEFT JOIN silver.sales_orders o ON o.sales_order_id = i.sales_order_id
UNION ALL
SELECT 'foreign_key', 'sales_order_items', 'sku_id exists in sku_variants', 'error',
       COUNT(*) FILTER (WHERE s.sku_id IS NULL), COUNT(*)
FROM silver.sales_order_items i LEFT JOIN silver.sku_variants s ON s.sku_id = i.sku_id
UNION ALL
SELECT 'foreign_key', 'sales_order_items', 'branch_id exists in branches', 'error',
       COUNT(*) FILTER (WHERE b.branch_id IS NULL), COUNT(*)
FROM silver.sales_order_items i LEFT JOIN silver.branches b ON b.branch_id = i.branch_id
UNION ALL
SELECT 'foreign_key', 'sku_variants', 'product_id exists in products_catalog', 'error',
       COUNT(*) FILTER (WHERE p.product_id IS NULL), COUNT(*)
FROM silver.sku_variants s LEFT JOIN silver.products_catalog p ON p.product_id = s.product_id
UNION ALL
SELECT 'foreign_key', 'sales_payments', 'sales_order_id exists in sales_orders', 'error',
       COUNT(*) FILTER (WHERE o.sales_order_id IS NULL), COUNT(*)
FROM silver.sales_payments p LEFT JOIN silver.sales_orders o ON o.sales_order_id = p.sales_order_id
UNION ALL
SELECT 'foreign_key', 'sales_returns', 'sales_line_id exists in sales_order_items', 'error',
       COUNT(*) FILTER (WHERE i.sales_line_id IS NULL), COUNT(*)
FROM silver.sales_returns r LEFT JOIN silver.sales_order_items i ON i.sales_line_id = r.sales_line_id
UNION ALL
SELECT 'foreign_key', 'delivery_shipments', 'sales_order_id exists in sales_orders', 'error',
       COUNT(*) FILTER (WHERE o.sales_order_id IS NULL), COUNT(*)
FROM silver.delivery_shipments d LEFT JOIN silver.sales_orders o ON o.sales_order_id = d.sales_order_id
UNION ALL
SELECT 'foreign_key', 'employees', 'branch_id exists in branches', 'error',
       COUNT(*) FILTER (WHERE b.branch_id IS NULL), COUNT(*)
FROM silver.employees e LEFT JOIN silver.branches b ON b.branch_id = e.branch_id
UNION ALL
SELECT 'foreign_key', 'payroll', 'employee_id exists in employees', 'error',
       COUNT(*) FILTER (WHERE e.employee_id IS NULL), COUNT(*)
FROM silver.payroll p LEFT JOIN silver.employees e ON e.employee_id = p.employee_id
UNION ALL
SELECT 'foreign_key', 'inventory_transfers', 'source_warehouse_id exists in warehouses', 'error',
       COUNT(*) FILTER (WHERE w.warehouse_id IS NULL), COUNT(*)
FROM silver.inventory_transfers t LEFT JOIN silver.warehouses w ON w.warehouse_id = t.source_warehouse_id
UNION ALL
SELECT 'foreign_key', 'inventory_transfers', 'destination_branch_id exists in branches', 'error',
       COUNT(*) FILTER (WHERE b.branch_id IS NULL), COUNT(*)
FROM silver.inventory_transfers t LEFT JOIN silver.branches b ON b.branch_id = t.destination_branch_id
UNION ALL
SELECT 'foreign_key', 'inventory_transfer_items', 'transfer_id exists in inventory_transfers', 'error',
       COUNT(*) FILTER (WHERE t.transfer_id IS NULL), COUNT(*)
FROM silver.inventory_transfer_items i LEFT JOIN silver.inventory_transfers t ON t.transfer_id = i.transfer_id
UNION ALL
SELECT 'foreign_key', 'inventory_transfer_items', 'sku_id exists in sku_variants', 'error',
       COUNT(*) FILTER (WHERE s.sku_id IS NULL), COUNT(*)
FROM silver.inventory_transfer_items i LEFT JOIN silver.sku_variants s ON s.sku_id = i.sku_id
UNION ALL
SELECT 'foreign_key', 'purchase_orders', 'supplier_id exists in suppliers', 'error',
       COUNT(*) FILTER (WHERE s.supplier_id IS NULL), COUNT(*)
FROM silver.purchase_orders p LEFT JOIN silver.suppliers s ON s.supplier_id = p.supplier_id
UNION ALL
SELECT 'foreign_key', 'purchase_orders', 'receiving_warehouse_id exists in warehouses', 'error',
       COUNT(*) FILTER (WHERE w.warehouse_id IS NULL), COUNT(*)
FROM silver.purchase_orders p LEFT JOIN silver.warehouses w ON w.warehouse_id = p.receiving_warehouse_id
UNION ALL
SELECT 'foreign_key', 'purchase_order_items', 'po_id exists in purchase_orders', 'error',
       COUNT(*) FILTER (WHERE p.po_id IS NULL), COUNT(*)
FROM silver.purchase_order_items i LEFT JOIN silver.purchase_orders p ON p.po_id = i.po_id
UNION ALL
SELECT 'foreign_key', 'purchase_order_items', 'sku_id exists in sku_variants', 'error',
       COUNT(*) FILTER (WHERE s.sku_id IS NULL), COUNT(*)
FROM silver.purchase_order_items i LEFT JOIN silver.sku_variants s ON s.sku_id = i.sku_id
UNION ALL
SELECT 'foreign_key', 'import_shipments', 'import_partner_id exists in import_partners', 'error',
       COUNT(*) FILTER (WHERE p.import_partner_id IS NULL), COUNT(*)
FROM silver.import_shipments s LEFT JOIN silver.import_partners p ON p.import_partner_id = s.import_partner_id
UNION ALL
SELECT 'foreign_key', 'import_shipments', 'destination_warehouse_id exists in warehouses', 'error',
       COUNT(*) FILTER (WHERE w.warehouse_id IS NULL), COUNT(*)
FROM silver.import_shipments s LEFT JOIN silver.warehouses w ON w.warehouse_id = s.destination_warehouse_id
UNION ALL
SELECT 'foreign_key', 'monthly_stock', 'stock_location_id exists in branches or warehouses', 'error',
       COUNT(*) FILTER (WHERE b.branch_id IS NULL AND w.warehouse_id IS NULL), COUNT(*)
FROM silver.monthly_stock m
LEFT JOIN silver.branches   b ON b.branch_id    = m.stock_location_id
LEFT JOIN silver.warehouses w ON w.warehouse_id = m.stock_location_id;


-- =============================================================================
-- 2) COVERAGE: rows that exist but have no related rows (not always an error)
-- =============================================================================

-- @step: coverage
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'coverage', 'customers', 'customer has at least one order', 'info',
       COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM silver.sales_orders o
                                          WHERE o.customer_id = c.customer_id)), COUNT(*)
FROM silver.customers c
UNION ALL
SELECT 'coverage', 'sales_orders', 'order has a payment', 'warning',
       COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM silver.sales_payments p
                                          WHERE p.sales_order_id = o.sales_order_id)), COUNT(*)
FROM silver.sales_orders o
UNION ALL
SELECT 'coverage', 'purchase_orders', 'purchase order has at least one item', 'warning',
       COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM silver.purchase_order_items i
                                          WHERE i.po_id = p.po_id)), COUNT(*)
FROM silver.purchase_orders p
UNION ALL
SELECT 'coverage', 'inventory_transfers', 'transfer has at least one item', 'warning',
       COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM silver.inventory_transfer_items i
                                          WHERE i.transfer_id = t.transfer_id)), COUNT(*)
FROM silver.inventory_transfers t
UNION ALL
SELECT 'coverage', 'sales_orders', 'guest orders (no customer_id)', 'info',
       COUNT(*) FILTER (WHERE is_guest), COUNT(*)
FROM silver.sales_orders
UNION ALL
SELECT 'coverage', 'products_catalog', 'product_id also found in public reference catalog', 'info',
       COUNT(*) FILTER (WHERE r.product_id IS NULL), COUNT(*)
FROM silver.products_catalog p
LEFT JOIN silver.product_catalog_public_reference r ON r.product_id = p.product_id
UNION ALL
SELECT 'coverage', 'products_catalog', 'product name also found in public reference catalog', 'info',
       COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM silver.product_catalog_public_reference r
                                          WHERE r.product_name_ar = p.product_name_ar)), COUNT(*)
FROM silver.products_catalog p
UNION ALL
SELECT 'coverage', 'branches', 'branch_display_name is unique', 'warning',
       COUNT(*) FILTER (WHERE n > 1), COUNT(*)
FROM (SELECT COUNT(*) OVER (PARTITION BY branch_display_name) AS n
      FROM silver.branches) x
UNION ALL
SELECT 'coverage', 'branches', 'branches sharing the same source name (fixed by D3)', 'info',
       COUNT(*) FILTER (WHERE n > 1), COUNT(*)
FROM (SELECT COUNT(*) OVER (PARTITION BY branch_name_ar) AS n
      FROM silver.branches) x;


-- =============================================================================
-- 3) SALES CONSISTENCY: do orders, items and payments agree with each other?
-- =============================================================================

-- @step: sales_orders_vs_items
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'consistency', 'sales_orders', v.check_name, v.severity, v.failed, s.total
FROM (
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE t.sales_order_id IS NULL)                        AS no_items,
        COUNT(*) FILTER (WHERE o.items_count <> t.n_lines)                      AS bad_count,
        COUNT(*) FILTER (WHERE abs(o.gross_egp - t.gross) > 0.05)               AS bad_gross,
        COUNT(*) FILTER (WHERE abs(o.discount_egp - t.discount) > 0.05)         AS bad_discount,
        COUNT(*) FILTER (WHERE abs(o.net_before_tax_egp - t.net) > 0.05)        AS bad_net_vs_lines,
        COUNT(*) FILTER (WHERE t.min_date <> o.order_date OR t.max_date <> o.order_date) AS bad_date,
        COUNT(*) FILTER (WHERE t.n_branches > 1 OR t.branch_id <> o.branch_id)  AS bad_branch,
        COUNT(*) FILTER (WHERE abs(o.net_before_tax_egp - (o.gross_egp - o.discount_egp)) > 0.05) AS bad_net,
        COUNT(*) FILTER (WHERE abs(o.paid_total_egp - (o.net_before_tax_egp + o.tax_egp)) > 0.05) AS bad_paid
    FROM silver.sales_orders o
    LEFT JOIN tmp_items_per_order t ON t.sales_order_id = o.sales_order_id
) s
CROSS JOIN LATERAL (VALUES
    ('order has at least one item line',                  'error', s.no_items),
    ('items_count = number of item lines',                'error', s.bad_count),
    ('gross_egp = sum of line gross',                     'error', s.bad_gross),
    ('discount_egp = sum of line discounts',              'error', s.bad_discount),
    ('net_before_tax_egp = sum of line net',              'error', s.bad_net_vs_lines),
    ('order_date = order_date on every item line',        'error', s.bad_date),
    ('branch_id = branch_id on every item line',          'error', s.bad_branch),
    ('net_before_tax = gross - discount',                 'error', s.bad_net),
    ('paid_total = net_before_tax + tax',                 'error', s.bad_paid)
) AS v(check_name, severity, failed);

-- Implied tax rate (to know which VAT % the data uses)
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows, details)
SELECT 'consistency', 'sales_orders', 'implied tax rate (tax / net_before_tax)', 'info', 0, COUNT(*),
       'min=' || round(MIN(tax_egp / NULLIF(net_before_tax_egp, 0)), 4) ||
       ' avg=' || round(AVG(tax_egp / NULLIF(net_before_tax_egp, 0)), 4) ||
       ' max=' || round(MAX(tax_egp / NULLIF(net_before_tax_egp, 0)), 4)
FROM silver.sales_orders;

-- @step: sales_item_lines
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'consistency', 'sales_order_items', v.check_name, v.severity, v.failed, s.total
FROM (
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE abs(i.gross_line_egp - i.quantity * i.unit_price_egp) > 0.05)      AS bad_gross,
        COUNT(*) FILTER (WHERE abs(i.net_line_egp - (i.gross_line_egp - i.discount_line_egp)) > 0.05) AS bad_net,
        COUNT(*) FILTER (WHERE abs(i.margin_egp - (i.net_line_egp - i.quantity * i.unit_cost_egp)) > 0.05) AS bad_margin,
        COUNT(*) FILTER (WHERE s.product_id IS NOT NULL AND s.product_id <> i.product_id)          AS bad_product,
        COUNT(*) FILTER (WHERE i.discount_line_egp > i.gross_line_egp)                            AS big_discount,
        COUNT(*) FILTER (WHERE i.quantity <= 0)                                                   AS bad_qty,
        COUNT(*) FILTER (WHERE i.margin_egp < 0)                                                  AS neg_margin,
        COUNT(*) FILTER (WHERE abs(i.unit_price_egp - p.listed_price_egp * s.price_multiplier) > 0.05) AS price_vs_list
    FROM silver.sales_order_items i
    LEFT JOIN silver.sku_variants     s ON s.sku_id = i.sku_id
    LEFT JOIN silver.products_catalog p ON p.product_id = s.product_id
) s
CROSS JOIN LATERAL (VALUES
    ('gross_line = quantity * unit_price',                'error',   s.bad_gross),
    ('net_line = gross_line - discount_line',             'error',   s.bad_net),
    ('margin = net_line - quantity * unit_cost',          'error',   s.bad_margin),
    ('product_id matches the product of the sku',         'error',   s.bad_product),
    ('discount not bigger than gross',                    'error',   s.big_discount),
    ('quantity > 0',                                      'error',   s.bad_qty),
    ('lines sold at a loss (margin < 0)',                 'info',    s.neg_margin),
    ('unit_price = catalog price * size/color multiplier','info',    s.price_vs_list)
) AS v(check_name, severity, failed);

-- @step: sales_payments
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'consistency', 'sales_payments', v.check_name, v.severity, v.failed, s.total
FROM (
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE abs(p.amount_egp - o.paid_total_egp) > 0.05) AS bad_amount,
        COUNT(*) FILTER (WHERE p.payment_date <> o.order_date)             AS other_date,
        COUNT(*) FILTER (WHERE p.payment_date < o.order_date)              AS paid_before,
        COUNT(*) FILTER (WHERE p.payment_method <> o.payment_method)       AS other_method
    FROM silver.sales_payments p
    JOIN silver.sales_orders o ON o.sales_order_id = p.sales_order_id
) s
CROSS JOIN LATERAL (VALUES
    ('payment amount = order paid_total',          'error',   s.bad_amount),
    ('payment_date before order_date',             'error',   s.paid_before),
    ('payment_date different from order_date',     'info',    s.other_date),
    ('payment_method same as on the order',        'warning', s.other_method)
) AS v(check_name, severity, failed);


-- =============================================================================
-- 4) VALIDITY: dates in the right order, amounts that make sense
-- =============================================================================

-- @step: returns_and_delivery
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'validity', 'sales_returns', v.check_name, v.severity, v.failed, s.total
FROM (
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE r.return_date < i.order_date)                 AS before_sale,
        COUNT(*) FILTER (WHERE r.return_quantity > i.quantity)               AS too_many,
        COUNT(*) FILTER (WHERE r.refund_capped_egp > r.returned_value_egp + 0.05) AS too_much,
        COUNT(*) FILTER (WHERE r.refund_exceeds_value)                       AS raw_too_much,
        COUNT(*) FILTER (WHERE r.sku_id <> i.sku_id)                         AS other_sku,
        COUNT(*) FILTER (WHERE r.sales_order_id <> i.sales_order_id)         AS other_order
    FROM silver.sales_returns r
    JOIN silver.sales_order_items i ON i.sales_line_id = r.sales_line_id
) s
CROSS JOIN LATERAL (VALUES
    ('return_date not before the sale',               'error', s.before_sale),
    ('return_quantity not more than sold quantity',   'error', s.too_many),
    ('refund_capped not more than returned value',    'error', s.too_much),
    ('raw refund above returned value (capped by D1)', 'info',  s.raw_too_much),
    ('return sku = sku of the sold line',             'error', s.other_sku),
    ('return sales_order_id = order of the line',     'error', s.other_order)
) AS v(check_name, severity, failed);

INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'validity', 'delivery_shipments', v.check_name, v.severity, v.failed, s.total
FROM (
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE d.delivery_date < d.ship_date) AS deliver_before_ship,
        COUNT(*) FILTER (WHERE d.ship_date < o.order_date)    AS ship_before_order
    FROM silver.delivery_shipments d
    JOIN silver.sales_orders o ON o.sales_order_id = d.sales_order_id
) s
CROSS JOIN LATERAL (VALUES
    ('delivery_date not before ship_date',  'error', s.deliver_before_ship),
    ('ship_date not before order_date',     'error', s.ship_before_order)
) AS v(check_name, severity, failed);

-- Which sales channels have shipments? (online orders should, store orders should not)
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows, details)
SELECT 'validity', 'delivery_shipments', 'shipments per sales_channel', 'info', 0, SUM(n),
       string_agg(sales_channel || ' (' || n || ')', ' ; ' ORDER BY n DESC)
FROM (SELECT o.sales_channel, COUNT(*) AS n
      FROM silver.delivery_shipments d
      JOIN silver.sales_orders o ON o.sales_order_id = d.sales_order_id
      GROUP BY o.sales_channel) x;

-- @step: purchasing
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'consistency', 'purchase_orders', 'po_subtotal = sum of line costs', 'error',
       COUNT(*) FILTER (WHERE abs(p.po_subtotal_egp - COALESCE(t.lines, 0)) > 0.05), COUNT(*)
FROM silver.purchase_orders p
LEFT JOIN (SELECT po_id, SUM(line_cost_egp) AS lines
           FROM silver.purchase_order_items GROUP BY po_id) t ON t.po_id = p.po_id
UNION ALL
SELECT 'consistency', 'purchase_order_items', 'line_cost = quantity * unit_cost', 'error',
       COUNT(*) FILTER (WHERE abs(line_cost_egp - quantity * unit_cost_egp) > 0.05), COUNT(*)
FROM silver.purchase_order_items
UNION ALL
SELECT 'validity', 'purchase_order_items', 'delivery_date not before po_date', 'error',
       COUNT(*) FILTER (WHERE i.delivery_date < p.po_date), COUNT(*)
FROM silver.purchase_order_items i JOIN silver.purchase_orders p ON p.po_id = i.po_id;

-- @step: people_and_marketing
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'consistency', 'payroll', 'net_paid = base + overtime + bonus - deductions', 'error',
       COUNT(*) FILTER (WHERE abs(net_paid_egp - (base_salary_egp + overtime_egp + bonus_egp - deductions_egp)) > 0.05),
       COUNT(*)
FROM silver.payroll
UNION ALL
SELECT 'validity', 'payroll', 'paid month not before the hire month', 'error',
       COUNT(*) FILTER (WHERE p.pay_month < date_trunc('month', e.hire_date)), COUNT(*)
FROM silver.payroll p JOIN silver.employees e ON e.employee_id = p.employee_id
UNION ALL
SELECT 'validity', 'employees', 'hire_date not in the future', 'error',
       COUNT(*) FILTER (WHERE hire_date > current_date), COUNT(*)
FROM silver.employees
UNION ALL
SELECT 'validity', 'marketing_campaigns', 'end_date not before start_date', 'error',
       COUNT(*) FILTER (WHERE end_date < start_date), COUNT(*)
FROM silver.marketing_campaigns
UNION ALL
SELECT 'validity', 'marketing_campaigns', 'clicks not more than impressions', 'error',
       COUNT(*) FILTER (WHERE clicks > impressions), COUNT(*)
FROM silver.marketing_campaigns
UNION ALL
SELECT 'validity', 'marketing_campaigns', 'orders_attributed not more than clicks', 'warning',
       COUNT(*) FILTER (WHERE orders_attributed > clicks), COUNT(*)
FROM silver.marketing_campaigns
UNION ALL
SELECT 'validity', 'marketing_campaigns', 'spend above budget', 'info',
       COUNT(*) FILTER (WHERE spend_egp > budget_egp), COUNT(*)
FROM silver.marketing_campaigns;


-- =============================================================================
-- 5) BUSINESS RULES: things that are logically impossible in real life
-- =============================================================================

-- @step: business_rules
INSERT INTO audit.data_quality_checks (category, table_name, check_name, severity, failed_rows, total_rows)
SELECT 'business', 'sales_orders', 'no sales before the branch effective_opening_date', 'warning',
       COUNT(*) FILTER (WHERE o.order_date < b.effective_opening_date), COUNT(*)
FROM silver.sales_orders o JOIN silver.branches b ON b.branch_id = o.branch_id
UNION ALL
SELECT 'business', 'sales_orders', 'sales before the REPORTED opening_date (fixed by D2)', 'info',
       COUNT(*) FILTER (WHERE o.order_date < b.opening_date), COUNT(*)
FROM silver.sales_orders o JOIN silver.branches b ON b.branch_id = o.branch_id
UNION ALL
SELECT 'business', 'sales_orders', 'no orders before the customer joined_date', 'warning',
       COUNT(*) FILTER (WHERE o.order_date < c.joined_date), COUNT(*)
FROM silver.sales_orders o JOIN silver.customers c ON c.customer_id = o.customer_id
UNION ALL
SELECT 'business', 'inventory_transfers', 'no transfers to a branch before effective opening', 'warning',
       COUNT(*) FILTER (WHERE t.transfer_date < b.effective_opening_date), COUNT(*)
FROM silver.inventory_transfers t JOIN silver.branches b ON b.branch_id = t.destination_branch_id
UNION ALL
SELECT 'consistency', 'sales_orders', 'return_level matches the returns table', 'error',
       COUNT(*) FILTER (WHERE (o.return_level <> 'none') <> EXISTS (SELECT 1 FROM silver.sales_returns r
                                                                 WHERE r.sales_order_id = o.sales_order_id)),
       COUNT(*)
FROM silver.sales_orders o
UNION ALL
SELECT 'business', 'sales_orders', 'reported status disagrees with returns (fixed by D4)', 'info',
       COUNT(*) FILTER (WHERE (status = 'Partially returned') <> has_return), COUNT(*)
FROM silver.sales_orders
UNION ALL
SELECT 'business', 'operating_expenses', 'expenses booked on head-office departments', 'info',
       COUNT(*) FILTER (WHERE cost_center_type = 'department'), COUNT(*)
FROM silver.operating_expenses;


-- =============================================================================
-- 6) DISTRIBUTIONS & DATE RANGES (profiling of categories and time coverage)
-- =============================================================================

-- @step: distributions
-- DO $$ ... $$ runs a small PL/pgSQL program. Here it loops over a list of
-- (table, column) pairs and, for each one, stores "value (count) ; value (count) ..."
-- format('%I') safely inserts a name, format('%L') safely inserts a text literal.
DO $$
DECLARE
    r RECORD;
    d TEXT;
    n BIGINT;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('sales_orders', 'status'), ('sales_orders', 'sales_channel'),
            ('sales_orders', 'payment_method'), ('sales_payments', 'status'),
            ('sales_payments', 'payment_method'), ('sales_returns', 'reason'),
            ('sales_returns', 'refund_method'), ('delivery_shipments', 'carrier'),
            ('delivery_shipments', 'fulfillment_status'), ('inventory_transfers', 'transfer_status'),
            ('purchase_orders', 'po_status'), ('purchase_orders', 'po_purpose'),
            ('purchase_orders', 'currency'), ('customers', 'customer_segment'),
            ('customers', 'age_band'), ('sku_variants', 'size'),
            ('products_catalog', 'category_en'), ('products_catalog', 'audience'),
            ('marketing_campaigns', 'channel'), ('marketing_campaigns', 'target_audience'),
            ('branches', 'retail_location_type'), ('employees', 'position_en'),
            ('monthly_stock', 'stock_location_type'), ('monthly_stock', 'product_category'),
            ('operating_expenses', 'expense_category'), ('operating_expenses', 'cost_center_type'),
            ('warehouses', 'warehouse_kind'), ('import_shipments', 'commodity_class')
        ) AS t(tbl, col)
    LOOP
        EXECUTE format(
            'SELECT string_agg(v || %L || c || %L, %L ORDER BY c DESC), SUM(c)
             FROM (SELECT COALESCE(%I::TEXT, %L) AS v, COUNT(*) AS c
                   FROM silver.%I GROUP BY 1) x',
            ' (', ')', ' ; ', r.col, '<NULL>', r.tbl)
        INTO d, n;

        INSERT INTO audit.data_quality_checks
            (category, table_name, check_name, severity, failed_rows, total_rows, details)
        VALUES ('distribution', r.tbl, r.col, 'info', 0, n, d);
    END LOOP;
END $$;

-- @step: date_ranges
DO $$
DECLARE
    r RECORD;
    d TEXT;
    n BIGINT;
    nulls BIGINT;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('sales_orders', 'order_date'), ('sales_order_items', 'order_date'),
            ('sales_payments', 'payment_date'), ('sales_returns', 'return_date'),
            ('delivery_shipments', 'ship_date'), ('delivery_shipments', 'delivery_date'),
            ('inventory_transfers', 'transfer_date'), ('purchase_orders', 'po_date'),
            ('purchase_order_items', 'delivery_date'), ('operating_expenses', 'expense_date'),
            ('monthly_stock', 'month_start'), ('payroll', 'pay_month'),
            ('marketing_campaigns', 'start_date'), ('import_shipments', 'shipment_date'),
            ('customers', 'joined_date'), ('branches', 'opening_date'), ('employees', 'hire_date')
        ) AS t(tbl, col)
    LOOP
        EXECUTE format(
            'SELECT MIN(%1$I) || %3$L || MAX(%1$I), COUNT(*), COUNT(*) FILTER (WHERE %1$I IS NULL)
             FROM silver.%2$I',
            r.col, r.tbl, ' -> ')
        INTO d, n, nulls;

        INSERT INTO audit.data_quality_checks
            (category, table_name, check_name, severity, failed_rows, total_rows, details)
        VALUES ('date_range', r.tbl, r.col || ' (failed = NULL dates)', 'info', nulls, n, d);
    END LOOP;
END $$;


-- @step: finish
UPDATE audit.data_quality_checks
SET failed_pct = round(100.0 * failed_rows / NULLIF(total_rows, 0), 3);