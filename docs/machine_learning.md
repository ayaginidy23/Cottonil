# Machine learning

**Rule:** a model is shown in the app only if it clearly beats a simple baseline on held-out data.

| Model | Used? | Why |
|---|---|---|
| Demand forecast (Holt-Winters per category) | **Yes** | Lower backtest error than the seasonal-naive baseline for the total and for every category |
| Market basket ("bought together") | No (calculated, not shown) | Lift is about 1 for every pair: products are combined almost at random in this data, so the rules carry no real signal |
| Churn prediction (gradient boosting) | No | No better than random guessing on this data |
| Sales anomaly detection (robust z-score) | No | Too many alerts and no meaningful drops, so the alerts did not point to real events |

Run the models used by the app (forecast + market basket) with `python ml/run_ml.py`. It also drops the output tables of the
experiments so nothing in the app or the AI can read them by mistake.

---

## Demand forecast — `ml/forecast_demand.py`

**Question:** how many units will each category sell in the next 6 months?

**Data:** monthly **net units** (after returns) per category and in total, from `gold.mart_sales_daily`,
**complete months only**.
- **Units, not EGP:** prices rose several times over the period (finding F1). An EGP forecast would mix
  inflation with demand.

**Methods compared per series:**
- **Holt-Winters (exponential smoothing):** level + damped trend + additive yearly seasonality (12 months).
- **Seasonal naive (baseline):** "the same month last year".

**Backtest:**
1. Hide the last 6 complete months.
2. Fit on the rest and forecast those 6 months.
3. Measure **MAPE** (mean absolute percentage error) against what really happened.
4. For each category, keep the method with the lower error (model selection).

**Final forecast:** refit on all history, forecast 6 months ahead, and add an **80% interval** around the forecast.

**Output:**
- `gold.ml_forecast_monthly`: history + forecast, interval, method.
- `gold.ml_model_metrics`: model vs baseline MAPE.

The Forecasting dashboard shows both, so the user sees how accurate the model was before trusting it.

---

## Market basket — `ml/market_basket.py`

**Question:** when a customer buys product A, which products are in the same order?

**Method (association rules, in SQL):**
- basket = one sales order as the set of distinct products; only orders with 2+ products count
- `support` = orders with A and B / all baskets
- `confidence` A -> B = orders with A and B / orders with A
- `lift` = confidence / share of baskets with B. **1 = no link** (B comes with A as often as with anything);
  above 1 = bought together more than by chance
- a pair needs at least 5 orders together; the best 10 partners per product are kept

**Output:** `gold.ml_product_pairs` (both directions) and the number of rules and maximum / average lift in
`gold.ml_model_metrics`.

**Result and decision:** the lift is close to 1 for every pair (the top partners of most products are the
same few best-sellers), which means there is no real "bought together" pattern in this data. Following the
rule at the top of this page, the rules are **not shown** in the dashboards or on the product page. The
Shopping Assistant's "complete the look" (`bought_together`) only uses a rule when its lift is at least
1.05; otherwise, which is the case here, it suggests matching items of other categories for the same
audience and says so. On real behavioural data the same script would show real pairs without changes.

---

## Experiments not used — `ml/experiments/`

### Churn prediction (`churn_model.py`)
- **Set-up:** cutoff date = last date − 180 days. Features (recency, frequency, real monetary value, tenure, average order, return / discount / e-commerce / wholesale shares, number of categories, B2B flag) are taken
  before the cutoff; the label is "no order after the cutoff". Gradient boosting, hold-out ROC-AUC.
- **Result:** AUC about 0.5, which means no signal; even recency alone did not separate the groups.
  Purchase timing in the generated data looks random.
- Also, customers buy on average less often than every 180 days, so "no order in 180 days" is a
  normal gap, not churn.
- **What the app shows instead:** rule-based **Inactive 12+ months** and RFM segments (At risk,
  Hibernating, ...). These are transparent and correct by definition.

### Sales anomalies (`detect_anomalies.py`)
- **Method:** weekly units per branch on a log scale; robust z-score against a rolling 12-week median
  and MAD; an alert needs both a high score and a minimum % change.
- **Result:** the alerts did not correspond to real events, so the Alerts dashboard was removed.

The experiment code is kept to show the method. On real behavioural data it could be re-tested
unchanged.
