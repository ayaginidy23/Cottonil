# =============================================================================
# ml/run_ml.py  -  Run the ML models used by the app
# -----------------------------------------------------------------------------
# Used by the app: the demand forecast (it clearly beats the baseline, see
# docs/machine_learning.md) and the market basket "bought together" rules. The churn and anomaly experiments live in
# ml/experiments/ and are NOT run here, because on this generated data they
# give no reliable signal. Their old output tables are removed so nothing in the
# app or the AI assistant can read them by mistake.
#
# Usage:  python ml/run_ml.py
# =============================================================================

import time

from sqlalchemy import text

import forecast_demand
import market_basket
from common import ENGINE

if __name__ == "__main__":
    with ENGINE.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gold.ml_churn_scores, gold.ml_feature_importance, gold.ml_anomalies"))
        conn.execute(text("""
            DO $$ BEGIN
                IF to_regclass('gold.ml_model_metrics') IS NOT NULL THEN
                    DELETE FROM gold.ml_model_metrics WHERE model IN ('churn', 'anomalies');
                END IF;
            END $$;"""))
    print("Removed the old churn / anomaly tables (experiments not used in the app).")

    print("\n=== Demand forecast (Holt-Winters per category) ===")
    t0 = time.time()
    forecast_demand.main()
    print(f"   done in {time.time() - t0:.1f}s")

    print("\n=== Market basket (bought together) ===")
    t0 = time.time()
    market_basket.main()
    print(f"   done in {time.time() - t0:.1f}s")
    print("\nDone. Restart the backend (or POST /api/apps/reload) to see the forecast.")
