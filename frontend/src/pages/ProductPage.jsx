// =============================================================================
// ProductPage.jsx - One product: photo, KPIs, monthly units, sizes, colours,
//   best branches and the demand forecast of its category.
//   Follows the global filters; "Download PDF" prints it with bilingual titles.
// =============================================================================
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink, FileDown, ImageOff } from 'lucide-react'
import ChartCard from '../components/ChartCard.jsx'
import KpiCard from '../components/KpiCard.jsx'
import { api } from '../lib/api.js'
import { useFilters } from '../lib/filters.jsx'
import { fmt } from '../lib/format.js'
import { useLang } from '../lib/i18n.jsx'
import { PrintHeader } from './AppPage.jsx'

export default function ProductPage() {
  const { productId } = useParams()
  const { filters, ready } = useFilters()
  const { lang, tl, t } = useLang()
  const ar = lang === 'ar'
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!ready) return
    setError(null)
    api.product(productId, filters).then(setData).catch((e) => setError(e.message))
  }, [productId, filters, ready])

  if (error) return <div className="error-box page"><strong>{t('loadError')}</strong><code>{error}</code></div>
  if (!data) return <div className="app-page"><div className="skeleton title" /><div className="card skeleton tall" /></div>

  const { info, kpis } = data
  const kpi = (id, label, value, format, good = 'up') => ({ id, label, value, format, good, change_pct: null })
  const forecast = data.category_forecast.map((r) => ({ ...r, actual_units: r.actual_units, forecast_units: r.is_forecast ? r.forecast_units : null }))

  return (
    <div className="app-page">
      <PrintHeader title={`${info.name} (${info.product_id})`} subtitle={`${info.category} · ${info.audience}`} />
      <div className="no-print back-row">
        <Link to="/products" className="link-btn"><ArrowLeft size={14} /> {t('productsGallery')}</Link>
        <button className="action-btn" onClick={() => window.print()} title={t('printNote')}>
          <FileDown size={16} /> {t('downloadPdf')}
        </button>
      </div>

      <section className="product-hero card">
        <div className="hero-img">
          {info.image_url ? <img src={info.image_url} alt={info.name} referrerPolicy="no-referrer" /> : <ImageOff size={40} />}
        </div>
        <div className="hero-info">
          <div className="eyebrow">{tl(info.category)} · {tl(info.audience)}</div>
          <h1 dir="auto">{info.name}</h1>
          <div className="muted">{info.product_id} · {info.skus} SKUs · {tl(info.size_group)}</div>
          <div className="hero-price">
            {info.min_price === info.max_price ? fmt(info.min_price, 'egp', { compact: false })
              : `${fmt(info.min_price, 'egp', { compact: false })} – ${fmt(info.max_price, 'egp', { compact: false })}`}
          </div>
          {info.url && (
            <a className="link-btn no-print" href={info.url} target="_blank" rel="noreferrer">
              {ar ? 'صفحة المنتج على موقع كوتونيل' : 'Product page on cottonilegypt.com'} <ExternalLink size={13} />
            </a>
          )}
        </div>
      </section>

      <section className="kpi-grid">
        <KpiCard kpi={kpi('ns', 'Net sales', kpis.net_sales, 'egp')} />
        <KpiCard kpi={kpi('u', 'Units sold (net)', kpis.units, 'number')} />
        <KpiCard kpi={kpi('m', 'Gross margin', kpis.margin_pct, 'pct')} />
        <KpiCard kpi={kpi('r', 'Unit return rate', kpis.return_rate, 'pct', 'down')} />
        <KpiCard kpi={kpi('d', 'Discount rate', kpis.discount_rate, 'pct', 'down')} />
        <KpiCard kpi={kpi('c', 'Customers', kpis.customers, 'number')} />
        <KpiCard kpi={kpi('s', 'Share of category', kpis.share_of_category, 'pct')} />
      </section>

      <section className="chart-grid">
        <ChartCard chart={{ id: 'monthly', title: 'Monthly units sold', type: 'line', width: 'full', format: 'number',
          x: 'month_start', series: [{ key: 'units', label: 'Net units' }], data: data.monthly }} />
        <ChartCard chart={{ id: 'sizes', title: 'Units sold by size', type: 'bar', width: 'half', format: 'number',
          x: 'label', series: [{ key: 'units', label: 'Units' }], data: data.sizes,
          table_columns: [{ key: 'label', label: 'Size' }, { key: 'units', label: 'Units', format: 'number' },
            { key: 'return_rate', label: 'Return rate', format: 'pct' }] }} />
        <ChartCard chart={{ id: 'colors', title: 'Units sold by colour', type: 'hbar', width: 'half', format: 'number',
          x: 'label', series: [{ key: 'units', label: 'Units' }], data: data.colors }} />
        <ChartCard chart={{ id: 'branches', title: 'Top branches', type: 'hbar', width: 'full', format: 'egp',
          x: 'label', series: [{ key: 'net_sales', label: 'Net sales' }], data: data.branches }} />
        {forecast.length > 0 && (
          <ChartCard chart={{ id: 'forecast', title: `Category demand forecast (units, 80% interval) - ${info.category}`, type: 'line', width: 'full',
            format: 'number', x: 'month_start', data: forecast,
            series: [{ key: 'actual_units', label: 'Actual units' }, { key: 'forecast_units', label: 'Forecast' },
              { key: 'lower_80', label: 'Lower 80%' }, { key: 'upper_80', label: 'Upper 80%' }] }} />
        )}
      </section>
    </div>
  )
}
