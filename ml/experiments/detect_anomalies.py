# =============================================================================
# EXPERIMENT - NOT USED IN THE APP. See docs/ml_experiments.md for the results
# and why it was left out.
# ml/detect_anomalies.py  -  Find unusual WEEKS per branch (sales alerts)
# -----------------------------------------------------------------------------
# Version 2. Why weekly and why a log scale?
#   Version 1 worked on DAILY units per branch. A branch sells only a handful of
#   units per day, and one big (e.g. wholesale) order makes a huge jump, so 7% of
#   all branch-days were flagged - all of them spikes, no drops at all. Too many
#   alerts = nobody reads them, and drops (the important ones) were invisible.
#
#   Fixes:
#   1. WEEKLY units per branch: ~7x more volume, much more stable than one day.
#   2. log(1 + units): sales counts are skewed (long tail upward). On a log scale
#      a fall to half and a rise to double are equally far from normal, so drops
#      become detectable too.
#
# Method (robust z-score):
#   normal   = median of the previous 12 weeks (log scale)
#   spread   = MAD of the previous 12 weeks (robust to the anomalies themselves)
#   score    = (this week - normal) / (1.4826 * MAD)
#   anomaly  = |score| >= 3.5  AND  units differ from normal by at least 25%
#
# Output: gold.ml_anomalies (one row per flagged branch-week: Drop or Spike)
# Usage:  python ml/detect_anomalies.py
# =============================================================================

import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # to import ml/common.py

from common import read_sql, save_metrics, write_table

WINDOW_WEEKS = 12
THRESHOLD = 3.5
MIN_CHANGE = 0.25          # at least 25% above / below the normal level


def main():
    df = read_sql("""
        SELECT date_trunc('week', order_date)::date AS week_start, branch_id,
               SUM(net_units) AS units, SUM(net_sales_after_returns_egp) AS net_sales
        FROM gold.mart_sales_daily GROUP BY 1, 2
    """)
    df["week_start"] = pd.to_datetime(df["week_start"])
    bounds = read_sql("SELECT MIN(order_date) AS first_day, MAX(order_date) AS last_day FROM gold.fact_orders")
    first_day = pd.Timestamp(bounds["first_day"].iloc[0])
    last_day = pd.Timestamp(bounds["last_day"].iloc[0])

    # keep only complete weeks (Monday-Sunday fully inside the data period)
    weeks = pd.date_range(df["week_start"].min(), df["week_start"].max(), freq="W-MON")
    weeks = weeks[(weeks >= first_day) & (weeks + pd.Timedelta(days=6) <= last_day)]

    frames = []
    for branch, g in df.groupby("branch_id"):
        g = g.set_index("week_start")[["units", "net_sales"]].astype(float).reindex(weeks, fill_value=0)
        g["branch_id"] = branch
        x = np.log1p(g["units"])
        past = x.shift(1).rolling(WINDOW_WEEKS, min_periods=WINDOW_WEEKS)      # only PAST weeks
        median = past.median()
        mad = past.apply(lambda v: np.median(np.abs(v - np.median(v))), raw=True)
        scale = (1.4826 * mad).where(lambda s: s > 0, past.std()).where(lambda s: s > 0, 0.1)
        g["score"] = (x - median) / scale
        g["expected_units"] = np.expm1(median)
        frames.append(g.rename_axis("week_start").reset_index())
    full = pd.concat(frames, ignore_index=True)

    change = (full["units"] - full["expected_units"]) / full["expected_units"].replace(0, np.nan)
    flagged = full[(full["score"].abs() >= THRESHOLD) & (change.abs() >= MIN_CHANGE)].copy()
    flagged["direction"] = np.where(flagged["score"] > 0, "Spike", "Drop")
    flagged["deviation_pct"] = change[flagged.index]
    out = flagged[["week_start", "branch_id", "direction", "units", "expected_units",
                   "deviation_pct", "score", "net_sales"]].copy()
    out["week_start"] = out["week_start"].dt.date
    out = out.round({"expected_units": 1, "deviation_pct": 3, "score": 2, "net_sales": 0})

    checked = int(full["score"].notna().sum())
    drops, spikes = int((out["direction"] == "Drop").sum()), int((out["direction"] == "Spike").sum())
    print(f"Branch-weeks checked: {checked:,} | anomalies: {len(out):,} "
          f"({len(out) / max(checked, 1):.2%}) | drops {drops}, spikes {spikes}")
    write_table(out, "ml_anomalies",
                f"Unusual branch-weeks: weekly units vs the median of the previous {WINDOW_WEEKS} weeks on a "
                f"log scale, robust z-score (MAD) |score| >= {THRESHOLD} and a change of at least "
                f"{MIN_CHANGE:.0%}. direction = Drop or Spike. week_start = Monday of the week.",
                primary_key=["week_start", "branch_id"])
    save_metrics("anomalies", {
        "branch_weeks_checked": (checked, f"{WINDOW_WEEKS}-week rolling robust z-score on log units"),
        "anomalies": (len(out), f"|score| >= {THRESHOLD} and change >= {MIN_CHANGE:.0%}"),
        "anomaly_rate": (len(out) / max(checked, 1), "Share of branch-weeks flagged"),
        "drops": (drops, "Weeks clearly below normal"),
        "spikes": (spikes, "Weeks clearly above normal"),
    })


if __name__ == "__main__":
    main()