# =============================================================================
# ml/forecast_demand.py  -  Monthly demand forecast (units) per product category

# =============================================================================

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from common import read_sql, save_metrics, write_table

warnings.filterwarnings("ignore")        # statsmodels prints many convergence notes
HORIZON = 6                              # months to forecast
TEST_MONTHS = 6                          # months held out for the backtest


def load_history() -> pd.DataFrame:
    """Net units per category per COMPLETE month (partial first/last months excluded)."""
    df = read_sql("""
        SELECT s.month_start, p.category, SUM(s.quantity - s.returned_units) AS units
        FROM gold.fact_sales_line s
        JOIN gold.dim_product p ON p.sku_id = s.sku_id
        JOIN gold.dim_date d ON d.date_key = s.month_start
        WHERE d.is_complete_month
        GROUP BY 1, 2
    """)
    df["month_start"] = pd.to_datetime(df["month_start"])
    wide = df.pivot_table(index="month_start", columns="category", values="units", fill_value=0)
    wide = wide.asfreq("MS", fill_value=0)                       # every month present
    wide["TOTAL"] = wide.sum(axis=1)
    return wide


def fit(series: pd.Series):
    """Holt-Winters with damped trend + yearly seasonality (needs 2+ years of data)."""
    seasonal = "add" if len(series) >= 24 else None
    model = ExponentialSmoothing(
        series.astype(float), trend="add", damped_trend=True, seasonal=seasonal,
        seasonal_periods=12 if seasonal else None, initialization_method="estimated",
    )
    return model.fit(optimized=True)


def mape(actual, predicted) -> float:
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    mask = actual > 0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask]))) if mask.any() else np.nan


def main():
    wide = load_history()
    print(f"History: {len(wide)} complete months x {wide.shape[1] - 1} categories (+ TOTAL)")

    # ---------------- 1) backtest ----------------
    model_err, naive_err, winner = {}, {}, {}
    for cat in wide.columns:
        y = wide[cat]
        train, test = y.iloc[:-TEST_MONTHS], y.iloc[-TEST_MONTHS:]
        if len(train) < 24:
            continue
        pred = fit(train).forecast(TEST_MONTHS)
        naive = y.shift(12).iloc[-TEST_MONTHS:]                  # same month last year
        model_err[cat] = mape(test, pred)
        naive_err[cat] = mape(test, naive)
        winner[cat] = "holt_winters" if model_err[cat] <= naive_err[cat] else "seasonal_naive"
    total_mape, total_naive = model_err.get("TOTAL", np.nan), naive_err.get("TOTAL", np.nan)
    cat_mape = np.nanmean([v for k, v in model_err.items() if k != "TOTAL"])
    cat_naive = np.nanmean([v for k, v in naive_err.items() if k != "TOTAL"])
    print(f"Backtest MAPE  total: model {total_mape:.1%} vs baseline {total_naive:.1%}")
    print(f"               avg per category: model {cat_mape:.1%} vs baseline {cat_naive:.1%}")
    best = {c: min(model_err[c], naive_err[c]) for c in model_err}
    sel_mape = np.nanmean([v for k, v in best.items() if k != "TOTAL"])
    print(f"               with per-category selection: {sel_mape:.1%} "
          f"(Holt-Winters chosen for {sum(v == 'holt_winters' for v in winner.values())}/{len(winner)})")

    # ---------------- 2) final forecast on all history ----------------
    rows = []
    for cat in wide.columns:
        y = wide[cat]
        for month, units in y.items():                            # history
            rows.append({"month_start": month.date(), "category": cat, "actual_units": float(units),
                         "forecast_units": None, "lower_80": None, "upper_80": None, "is_forecast": False,
                         "method": None})
        method = winner.get(cat, "holt_winters")
        future = pd.date_range(y.index[-1] + pd.offsets.MonthBegin(1), periods=HORIZON, freq="MS")
        if method == "holt_winters":
            res = fit(y)
            fc = res.forecast(HORIZON).clip(lower=0)
            residuals = y.values - res.fittedvalues.values
        else:                                                     # same month last year
            fc = pd.Series([float(y.get(m - pd.DateOffset(years=1), y.iloc[-12])) for m in future], index=future)
            residuals = (y - y.shift(12)).dropna().values
        # 80% interval from the spread of the past errors (simple and honest)
        sigma = float(np.std(residuals))
        for h, (month, value) in enumerate(fc.items(), start=1):
            width = 1.2816 * sigma * np.sqrt(h)                   # grows with the horizon
            rows.append({"month_start": month.date(), "category": cat, "actual_units": None,
                         "forecast_units": round(float(value), 1),
                         "lower_80": round(max(float(value) - width, 0), 1),
                         "upper_80": round(float(value) + width, 1), "is_forecast": True,
                         "method": method})

    out = pd.DataFrame(rows)
    write_table(out, "ml_forecast_monthly",
                "Monthly net units per product category (and TOTAL): actual history + 6-month "
                "forecast with 80% interval. method = holt_winters or seasonal_naive (best backtest per "
                "category). is_forecast = true for future months.",
                primary_key=["month_start", "category"])
    save_metrics("demand_forecast", {
        "mape_total": (total_mape, f"Backtest on last {TEST_MONTHS} months, total units"),
        "mape_total_baseline": (total_naive, "Seasonal naive (same month last year)"),
        "mape_category_avg": (cat_mape, "Average MAPE over categories"),
        "mape_category_baseline": (cat_naive, "Seasonal naive average over categories"),
        "mape_category_selected": (sel_mape, "Average MAPE using the best method per category"),
    })


if __name__ == "__main__":
    main()
