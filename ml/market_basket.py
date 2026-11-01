# =============================================================================
# ml/market_basket.py  -  "Bought together" (market basket analysis)
# -----------------------------------------------------------------------------
# Question: when a customer buys product A, which products are in the same order?
#
# Method (association rules, done in SQL because it is just counting):
#   basket          = one sales order, as the set of DISTINCT products in it
#   together(A, B)  = number of orders that contain both A and B
#   support         = together / all orders with 2+ products
#   confidence A->B = together / orders that contain A
#                     ("of the orders with A, how many also had B")
#   lift            = confidence A->B / share of orders that contain B
#                     lift 1   = B appears with A as often as with anything (no link)
#                     lift > 1 = A and B are bought together MORE than by chance
#
# Only pairs seen in at least MIN_TOGETHER orders are kept, so one or two
# accidental orders do not create a rule.
#
# Output: gold.ml_product_pairs (both directions: A->B and B->A), used by
#   - the Product Profitability dashboard ("Bought together" table)
#   - the product page
#   - the Shopping Assistant tool "bought_together" (complete the look)
#
# Usage:  python ml/market_basket.py      (also run by ml/run_ml.py)
# =============================================================================

from sqlalchemy import text

from common import ENGINE, save_metrics

MIN_TOGETHER = 5          # a pair must appear in at least this many orders
TOP_PER_PRODUCT = 10      # keep the best 10 partners per product

SQL = """
DROP TABLE IF EXISTS gold.ml_product_pairs;
CREATE TABLE gold.ml_product_pairs AS
WITH baskets AS (                       -- distinct products per order
    SELECT DISTINCT sales_order_id, product_id
    FROM gold.fact_sales_line
),
multi AS (                              -- only orders with 2+ different products can form a pair
    SELECT sales_order_id FROM baskets GROUP BY 1 HAVING COUNT(*) >= 2
),
b AS (
    SELECT bk.* FROM baskets bk JOIN multi m USING (sales_order_id)
),
n AS (SELECT COUNT(*)::numeric AS orders FROM multi),
item AS (                               -- orders that contain each product
    SELECT product_id, COUNT(*)::numeric AS orders FROM b GROUP BY 1
),
pairs AS (
    SELECT x.product_id AS product_a, y.product_id AS product_b, COUNT(*) AS together
    FROM b x JOIN b y ON y.sales_order_id = x.sales_order_id AND y.product_id <> x.product_id
    GROUP BY 1, 2
    HAVING COUNT(*) >= :min_together
),
scored AS (
    SELECT p.product_a, p.product_b, p.together,
           ROUND(p.together / n.orders, 5)                              AS support,
           ROUND(p.together / ia.orders, 4)                             AS confidence,
           ROUND((p.together / ia.orders) / (ib.orders / n.orders), 3)  AS lift,
           ROW_NUMBER() OVER (PARTITION BY p.product_a
                              ORDER BY (p.together / ia.orders) / (ib.orders / n.orders) DESC,
                                       p.together DESC) AS rank_for_a
    FROM pairs p
    CROSS JOIN n
    JOIN item ia ON ia.product_id = p.product_a
    JOIN item ib ON ib.product_id = p.product_b
),
names AS (
    SELECT product_id, MIN(product_name_ar) AS name_ar, MIN(category) AS category
    FROM gold.dim_product GROUP BY 1
)
SELECT s.product_a, na.name_ar AS product_a_name, na.category AS product_a_category,
       s.product_b, nb.name_ar AS product_b_name, nb.category AS product_b_category,
       s.together, s.support, s.confidence, s.lift, s.rank_for_a
FROM scored s
JOIN names na ON na.product_id = s.product_a
JOIN names nb ON nb.product_id = s.product_b
WHERE s.rank_for_a <= :top;

ALTER TABLE gold.ml_product_pairs ADD PRIMARY KEY (product_a, product_b);
COMMENT ON TABLE gold.ml_product_pairs IS
  'Market basket: products bought in the same order. confidence = share of orders with product_a that also had product_b; lift > 1 means bought together more than by chance. Best 10 partners per product, pairs seen in 5+ orders.';
"""


def main():
    with ENGINE.begin() as conn:
        for stmt in [s for s in SQL.split(";\n") if s.strip()]:
            conn.execute(text(stmt), {"min_together": MIN_TOGETHER, "top": TOP_PER_PRODUCT})
        stats = conn.execute(text("""
            SELECT COUNT(*) AS pairs,
                   COUNT(*) FILTER (WHERE lift >= 1.2) AS strong,
                   COALESCE(MAX(lift), 0) AS max_lift,
                   COALESCE(AVG(lift), 0) AS avg_lift
            FROM gold.ml_product_pairs""")).mappings().one()
        orders = conn.execute(text("""
            SELECT COUNT(*) FROM (SELECT sales_order_id FROM gold.fact_sales_line
                                  GROUP BY 1 HAVING COUNT(DISTINCT product_id) >= 2) t""")).scalar()
    print(f"   orders with 2+ products: {orders:,}")
    print(f"   -> gold.ml_product_pairs: {stats['pairs']:,} rules "
          f"({stats['strong']:,} with lift >= 1.2, max lift {float(stats['max_lift']):.2f})")
    if float(stats["max_lift"]) < 1.2:
        print("   note: no strong pairs - products are combined almost at random in this data.")
    save_metrics("market_basket", {
        "rules": (stats["pairs"], f"pairs seen in {MIN_TOGETHER}+ orders, top {TOP_PER_PRODUCT} per product"),
        "strong_rules": (stats["strong"], "rules with lift >= 1.2"),
        "max_lift": (stats["max_lift"], "highest lift"),
        "avg_lift": (stats["avg_lift"], "average lift (1 = no link)"),
    })


if __name__ == "__main__":
    main()
