# Data limitations

The products, names and prices are real (public catalog). The transactions are partly generated. Generated
data has typical signs: some fields are perfectly uniform, and some tables are not connected to each
other. The platform labels these limits instead of presenting them as insights.

| Area | What we see | How it is handled |
|---|---|---|
| Uniform categories | Return reasons, refund methods, age bands, colours, carriers, expense categories, marketing audiences and governorates are spread almost equally | Not ranked as insights; many such charts were removed. Dashboard descriptions say so where relevant |
| Margin | Gross margin is almost identical for every product, category and channel | Profit differences are explained by volume and costs, not pricing |
| Branches | Branches sell almost the same; reported opening dates are wrong (D2) | Effective opening date; new-vs-mature store analysis is not used |
| Order status | Does not match the returns table (D4) | Return status derived from the returns table |
| Refunds | A share of refunds exceed the value of the returned items, evenly across methods and channels (D1) | Refunds capped in all KPIs; the raw excess is shown in Loss Prevention as a data-quality signal, not as fraud |
| Channel vs customer | Wholesale orders are not linked to B2B customers (F8) | Wholesale analysed by sales channel |
| Channel mix over time | Channel shares are flat for all years (no shift to online) | Shown as is; no trend claimed |
| Delivery status | The "delayed" flag does not match the actual delivery days | Delivery speed is taken from the dates |
| Stock-out risk score | A source score that does not match stock vs demand | Removed; months of cover (stock ÷ recent sales) is used instead |
| Purchases and imports | Generated on a different scale from sales; lead times and overheads are almost constant | Analysed on their own; never compared with sales |
| Transfers and marketing spend | Flat over time while sales grow | Shown as is; no growth claims |
| Marketing ROAS | Attributed orders are high, so the estimated ROAS is unrealistic in absolute terms | Labelled an estimate; use it to compare channels only |
| Payroll | Payroll records do not cover all employees, especially in recent months | Workforce KPIs and branch P&L payroll may be understated; flagged where shown |
| Partial months | First and last months are incomplete (F7) | Monthly charts use complete months; KPI comparison is disabled when the previous period starts before the data |
| Inflation | Prices rise strongly over the years (F1) | Real (2026-price) values in Sales, Pricing and Inventory; the forecast uses units |
| Store policy | No official policy text in the data | The chatbot uses a demo knowledge base, clearly labelled as demo |

## Why this matters
A dashboard that turns random differences into "insights" would mislead decisions. The checks,
investigations and labels above keep the conclusions to what the data can really support. They also show
exactly where real data would add value: return reasons, delivery status, campaign revenue and payroll.
