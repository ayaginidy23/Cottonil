# Dashboards

## How the app engine works
- Every dashboard is **one YAML file** in `backend/app/apps/`: title, group, description, KPIs, charts. Each KPI or chart is a SQL query on gold with a `{where}` placeholder.
- The backend (`engine.py`) fills `{where}` from the **shared filters**: period, branches and sales channel. Each query declares which column each filter applies to (`columns:`). A filter a query does not declare is ignored for that query, for example the channel filter on costs.
- **KPI comparison:** every KPI is also computed for the previous period of the same length. The change is shown as a relative % for amounts and in **percentage points (pp)** for KPIs that are already a percentage. There is no comparison when the previous period starts before the data (e.g. "All time"). `good: down` makes a decrease green (costs, returns).
- **Complete months only** in monthly trend charts (`dim_date.is_complete_month`), so a running month never looks like a drop.
- Results are cached in memory; `POST /api/apps/reload` re-reads the YAML files.
- Frontend: one generic page renders any app. Chart types: line, area, bar, horizontal bar, donut, table. Every chart has a **table view**, tables have a **CSV export**, and the palette is colour-blind safe.
- **Period presets:** Last 12 months (complete months, the default), Year to date, last full year, All time, or custom dates.

## The 16 dashboards

### Executive Dashboard  ·  _Overview_
`01_executive.yaml`  
One view of sales, profit, customers and returns across all branches and channels.

- **KPIs:** Net sales · Real net sales · Gross margin · Operating profit · Orders · Avg order value · Active customers · Orders with a return
- **Charts:** Monthly net sales - nominal vs real (2026 prices) · Net sales by channel · Net sales by product category · Top 10 branches by operating profit · Net sales by governorate
- **What to look for:** Growth of net sales vs real (inflation-adjusted) sales; growth split into more orders vs higher order value; stable gross margin and return rate.

### Sales Performance  ·  _Sales_
`10_sales.yaml`  
Revenue and units over time, real growth after inflation, retail events (Ramadan, Eid, back to school) and weekdays.

- **KPIs:** Net sales · Units sold (net) · Avg daily sales · Avg selling price / unit
- **Charts:** Yearly sales - nominal vs real (how much growth is inflation?) · Monthly units sold · Avg daily sales by retail event · Avg daily sales by weekday
- **What to look for:** How much of the EGP growth is inflation (nominal vs real by year); the uplift on Ramadan / Eid days and on Thu-Sat.

### Channels & Wholesale  ·  _Sales_
`11_channels.yaml`  
Retail stores, e-commerce and wholesale side by side - share, basket size, guests and the channel scorecard - plus what drives the wholesale / reseller channel (categories, branches, customer types). Wholesale charts always show the wholesale channel, so the channel filter does not apply to them.

- **KPIs:** E-commerce share of sales · Share of total sales · Store (POS) avg order · E-commerce avg order · Wholesale avg order · Guest (unregistered) orders · Orders from B2B customers
- **Charts:** Monthly net sales by channel · Channel scorecard · Wholesale sales by category · Wholesale sales - retail branches vs reseller points · Wholesale orders by customer type · Branches by wholesale sales
- **What to look for:** Wholesale is a small share of orders but a large share of sales (large baskets); e-commerce share; which categories and branches drive wholesale.

### Price & Promotion Intelligence  ·  _Sales_
`12_pricing.yaml`  
Discount depth and its effect on margin, price inflation over time (price index), and discounting by category.

- **KPIs:** Discount rate · Lines sold on discount · Avg discount depth · Margin at full price · Margin on discounted lines
- **Charts:** Price index by month (1.0 = 2026 catalog prices) · Year-on-year price increase · Gross margin by discount depth
- **What to look for:** Yearly price increases (strongest during the currency devaluation years); how margin falls as the discount gets deeper.

### Branch Performance & P&L  ·  _Branches_
`20_branches.yaml`  
How much every branch sells and how much it really earns - gross margin after returns minus operating expenses, payroll and transfer costs (P&L = profit and loss). Costs are not split by sales channel, so the channel filter applies only to the sales KPIs and the retail-vs-reseller chart.

- **KPIs:** Avg net sales per branch · Avg basket · Top 10 branches' share · Operating profit · Operating margin · Operating expenses · Payroll · Cost-to-sales ratio · Loss-making branches
- **Charts:** From gross margin to operating profit · Monthly operating profit vs costs · Top 10 most profitable branches · 10 least profitable branches · Monthly sales - retail branches vs reseller points · Branch scorecard - sales, costs and profit
- **What to look for:** Branches sell almost the same, so profit differences come from costs; the bridge from gross margin to operating profit; the branch scorecard (sort by operating margin).

### New Store Expansion & Site Selection  ·  _Branches_
`22_store_expansion.yaml`  
Where is demand not well served by the branch network? Registered customers and online orders per governorate vs the number of branches. All customers and online orders are in the 21 governorates that already have a branch, so the question is where to add a second branch. (Reported opening dates are unreliable, so new-vs-mature store analysis is not used.)

- **KPIs:** Governorates with a branch · Registered customers per branch
- **Charts:** Demand vs network by governorate (expansion candidates first) · Registered customers per branch by governorate
- **What to look for:** Governorates where one branch serves far more registered customers than the national average - candidates for a second branch.

### Customers - Segments, Value & Churn  ·  _Customers & Marketing_
`30_customers.yaml`  
Who the customers are (RFM segments), how loyal they are, what they are worth, who stopped buying and who to win back. The first KPIs follow the filters; segments, lifetime value and inactivity are calculated on all history up to the last data date. Rule-based (no ML).

- **KPIs:** Active customers · Repeat customers · Sales from registered customers · Champions + Loyal customers · Inactive 12+ months · Avg customer lifetime value · At-risk customers · Lifetime revenue of at-risk customers · Avg days between orders
- **Charts:** Customers by RFM segment · Share of revenue by customer value group · What each segment is worth · Customers by days since last order · Bought again within 12 months - by year of first order · New customers per month (first order) · Win-back list - most valuable at-risk customers
- **What to look for:** Repeat rate and share of sales from registered customers; what each RFM segment is worth; revenue concentration in the top customers; the win-back list of valuable at-risk customers.

### Marketing ROI & Campaigns  ·  _Customers & Marketing_
`32_marketing.yaml`  
Spend, reach, clicks, conversion and cost per order by channel. Revenue per campaign is estimated as attributed orders x the average order value of that month (the data has no direct campaign revenue).

- **KPIs:** Marketing spend · Campaigns · Click-through rate · Click -> order conversion · Cost per attributed order · Estimated ROAS
- **Charts:** Channel performance · Monthly marketing spend
- **What to look for:** Compare channels with each other (cost per order, estimated ROAS); the absolute ROAS is an estimate (no campaign revenue in the data).

### Product Profitability & Margin  ·  _Products_
`40_product_profitability.yaml`  
Margin by product and category, the products that carry the business (Pareto) and the ones with the weakest margin.

- **KPIs:** Gross margin · Gross margin (EGP) · Margin per unit sold · Sales from top 10 products
- **Charts:** Gross margin % by category · Pareto - cumulative share of sales by product rank · Category profitability · Top 15 products by gross margin (EGP)
- **What to look for:** Pareto: a small share of products makes most of the sales; margin is almost the same in every category.

### Size, Colour & Returns  ·  _Products_
`41_size_color_returns.yaml`  
Which sizes and colours sell, the size mix per category (input for buying), and what comes back - return rate, refunds and how fast items are returned. Return reasons in this data are evenly spread (generated), so they are shown for completeness.

- **KPIs:** Best-selling size · Units in the top 3 sizes · Kids sizes share of units · Best-selling colour · Unit return rate · Refunds (capped) · Refunds as % of sales · Fully returned orders · Avg days to return
- **Charts:** Units sold by size · Avg selling price by size · Units sold by colour · Units by size group · How fast items come back · Monthly unit return rate · Return rate by channel · Return reasons · Size curve per category (share of category units)
- **What to look for:** Most units are in three adult sizes; the size curve per category for buying; low and stable return rate; how long after purchase items come back.

### Demand Forecasting & Product Planning  ·  _Products_
`43_forecasting.yaml`  
Demand history, trend and seasonality, plus the ML forecast of units for the next 6 months per category (Holt-Winters or seasonal baseline, whichever was more accurate in the backtest). Forecast items ignore the filters.

- **KPIs:** Forecast - next 6 months (units) · Forecast vs same months last year · Forecast error (backtest MAPE) · Avg units per month · Peak month (avg units) · Seasonality swing
- **Charts:** Total units - last 24 months and 6-month forecast (80% interval) · Forecast by category - next 6 months vs the same months last year · Seasonality index by month (1.0 = average month) · Units sold by year (complete months) · Category demand - latest 12 complete months vs the 12 before (ignores the date filter)
- **What to look for:** Next 6 months forecast with an 80% interval, its backtest error vs the baseline, expected growth per category, seasonality by month.

### Inventory, Replenishment & Transfers  ·  _Inventory & Supply Chain_
`50_inventory_supply.yaml`  
Stock levels and value in branches and warehouses, which branch needs stock now and which has too much (months of cover), and the warehouse-to-branch transfers. Stock is a month-end snapshot, so stock KPIs use the latest month in the selected period.

- **KPIs:** Units in stock (latest month) · Stock value (latest month) · Stock held in warehouses · Months of cover (branches) · Branch-categories to replenish · Branch-categories overstocked · Transfers · Units moved · Transport cost · Cost per unit moved · Transfers completed
- **Charts:** Month-end stock value - nominal vs real (2026 prices) · Units in stock by category (latest month) · Months of cover by category (branches, latest month) · Warehouses (latest month) · Branch-category status (latest month) · Transfer status · Replenishment list - most urgent first · Units moved per month · Main warehouse -> branch flows
- **What to look for:** Stock value nominal vs real (growth is price, not volume); warehouse utilisation (over- vs under-used); branch-category cover with a replenish / overstock action list; transfers.

### Procurement & Imports  ·  _Inventory & Supply Chain_
`51_procurement_imports.yaml`  
Buying the goods - local suppliers (spend, lead times, partial deliveries, payment terms) and imports (what goods really cost once they arrive - customs value plus freight plus duties, in USD). Purchases and imports are generated on a different scale than sales, so they are analysed on their own, not compared with sales.

- **KPIs:** Purchase spend · Purchase orders · Active suppliers · Avg lead time · POs only partly received · Avg payment terms · Import shipments · Landed cost · Freight + duty overhead
- **Charts:** Monthly purchase spend · Landed cost composition by commodity · Supplier scorecard · Import partners
- **What to look for:** Supplier lead time vs payment terms (cash-flow view), partial deliveries, the supplier scorecard; import overhead (freight + duty) on top of goods value.

### Last-Mile Delivery Performance  ·  _Operations_
`60_delivery.yaml`  
E-commerce delivery speed, delays and shipping fees by carrier and governorate (only e-commerce orders are shipped).

- **KPIs:** Shipments · Avg delivery time · Delayed shipments · Delivered within 2 days · Avg shipping fee · Shipping fee / order value
- **Charts:** Delivery time distribution · Carrier scorecard
- **What to look for:** Share of shipments delivered within 2 days vs 5+ days; carriers perform almost the same.

### Workforce Productivity & Store Operations  ·  _Operations_
`61_workforce.yaml`  
Headcount, labour cost and sales per employee - which branches turn payroll into sales most efficiently.

- **KPIs:** Employees paid · Labour cost · Avg monthly pay per employee · Overtime share of pay · Monthly sales per employee · Payroll as % of sales
- **Charts:** Employees by position · Avg monthly pay by position · Pay mix by position · Monthly labour cost · Branch productivity
- **What to look for:** Labour cost and sales per employee. Caution: payroll records do not cover all employees in recent months (see data_limitations.md).

### Loss Prevention & Refund Risk  ·  _Operations_
`62_loss_prevention.yaml`  
Risk signals from returns and refunds - refunds above the value of the items, very fast returns, cash refunds and branches that stand out. (The data has no theft / shrinkage records, so this app focuses on refund risk.)

- **KPIs:** Refunds above item value · Excess refunded (raw data) · Returns within 1 day · Refunds paid in cash
- **Charts:** Top 15 branches by excess refunded · Branch refund-risk table
- **What to look for:** Refunds above the value of the returned items (decision D1), very fast returns, cash refunds, and branches with the highest excess refunded.

## Adding a dashboard
1. Copy an existing YAML file in `backend/app/apps/` and change `id`, `title`, `group`, `order`.
2. Write each KPI as a SQL query returning one column named `value`, and each chart as a SQL query returning the rows to draw (`x` and `series` name the columns).
3. Restart the backend (or `POST /api/apps/reload`). It appears in the sidebar automatically, with no frontend code.
