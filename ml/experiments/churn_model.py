# =============================================================================
# EXPERIMENT - NOT USED IN THE APP. See docs/ml_experiments.md for the results
# and why it was left out.
# ml/churn_model.py  -  Predict which customers are likely to stop buying
# -----------------------------------------------------------------------------
# Definition: a customer "churns" if they place NO order in the next 180 days.
#
# How we get labelled training data from history (no future leakage):
#   cutoff = last data date - 180 days
#   features = what we knew about each customer UP TO the cutoff
#   label    = did they order in the 180 days AFTER the cutoff? (no -> churned = 1)
# Then the trained model scores every customer using features up to TODAY.
#
# Features: recency, frequency, monetary (real, inflation-adjusted), tenure,
# average order value, return share, e-commerce share, wholesale share,
# discount share, number of categories bought, segment.
#
# Model: Gradient Boosting (scikit-learn) - strong on tabular data.
# Evaluation on a 25% hold-out set: ROC-AUC (0.5 = random, 1.0 = perfect),
# precision / recall of the "high risk" group, compared with a simple rule
# ("churn if recency > 90 days").
#
# Output tables:
#   gold.ml_churn_scores        : churn probability + risk band per customer
#   gold.ml_feature_importance  : which features drive churn
#   gold.ml_model_metrics       : AUC, precision, recall vs the rule
#
# Usage:  python ml/churn_model.py
# =============================================================================

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # to import ml/common.py

from common import read_sql, save_metrics, write_table

HORIZON_DAYS = 180

FEATURES_SQL = """
WITH o AS (
    SELECT * FROM gold.fact_orders
    WHERE customer_key <> 'GUEST' AND order_date <= :as_of
),
cats AS (
    SELECT s.customer_key, COUNT(DISTINCT p.category) AS categories
    FROM gold.fact_sales_line s JOIN gold.dim_product p ON p.sku_id = s.sku_id
    WHERE s.customer_key <> 'GUEST' AND s.order_date <= :as_of
    GROUP BY 1
)
SELECT o.customer_key,
       (:as_of)::date - MAX(o.order_date)                         AS recency_days,
       COUNT(*)                                                   AS frequency,
       SUM(o.real_net_sales_egp)                                  AS monetary_real,
       (:as_of)::date - MIN(o.order_date)                         AS tenure_days,
       AVG(o.real_net_sales_egp)                                  AS avg_order_real,
       AVG(CASE WHEN o.has_return THEN 1.0 ELSE 0 END)            AS return_share,
       AVG(CASE WHEN o.sales_channel = 'E-commerce' THEN 1.0 ELSE 0 END)           AS ecom_share,
       AVG(CASE WHEN o.sales_channel = 'Wholesale / reseller' THEN 1.0 ELSE 0 END) AS wholesale_share,
       AVG(CASE WHEN o.discount_egp > 0 THEN 1.0 ELSE 0 END)      AS discount_share,
       COUNT(*) FILTER (WHERE o.order_date > (:as_of)::date - 180) AS orders_last_180d,
       MAX(c.categories)                                          AS categories,
       MAX(CASE WHEN dc.customer_segment = 'B2B reseller' THEN 1 ELSE 0 END) AS is_b2b
FROM o
LEFT JOIN cats c ON c.customer_key = o.customer_key
JOIN gold.dim_customer dc ON dc.customer_key = o.customer_key
GROUP BY o.customer_key
"""

FEATURES = ["recency_days", "frequency", "monetary_real", "tenure_days", "avg_order_real",
            "return_share", "ecom_share", "wholesale_share", "discount_share",
            "orders_last_180d", "categories", "is_b2b"]


def main():
    last_date = read_sql("SELECT MAX(order_date) AS d FROM gold.fact_orders")["d"].iloc[0]
    cutoff = last_date - pd.Timedelta(days=HORIZON_DAYS)
    print(f"Last data date {last_date} | training cutoff {cutoff}")

    # ---------------- training set (features up to cutoff, label after) ----------------
    train_df = read_sql(FEATURES_SQL, as_of=cutoff)
    active_after = set(read_sql(
        "SELECT DISTINCT customer_key FROM gold.fact_orders WHERE order_date > :c AND order_date <= :l",
        c=cutoff, l=last_date)["customer_key"])
    train_df["churned"] = (~train_df["customer_key"].isin(active_after)).astype(int)
    print(f"Training customers: {len(train_df):,} | churn rate {train_df['churned'].mean():.1%}")

    X = train_df[FEATURES].astype(float).fillna(0)
    y = train_df["churned"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    model = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                                       subsample=0.8, random_state=42)
    model.fit(X_tr, y_tr)

    # ---------------- evaluation ----------------
    proba = model.predict_proba(X_te)[:, 1]
    auc = roc_auc_score(y_te, proba)
    pred = (proba >= 0.5).astype(int)
    rule = (X_te["recency_days"] > 90).astype(int)            # simple business rule to beat
    metrics = {
        "roc_auc": (auc, "Hold-out ROC-AUC (0.5 random, 1.0 perfect)"),
        "roc_auc_rule": (roc_auc_score(y_te, X_te["recency_days"]), "AUC of recency alone"),
        "precision": (precision_score(y_te, pred, zero_division=0), "Of predicted churners, share that churned"),
        "recall": (recall_score(y_te, pred, zero_division=0), "Of real churners, share we caught"),
        "precision_rule": (precision_score(y_te, rule, zero_division=0), "Rule: recency > 90 days"),
        "recall_rule": (recall_score(y_te, rule, zero_division=0), "Rule: recency > 90 days"),
        "train_churn_rate": (y.mean(), f"Churn = no order in {HORIZON_DAYS} days after cutoff"),
    }
    print(f"Hold-out ROC-AUC {auc:.3f} (recency alone {metrics['roc_auc_rule'][0]:.3f})")
    save_metrics("churn", metrics)

    imp = pd.DataFrame({"feature": FEATURES, "importance": model.feature_importances_})
    write_table(imp.sort_values("importance", ascending=False), "ml_feature_importance",
                "Feature importance of the churn model (Gradient Boosting). Higher = more influence.",
                primary_key=["feature"])

    # ---------------- score every customer as of today ----------------
    model.fit(X, y)                                           # refit on all labelled data
    now_df = read_sql(FEATURES_SQL, as_of=last_date)
    now_df["churn_probability"] = model.predict_proba(now_df[FEATURES].astype(float).fillna(0))[:, 1]
    now_df["risk_band"] = pd.cut(now_df["churn_probability"], [-0.01, 0.4, 0.7, 1.01],
                                 labels=["Low", "Medium", "High"]).astype(str)
    out = now_df[["customer_key", "churn_probability", "risk_band", "recency_days", "frequency",
                  "monetary_real", "orders_last_180d"]].copy()
    out["churn_probability"] = out["churn_probability"].round(4)
    write_table(out, "ml_churn_scores",
                f"Churn model scores per customer as of the last data date: probability of no order "
                f"in the next {HORIZON_DAYS} days, risk_band Low (<0.4) / Medium / High (>=0.7). "
                "monetary_real is inflation-adjusted lifetime value.",
                primary_key=["customer_key"])
    print(out["risk_band"].value_counts().to_string())


if __name__ == "__main__":
    main()