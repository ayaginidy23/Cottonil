-- =============================================================================
-- silver_fixes.sql  -  Phase 2 cleaning: apply the decisions from
--                      docs/cleaning_decisions.md to the silver tables
-- -----------------------------------------------------------------------------
-- Rule: we never delete rows here. Unreliable source values are KEPT, and we add
-- corrected / derived columns + flags next to them, so every decision is visible
-- and reversible.
--
-- Runs automatically right after build_silver.sql (see etl/build_silver.py).
-- =============================================================================


-- @step: fix_branches
-- Decision D2: opening_date is unreliable (all 80 branches sell and receive stock
-- from Oct-2018, up to 680 days before their "opening"). Keep it, but add the
-- first real activity date and use that as the effective opening date.
-- Decision D3: two branches share the same Arabic name -> unique display name.
ALTER TABLE silver.branches
    ADD COLUMN first_sale_date        DATE,
    ADD COLUMN first_transfer_date    DATE,
    ADD COLUMN effective_opening_date DATE,
    ADD COLUMN opening_date_conflict  BOOLEAN,
    ADD COLUMN branch_display_name    TEXT;

UPDATE silver.branches b
SET first_sale_date = s.first_sale
FROM (SELECT branch_id, MIN(order_date) AS first_sale
      FROM silver.sales_orders GROUP BY branch_id) s
WHERE s.branch_id = b.branch_id;

UPDATE silver.branches b
SET first_transfer_date = t.first_transfer
FROM (SELECT destination_branch_id AS branch_id, MIN(transfer_date) AS first_transfer
      FROM silver.inventory_transfers GROUP BY destination_branch_id) t
WHERE t.branch_id = b.branch_id;

-- LEAST() returns the smallest value and ignores NULLs
UPDATE silver.branches
SET effective_opening_date = LEAST(opening_date, first_sale_date, first_transfer_date),
    opening_date_conflict  = LEAST(first_sale_date, first_transfer_date) < opening_date;

UPDATE silver.branches b
SET branch_display_name = CASE WHEN d.n > 1 THEN b.branch_name_ar || ' (' || b.branch_id || ')'
                               ELSE b.branch_name_ar END
FROM (SELECT branch_id, COUNT(*) OVER (PARTITION BY branch_name_ar) AS n
      FROM silver.branches) d
WHERE d.branch_id = b.branch_id;

-- COMMENT = documentation stored inside the database (pgAdmin shows it,
-- and the AI assistant will read these comments later)
COMMENT ON COLUMN silver.branches.opening_date IS
    'As reported in source. Unreliable: sales start before it for all branches. Use effective_opening_date.';
COMMENT ON COLUMN silver.branches.effective_opening_date IS
    'Earliest of reported opening date, first sale and first stock transfer.';


-- @step: fix_returns
-- Decision D1: 5,650 refunds are bigger than the value of the returned units.
-- Not explained by VAT (ratio 0.87-1.25, median 1.05, not 1.14) and almost all are
-- full-line returns -> generator noise. Keep the original refund, add a capped
-- refund (max = net value of the returned units) and use the capped one in KPIs.
ALTER TABLE silver.sales_returns
    ADD COLUMN returned_value_egp   NUMERIC,   -- net (pre-tax) value of the returned units
    ADD COLUMN returned_cost_egp    NUMERIC,   -- cost of the returned units
    ADD COLUMN refund_capped_egp    NUMERIC,
    ADD COLUMN refund_exceeds_value BOOLEAN;

UPDATE silver.sales_returns r
SET returned_value_egp = i.net_line_egp * r.return_quantity::NUMERIC / NULLIF(i.quantity, 0),
    returned_cost_egp  = i.unit_cost_egp * r.return_quantity
FROM silver.sales_order_items i
WHERE i.sales_line_id = r.sales_line_id;

UPDATE silver.sales_returns
SET refund_capped_egp    = LEAST(refund_amount_egp, returned_value_egp),
    refund_exceeds_value = refund_amount_egp > returned_value_egp + 0.05;

COMMENT ON COLUMN silver.sales_returns.refund_amount_egp IS
    'As reported. ~20% exceed the value of the returned units. Use refund_capped_egp in KPIs.';


-- @step: fix_orders_returns
-- Decision D4: sales_orders.status does not match the returns table (only 560 of
-- 10,728 "Partially returned" orders have returns; 27,940 orders with returns are
-- labelled Completed/Delivered). Derive the return status from the returns table.
ALTER TABLE silver.sales_orders
    ADD COLUMN sold_units     INTEGER,
    ADD COLUMN returned_units INTEGER DEFAULT 0,
    ADD COLUMN refund_egp     NUMERIC DEFAULT 0,
    ADD COLUMN has_return     BOOLEAN,
    ADD COLUMN return_level   TEXT;              -- none / partial / full

UPDATE silver.sales_orders o
SET sold_units = i.units
FROM (SELECT sales_order_id, SUM(quantity) AS units
      FROM silver.sales_order_items GROUP BY sales_order_id) i
WHERE i.sales_order_id = o.sales_order_id;

UPDATE silver.sales_orders o
SET returned_units = r.units,
    refund_egp     = r.refund
FROM (SELECT sales_order_id, SUM(return_quantity) AS units, SUM(refund_capped_egp) AS refund
      FROM silver.sales_returns GROUP BY sales_order_id) r
WHERE r.sales_order_id = o.sales_order_id;

UPDATE silver.sales_orders
SET has_return   = returned_units > 0,
    return_level = CASE WHEN returned_units = 0          THEN 'none'
                        WHEN returned_units >= sold_units THEN 'full'
                        ELSE 'partial' END;

CREATE INDEX ON silver.sales_orders (return_level);

COMMENT ON COLUMN silver.sales_orders.status IS
    'As reported. Unreliable for returns (does not match sales_returns). Use has_return / return_level.';


-- @step: fix_price_index
-- Finding F1: selling prices rise every year vs today's catalog price
-- (avg ratio 0.14 in 2018 -> 1.01 in 2026) = inflation built into the data.
-- A monthly price index lets us compare years in "today's prices":
--     real_value = value / price_index
DROP TABLE IF EXISTS silver.price_index_monthly;
CREATE TABLE silver.price_index_monthly AS
SELECT
    date_trunc('month', i.order_date)::DATE                                 AS month_start,
    AVG(i.unit_price_egp / NULLIF(p.listed_price_egp * s.price_multiplier, 0)) AS price_index,
    COUNT(*)                                                                AS lines
FROM silver.sales_order_items i
JOIN silver.sku_variants s     ON s.sku_id = i.sku_id
JOIN silver.products_catalog p ON p.product_id = s.product_id
GROUP BY 1;
ALTER TABLE silver.price_index_monthly ADD PRIMARY KEY (month_start);

COMMENT ON TABLE silver.price_index_monthly IS
    'Average selling price / current catalog price per month. 1.0 = 2026 catalog prices.';


-- @step: fix_analyze
ANALYZE silver.branches;
ANALYZE silver.sales_returns;
ANALYZE silver.sales_orders;
ANALYZE silver.price_index_monthly;