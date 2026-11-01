// =============================================================================
// SimulatorPage.jsx - What-if: "what happens if we give X% discount?"
// -----------------------------------------------------------------------------
// Starting point (from the database): the last 12 complete months of a category -
// units, net sales, cost of goods. The calculation runs in the browser so the
// sliders update instantly:
//   new price = price x (1 - discount)
//   new units = units x (1 - discount) ^ elasticity          (constant elasticity)
//   sales     = new price x new units,   margin = sales - unit cost x new units
// Elasticity = how strongly customers react to price: -1.5 means 10% cheaper ->
// about 17% more units. It is an ASSUMPTION the manager sets (the generated data
// cannot measure it reliably), so the page also shows the break-even discount:
// the biggest discount that still keeps the same gross margin in EGP.
// =============================================================================
import { useEffect, useMemo, useState } from 'react'
import ChartCard from '../components/ChartCard.jsx'
import { api } from '../lib/api.js'
import { useFilters } from '../lib/filters.jsx'
import { fmt } from '../lib/format.js'
import { useLang } from '../lib/i18n.jsx'

function scenario(base, d, e) {
  const units = Number(base.units) || 0
  if (!units) return null
  const price = Number(base.net_sales) / units
  const cost = Number(base.cogs) / units
  const newUnits = units * (1 - d) ** e
  const sales = price * (1 - d) * newUnits
  const margin = sales - cost * newUnits
  return { units: newUnits, sales, margin, marginPct: sales ? margin / sales : 0, price: price * (1 - d) }
}

function breakEven(base, e) {
  const now = scenario(base, 0, e)
  let best = 0
  for (let d = 0.005; d <= 0.7; d += 0.005) {
    const s = scenario(base, d, e)
    if (s && s.margin >= now.margin) best = d
  }
  return best
}

const pctChange = (a, b) => (b ? a / b - 1 : 0)

export default function SimulatorPage() {
  const { filters, ready } = useFilters()
  const { lang, tl, t } = useLang()
  const ar = lang === 'ar'
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [cat, setCat] = useState('All categories')
  const [discount, setDiscount] = useState(0.1)
  const [elasticity, setElasticity] = useState(-1.5)

  useEffect(() => {
    if (!ready) return
    api.simulatorBaseline(12, filters).then(setData).catch((e) => setError(e.message))
  }, [filters.branches, filters.channels, ready])   // eslint-disable-line react-hooks/exhaustive-deps

  const base = data?.categories.find((c) => c.category === cat) || data?.categories[0]
  const now = base && scenario(base, 0, elasticity)
  const sim = base && scenario(base, discount, elasticity)
  const be = base ? breakEven(base, elasticity) : 0

  const curve = useMemo(() => {
    if (!base) return []
    const rows = []
    for (let i = 0; i <= 50; i += 2.5) {
      const s = scenario(base, i / 100, elasticity)
      rows.push({ discount: `${i}%`, sales: s.sales, margin: s.margin })
    }
    return rows
  }, [base, elasticity])

  if (error) return <div className="error-box page"><strong>{t('loadError')}</strong><code>{error}</code></div>
  if (!data || !base) return <div className="app-page"><div className="skeleton title" /><div className="card skeleton tall" /></div>

  const rows = [
    ['Units sold (net)', 'number', now.units, sim.units],
    ['Avg selling price / unit', 'egp', now.price, sim.price],
    ['Net sales', 'egp', now.sales, sim.sales],
    ['Gross margin (EGP)', 'egp', now.margin, sim.margin],
    ['Margin %', 'pct', now.marginPct, sim.marginPct],
  ]
  const dUnits = pctChange(sim.units, now.units)
  const dSales = pctChange(sim.sales, now.sales)
  const dMargin = pctChange(sim.margin, now.margin)
  const p = (v) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`
  const el = elasticity.toFixed(1)
  const beEn = be > 0 ? `Discounts above ${(be * 100).toFixed(1)}% lose gross margin in EGP.`
    : 'At this elasticity any extra discount loses gross margin in EGP (the extra units do not pay for the lower price).'
  const beAr = be > 0 ? `أي خصم أكبر من ${(be * 100).toFixed(1)}% بيخسّرنا من مجمل الربح بالجنيه.`
    : 'بالمرونة دي أي خصم زيادة بيقلل مجمل الربح بالجنيه (القطع الزيادة مش بتعوّض السعر الأقل).'
  const summaryEn = `With ${(discount * 100).toFixed(1)}% extra discount and elasticity ${el}, units ${p(dUnits)}, net sales ${p(dSales)} and gross margin ${p(dMargin)}. ${beEn}`
  const summaryAr = `بخصم إضافي ${(discount * 100).toFixed(1)}% ومرونة ${el}: القطع ${p(dUnits)}، صافي المبيعات ${p(dSales)}، ومجمل الربح ${p(dMargin)}. ${beAr}`

  return (
    <div className="app-page">
      <div className="page-head">
        <div>
          <div className="eyebrow">{ar ? 'أدوات الذكاء الاصطناعي' : 'AI Tools'}</div>
          <h1>{t('simulator')}</h1>
          <p className="muted">
            {ar ? `لو عملنا خصم، هنكسب ولا هنخسر؟ نقطة البداية: آخر 12 شهر كامل (${data.categories[0].from_month} ← ${data.categories[0].to_month}). المرونة افتراض انت بتحدده.`
              : `If we give a discount, do we win or lose? Starting point: the last 12 complete months (${data.categories[0].from_month} → ${data.categories[0].to_month}). Elasticity is an assumption you set.`}
          </p>
        </div>
      </div>

      <section className="card sim-controls">
        <label>
          <span className="kpi-label">{ar ? 'الفئة' : 'Category'}</span>
          <select className="input select" value={cat} onChange={(e) => setCat(e.target.value)}>
            {data.categories.map((c) => <option key={c.category} value={c.category}>{tl(c.category)}</option>)}
          </select>
        </label>
        <label>
          <span className="kpi-label">{ar ? 'خصم إضافي' : 'Extra discount'}: <strong>{(discount * 100).toFixed(1)}%</strong></span>
          <input type="range" min="0" max="0.5" step="0.005" value={discount} onChange={(e) => setDiscount(Number(e.target.value))} />
          <span className="muted small">{ar ? 'الخصم الحالي في المتوسط' : 'Current average discount'}: {fmt(base.current_discount, 'pct')}</span>
        </label>
        <label>
          <span className="kpi-label">{ar ? 'مرونة السعر' : 'Price elasticity'}: <strong>{elasticity}</strong></span>
          <input type="range" min="-4" max="-0.2" step="0.1" value={elasticity} onChange={(e) => setElasticity(Math.round(Number(e.target.value) * 10) / 10)} />
          <span className="muted small">
            {ar ? `${elasticity} = لو السعر قل 10% القطع تزيد حوالي ${((0.9 ** elasticity - 1) * 100).toFixed(0)}%`
              : `${elasticity} = 10% cheaper → about ${((0.9 ** elasticity - 1) * 100).toFixed(0)}% more units`}
          </span>
        </label>
      </section>

      <section className={`card sim-verdict ${dMargin >= 0 ? 'win' : 'lose'}`}>
        <strong>{dMargin >= 0 ? (ar ? 'الخصم ده بيزود الربح' : 'This discount increases profit') : (ar ? 'الخصم ده بيقلل الربح' : 'This discount reduces profit')}</strong>
        <p dir={ar ? 'rtl' : 'ltr'}>{ar ? summaryAr : summaryEn}</p>
        <p className="muted small">{ar ? 'خصم التعادل' : 'Break-even discount'}: {(be * 100).toFixed(1)}%</p>
      </section>

      <section className="chart-grid">
        <div className="card chart w-half">
          <div className="chart-head"><h3>{ar ? 'الوضع الحالي مقابل السيناريو (12 شهر)' : 'Now vs scenario (12 months)'}</h3></div>
          <table className="table">
            <thead><tr><th /><th className="num">{ar ? 'دلوقتي' : 'Now'}</th><th className="num">{ar ? 'السيناريو' : 'Scenario'}</th><th className="num">{ar ? 'الفرق' : 'Change'}</th></tr></thead>
            <tbody>
              {rows.map(([label, f, a, b]) => (
                <tr key={label}>
                  <td>{tl(label)}</td>
                  <td className="num">{fmt(a, f, { compact: false })}</td>
                  <td className="num">{fmt(b, f, { compact: false })}</td>
                  <td className={`num ${(f === 'pct' ? b - a : b / a - 1) >= 0 ? 'good-text' : 'error-text'}`}>
                    {f === 'pct' ? `${((b - a) * 100).toFixed(1)} pp` : p(pctChange(b, a))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ChartCard chart={{ id: 'curve', title: 'Net sales and gross margin by discount', type: 'line', width: 'half',
          format: 'egp', x: 'discount', data: curve,
          series: [{ key: 'sales', label: 'Net sales' }, { key: 'margin', label: 'Gross margin' }] }} />
      </section>
      <p className="muted small">
        {ar ? 'ملحوظة: المحاكي بيفترض إن المرونة ثابتة وإن التكلفة للقطعة ثابتة، ومش بيحسب سحب المبيعات من منتجات تانية أو من شهور جاية.'
          : 'Note: the simulator assumes a constant elasticity and a constant unit cost, and ignores sales pulled from other products or from future months.'}
      </p>
    </div>
  )
}
