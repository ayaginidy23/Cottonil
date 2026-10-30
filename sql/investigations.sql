-- =============================================================================
-- investigations.sql  -  Dig into the issues found by quality_checks.sql
-- -----------------------------------------------------------------------------
-- A quality check only says "X rows break the rule". Before deciding how to
-- clean, we need to know WHY. Each step below is one SELECT that tests a
-- hypothesis. The output contains only ids, counts, ratios and dates.
--
-- Executed by etl/investigate.py -> reports/investigation_report.md
-- (You can also copy any single query into pgAdmin and run it there.)
-- =============================================================================


-- @step: 1a_refund_ratio
-- Hypothesis: refunds include 14% VAT, while net_line_egp is BEFORE tax.
-- ratio_per_unit = refund / (line net value of the returned units)
--   ~1.00 -> refund = price without tax
--   ~1.14 -> refund = price + 14% VAT  (then the "error" is not an error)
WITH x AS (
    SELECT
        r.refund_amount_egp,
        i.net_line_egp,
        r.refund_amount_egp
          / NULLIF(i.net_line_egp * r.return_quantity::NUMERIC / i.quantity, 0) AS ratio_per_unit
    FROM silver.sales_returns r
    JOIN silver.sales_order_items i ON i.sales_line_id = r.sales_line_id
)
SELECT
    (refund_amount_egp > net_line_egp + 0.05)                          AS breaks_rule,
    COUNT(*)                                                           AS returns,
    round(MIN(ratio_per_unit), 4)                                      AS min_ratio,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY ratio_per_unit)::NUMERIC, 4) AS median_ratio,
    round(AVG(ratio_per_unit), 4)                                      AS avg_ratio,
    round(MAX(ratio_per_unit), 4)                                      AS max_ratio,
    COUNT(*) FILTER (WHERE abs(ratio_per_unit - 1.00) < 0.01)          AS ratio_about_1_00,
    COUNT(*) FILTER (WHERE abs(ratio_per_unit - 1.14) < 0.01)          AS ratio_about_1_14,
    COUNT(*) FILTER (WHERE ratio_per_unit > 1.15)                      AS ratio_above_1_15
FROM x
GROUP BY 1
ORDER BY 1;

-- @step: 1b_refund_by_reason
-- Does one return reason (e.g. Exchange / Defect claim) cause the high refunds?
SELECT
    r.reason,
    COUNT(*)                                                          AS returns,
    COUNT(*) FILTER (WHERE r.refund_amount_egp > i.net_line_egp + 0.05) AS refund_above_line,
    round(100.0 * COUNT(*) FILTER (WHERE r.refund_amount_egp > i.net_line_egp + 0.05)
          / COUNT(*), 1)                                              AS pct_above
FROM silver.sales_returns r
JOIN silver.sales_order_items i ON i.sales_line_id = r.sales_line_id
GROUP BY r.reason
ORDER BY pct_above DESC;

-- @step: 1c_refund_full_vs_partial
-- Is the problem only in returns where ALL units of the line were returned?
SELECT
    CASE WHEN r.return_quantity = i.quantity THEN 'full line returned'
         ELSE 'part of line returned' END                              AS return_type,
    COUNT(*)                                                          AS returns,
    COUNT(*) FILTER (WHERE r.refund_amount_egp > i.net_line_egp + 0.05) AS refund_above_line
FROM silver.sales_returns r
JOIN silver.sales_order_items i ON i.sales_line_id = r.sales_line_id
GROUP BY 1;


-- @step: 2a_opening_summary
-- Hypothesis: the generator ignored opening dates, so EVERY branch "sells"
-- from the first day of the data (2018-10-19). If sales AND transfers both start
-- before opening for the same branches, the opening_date is what's wrong.
WITH f AS (
    SELECT
        b.branch_id, b.retail_location_type, b.opening_date,
        MIN(o.order_date)                                         AS first_sale,
        COUNT(*) FILTER (WHERE o.order_date < b.opening_date)     AS early_orders,
        COUNT(*)                                                  AS orders
    FROM silver.branches b
    JOIN silver.sales_orders o ON o.branch_id = b.branch_id
    GROUP BY b.branch_id, b.retail_location_type, b.opening_date
)
SELECT
    retail_location_type,
    COUNT(*)                                       AS branches,
    COUNT(*) FILTER (WHERE early_orders > 0)       AS branches_with_early_sales,
    SUM(early_orders)                              AS early_orders,
    SUM(orders)                                    AS all_orders,
    MIN(first_sale)                                AS earliest_first_sale,
    MAX(first_sale)                                AS latest_first_sale,
    MIN(opening_date)                              AS earliest_opening,
    MAX(opening_date)                              AS latest_opening
FROM f
GROUP BY retail_location_type;

-- @step: 2b_opening_per_branch
-- Branches with the most sales before their opening date (ids only)
WITH f AS (
    SELECT
        b.branch_id, b.retail_location_type, b.opening_date,
        MIN(o.order_date)                                         AS first_sale,
        COUNT(*) FILTER (WHERE o.order_date < b.opening_date)     AS early_orders,
        COUNT(*)                                                  AS orders
    FROM silver.branches b
    JOIN silver.sales_orders o ON o.branch_id = b.branch_id
    GROUP BY b.branch_id, b.retail_location_type, b.opening_date
),
t AS (
    SELECT destination_branch_id AS branch_id, MIN(transfer_date) AS first_transfer
    FROM silver.inventory_transfers
    GROUP BY destination_branch_id
)
SELECT
    f.branch_id, f.retail_location_type, f.opening_date, f.first_sale, t.first_transfer,
    f.opening_date - f.first_sale                  AS days_selling_before_opening,
    f.early_orders, f.orders,
    round(100.0 * f.early_orders / f.orders, 1)    AS pct_early
FROM f
LEFT JOIN t ON t.branch_id = f.branch_id
WHERE f.early_orders > 0
ORDER BY f.early_orders DESC
LIMIT 25;

-- @step: 2c_opening_by_channel
-- Are the "early" orders a specific channel (e.g. online orders assigned to a branch)?
SELECT
    o.sales_channel,
    COUNT(*)                                                    AS orders,
    COUNT(*) FILTER (WHERE o.order_date < b.opening_date)       AS early_orders,
    round(100.0 * COUNT(*) FILTER (WHERE o.order_date < b.opening_date) / COUNT(*), 1) AS pct_early
FROM silver.sales_orders o
JOIN silver.branches b ON b.branch_id = o.branch_id
GROUP BY o.sales_channel
ORDER BY orders DESC;


-- @step: 3_duplicate_branches
-- The 2 branches that share a name: are they real duplicates or two outlets?
SELECT
    b.branch_id, b.retail_location_type, b.opening_date,
    (COUNT(*) OVER (PARTITION BY b.address_ar) > 1)  AS same_address_as_twin,
    (SELECT COUNT(*) FROM silver.sales_orders o WHERE o.branch_id = b.branch_id)   AS orders,
    (SELECT COUNT(*) FROM silver.employees e WHERE e.branch_id = b.branch_id)      AS employees,
    (SELECT MIN(order_date) FROM silver.sales_orders o WHERE o.branch_id = b.branch_id) AS first_sale
FROM silver.branches b
WHERE b.branch_name_ar IN (SELECT branch_name_ar FROM silver.branches
                           GROUP BY branch_name_ar HAVING COUNT(*) > 1)
ORDER BY b.branch_id;


-- @step: 4a_status_vs_returns
-- Only 10,728 orders are "Partially returned", but returns exist for 28,500 orders.
-- Do the order statuses match the returns table?
WITH ret AS (
    SELECT sales_order_id, SUM(return_quantity) AS returned_units
    FROM silver.sales_returns
    GROUP BY sales_order_id
)
SELECT
    o.status,
    (ret.sales_order_id IS NOT NULL)  AS has_return_rows,
    COUNT(*)                          AS orders
FROM silver.sales_orders o
LEFT JOIN ret ON ret.sales_order_id = o.sales_order_id
GROUP BY 1, 2
ORDER BY 1, 2;

-- @step: 4b_full_vs_partial_returns
-- Are some orders fully returned (all units back)?
WITH ret AS (
    SELECT sales_order_id, SUM(return_quantity) AS returned_units
    FROM silver.sales_returns GROUP BY sales_order_id
),
sold AS (
    SELECT sales_order_id, SUM(quantity) AS sold_units
    FROM silver.sales_order_items GROUP BY sales_order_id
)
SELECT
    CASE WHEN ret.returned_units >= sold.sold_units THEN 'fully returned'
         ELSE 'partially returned' END     AS return_level,
    COUNT(*)                               AS orders
FROM ret JOIN sold ON sold.sales_order_id = ret.sales_order_id
GROUP BY 1;

-- @step: 4c_status_by_channel
SELECT sales_channel, status, COUNT(*) AS orders
FROM silver.sales_orders
GROUP BY 1, 2
ORDER BY 1, 3 DESC;


-- @step: 5_price_vs_catalog_by_year
-- 99.98% of lines don't sell at catalog price x multiplier. Is it inflation over
-- time (catalog = today's prices, old sales = cheaper)?
SELECT
    EXTRACT(YEAR FROM i.order_date)::INT                                        AS year,
    COUNT(*)                                                                    AS lines,
    round(MIN(i.unit_price_egp / NULLIF(p.listed_price_egp * s.price_multiplier, 0)), 3) AS min_ratio,
    round(AVG(i.unit_price_egp / NULLIF(p.listed_price_egp * s.price_multiplier, 0)), 3) AS avg_ratio,
    round(MAX(i.unit_price_egp / NULLIF(p.listed_price_egp * s.price_multiplier, 0)), 3) AS max_ratio
FROM silver.sales_order_items i
JOIN silver.sku_variants s     ON s.sku_id = i.sku_id
JOIN silver.products_catalog p ON p.product_id = s.product_id
GROUP BY 1
ORDER BY 1;


-- @step: 6_channel_vs_customer
-- Do wholesale orders belong to B2B customers? Who are the guest orders?
SELECT
    o.sales_channel,
    COALESCE(c.customer_segment, 'GUEST (no customer)') AS customer_segment,
    COUNT(*)                                            AS orders
FROM silver.sales_orders o
LEFT JOIN silver.customers c ON c.customer_id = o.customer_id
GROUP BY 1, 2
ORDER BY 1, 3 DESC;


-- @step: 7_catalog_vs_public_reference
-- All 139 products exist in the public catalog (238). Do price and category match?
SELECT
    COUNT(*)                                                         AS products,
    COUNT(*) FILTER (WHERE p.listed_price_egp = r.listed_price_egp)  AS same_price,
    COUNT(*) FILTER (WHERE p.category_en = r.category)               AS same_category,
    (SELECT COUNT(*) FROM silver.product_catalog_public_reference)   AS public_products,
    (SELECT COUNT(DISTINCT category) FROM silver.product_catalog_public_reference) AS public_categories
FROM silver.products_catalog p
JOIN silver.product_catalog_public_reference r ON r.product_id = p.product_id;


-- @step: 8_partial_months
-- Data starts 2018-10-19 and ends 2026-10-18: first and last months are incomplete.
SELECT
    date_trunc('month', order_date)::DATE  AS month,
    COUNT(*)                               AS orders,
    MIN(order_date)                        AS first_day,
    MAX(order_date)                        AS last_day
FROM silver.sales_orders
WHERE order_date < DATE '2018-12-01' OR order_date >= DATE '2026-09-01'
GROUP BY 1
ORDER BY 1;


-- @step: 9_customers_without_orders
-- 10,340 customers never ordered. Are they recent sign-ups (normal) or spread out?
SELECT
    EXTRACT(YEAR FROM c.joined_date)::INT   AS joined_year,
    COUNT(*)                                AS customers,
    COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM silver.sales_orders o
                                       WHERE o.customer_id = c.customer_id)) AS never_ordered
FROM silver.customers c
GROUP BY 1
ORDER BY 1;