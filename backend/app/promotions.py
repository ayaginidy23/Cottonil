# =============================================================================
# promotions.py  -  Current offers (managed by the company, used by the chatbot)
# -----------------------------------------------------------------------------
# Table app.promotions: one row per offer.
#   scope       'category' -> discount on the products of one category
#               'audience' -> discount on products for Men / Women / Kids ...
#               'order'    -> discount on the whole order when it has min_units+ pieces
#   discount_pct  0.15 = 15% off
#   starts_on / ends_on, active   -> only offers that are active today are shown
#
# Who uses it:
#   - the "Offers" page (management adds, pauses and deletes offers)
#   - the Shopping Assistant tool current_offers (tells customers the offers)
#   - the cart (applies the best offer to the order; offers are not combined)
# Wholesale quotes keep their own volume tiers (see shop_tools.b2b_quote).
#
# The first time, a few DEMO offers are created from the real catalog categories
# so the feature can be shown; they are marked "(demo)" and can be deleted.
# =============================================================================

from datetime import date, timedelta

from .db import fetch_all, fetch_one, pool

_ready = False

DDL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.promotions (
    promo_id      SERIAL PRIMARY KEY,
    title_en      TEXT NOT NULL,
    title_ar      TEXT NOT NULL,
    scope         TEXT NOT NULL CHECK (scope IN ('category', 'audience', 'order')),
    target        TEXT,                       -- the category or audience; NULL for 'order'
    min_units     INT NOT NULL DEFAULT 1,     -- for 'order': pieces needed in the order
    discount_pct  NUMERIC NOT NULL CHECK (discount_pct > 0 AND discount_pct <= 0.7),
    starts_on     DATE NOT NULL DEFAULT CURRENT_DATE,
    ends_on       DATE NOT NULL,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _ensure() -> None:
    global _ready
    if _ready:
        return
    with pool.connection() as conn:
        conn.execute(DDL)
        empty = conn.execute("SELECT NOT EXISTS (SELECT 1 FROM app.promotions) AS e").fetchone()["e"]
    if empty:
        _seed_demo()
    _ready = True


def _seed_demo() -> None:
    """Three demo offers built from the categories that really exist in the catalog."""
    cats = [r["category"] for r in fetch_all("""
        SELECT category FROM gold.dim_product GROUP BY 1 ORDER BY COUNT(DISTINCT product_id) DESC LIMIT 2
    """)]
    end = date.today() + timedelta(days=30)
    rows = [("Buy 3 or more pieces: 10% off the order (demo)",
             "اشتري 3 قطع أو أكتر وخد خصم 10% على الأوردر (تجريبي)", "order", None, 3, 0.10)]
    if cats:
        rows.append((f"15% off {cats[0]} (demo)", f"خصم 15% على {cats[0]} (تجريبي)", "category", cats[0], 1, 0.15))
    if len(cats) > 1:
        rows.append((f"20% off {cats[1]} (demo)", f"خصم 20% على {cats[1]} (تجريبي)", "category", cats[1], 1, 0.20))
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.executemany("""
                INSERT INTO app.promotions (title_en, title_ar, scope, target, min_units, discount_pct, ends_on)
                VALUES (%s, %s, %s, %s, %s, %s, %s)""", [(*r, end) for r in rows])


COLUMNS = ("promo_id, title_en, title_ar, scope, target, min_units, discount_pct, starts_on, ends_on, "
           "active, (active AND CURRENT_DATE BETWEEN starts_on AND ends_on) AS running_now")


def all_offers() -> list[dict]:
    _ensure()
    return fetch_all(f"SELECT {COLUMNS} FROM app.promotions ORDER BY running_now DESC, ends_on, promo_id")


def active_offers() -> list[dict]:
    _ensure()
    return fetch_all(f"""
        SELECT {COLUMNS} FROM app.promotions
        WHERE active AND CURRENT_DATE BETWEEN starts_on AND ends_on
        ORDER BY discount_pct DESC""")


def create_offer(o: dict) -> dict:
    _ensure()
    return fetch_one(f"""
        INSERT INTO app.promotions (title_en, title_ar, scope, target, min_units, discount_pct, starts_on, ends_on)
        VALUES (%(title_en)s, %(title_ar)s, %(scope)s, %(target)s, %(min_units)s, %(discount_pct)s,
                %(starts_on)s, %(ends_on)s)
        RETURNING {COLUMNS}""", o)


def set_active(promo_id: int, active: bool) -> dict | None:
    _ensure()
    return fetch_one(f"UPDATE app.promotions SET active = %(a)s WHERE promo_id = %(i)s RETURNING {COLUMNS}",
                     {"a": active, "i": promo_id})


def delete_offer(promo_id: int) -> None:
    _ensure()
    with pool.connection() as conn:
        conn.execute("DELETE FROM app.promotions WHERE promo_id = %(i)s", {"i": promo_id})


def targets() -> dict:
    """Categories and audiences that exist, for the form on the Offers page."""
    return {
        "categories": [r["category"] for r in fetch_all("SELECT DISTINCT category FROM gold.dim_product ORDER BY 1")],
        "audiences": [r["audience"] for r in fetch_all("SELECT DISTINCT audience FROM gold.dim_product ORDER BY 1")],
    }
