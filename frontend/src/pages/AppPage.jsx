// =============================================================================
// AppPage.jsx - The ONE page that renders every dashboard app
// -----------------------------------------------------------------------------
// Reads :appId from the URL, asks the API for that app with the current filters,
// then draws the KPI cards and the charts it gets back. Adding a new app needs
// no change here - only a new YAML file in the backend.
//
// Toolbar:
//   "Explain this page" -> AI summary of exactly what is on screen (EN + AR)
//   "Download PDF"      -> the browser's print-to-PDF with a print layout:
//                          header (title in both languages, filters, date),
//                          the AI summary in English AND Arabic, all KPIs and
//                          charts with bilingual titles. The browser draws the
//                          Arabic text itself, so it is always shaped correctly.
// =============================================================================
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { FileDown, Lightbulb, Sparkles } from 'lucide-react'

import ChartCard from '../components/ChartCard.jsx'
import ExplainPanel from '../components/ExplainPanel.jsx'
import KpiCard from '../components/KpiCard.jsx'
import { api } from '../lib/api.js'
import { useFilters } from '../lib/filters.jsx'
import { Bi, arabicLabel, useLang } from '../lib/i18n.jsx'

export function PrintHeader({ title, subtitle }) {
  const { filters } = useFilters()
  const { t } = useLang()
  const ar = arabicLabel(title)
  return (
    <div className="print-only print-header">
      <img src="/cottonil-logo-blue.png" alt="Cottonil" className="print-logo"
        onError={(e) => { e.currentTarget.style.display = 'none' }} />
      <h1>{title}</h1>
      {ar !== title && <h2 dir="rtl" lang="ar">{ar}</h2>}
      {subtitle && <p>{subtitle}</p>}
      {subtitle && arabicLabel(subtitle) !== subtitle && <p dir="rtl" lang="ar">{arabicLabel(subtitle)}</p>}
      <p className="print-meta">
        {t('period')}: {filters.dateFrom || 'start'} → {filters.dateTo || 'end'} ·{' '}
        {filters.branches.length ? `${filters.branches.length} branches` : 'All branches / كل الفروع'} ·{' '}
        {filters.channels.length ? filters.channels.join(', ') : 'All channels / كل القنوات'} ·{' '}
        {t('generatedOn')} {new Date().toLocaleString('en-GB')}
      </p>
    </div>
  )
}

export default function AppPage() {
  const { appId } = useParams()
  const { filters, ready } = useFilters()
  const { t, tl } = useLang()
  const [state, setState] = useState({ loading: true, data: null, error: null })
  const [explain, setExplain] = useState({ open: false, loading: false, data: null, error: null })

  useEffect(() => {
    if (!ready) return
    let cancelled = false            // ignore old answers if filters change quickly
    setState((s) => ({ ...s, loading: true, error: null }))
    setExplain({ open: false, loading: false, data: null, error: null })   // summary belongs to the old view
    api
      .app(appId, filters)
      .then((data) => !cancelled && setState({ loading: false, data, error: null }))
      .catch((e) => !cancelled && setState({ loading: false, data: null, error: e.message }))
    return () => {
      cancelled = true
    }
  }, [appId, filters, ready])

  const runExplain = async () => {
    if (explain.data) { setExplain((x) => ({ ...x, open: true })); return explain.data }
    setExplain({ open: true, loading: true, data: null, error: null })
    try {
      const data = await api.explain(appId, filters)
      setExplain({ open: true, loading: false, data, error: null })
      return data
    } catch (e) {
      setExplain({ open: true, loading: false, data: null, error: e.message })
      return null
    }
  }

  // PDF: get the AI summary first (best effort), let React draw it, then print
  const downloadPdf = async () => {
    await runExplain()
    setTimeout(() => window.print(), 400)
  }

  const { loading, data, error } = state

  if (error) {
    return (
      <div className="error-box page">
        <strong>{t('loadError')}</strong>
        <code>{error}</code>
      </div>
    )
  }
  if (!data) return <PageSkeleton />

  return (
    <div className={`app-page ${loading ? 'is-loading' : ''}`}>
      <PrintHeader title={data.title} subtitle={data.description} />
      <div className="page-head no-print">
        <div>
          <div className="eyebrow">{tl(data.group)}</div>
          <h1>{tl(data.title)}</h1>
          <p className="muted">{tl(data.description)}</p>
        </div>
        <div className="page-actions">
          <button className="action-btn primary" onClick={runExplain} disabled={explain.loading}>
            <Sparkles size={16} /> {explain.loading ? t('explaining') : t('explain')}
          </button>
          <button className="action-btn" onClick={downloadPdf} title={t('printNote')}>
            <FileDown size={16} /> {t('downloadPdf')}
          </button>
        </div>
      </div>

      {explain.open && (
        <ExplainPanel summary={explain.data} loading={explain.loading} error={explain.error}
          onClose={() => setExplain((x) => ({ ...x, open: false }))} />
      )}

      {data.insights?.length > 0 && (
        <div className="card insights">
          <Lightbulb size={18} />
          <ul>
            {data.insights.map((txt, i) => (
              <li key={i}><Bi text={txt} /></li>
            ))}
          </ul>
        </div>
      )}

      <section className="kpi-grid">
        {data.kpis.map((k) => (
          <KpiCard key={k.id} kpi={k} />
        ))}
      </section>

      <section className="chart-grid">
        {data.charts.map((c) => (
          <ChartCard key={c.id} chart={c} />
        ))}
      </section>
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="app-page">
      <div className="skeleton title" />
      <section className="kpi-grid">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="card kpi skeleton" />
        ))}
      </section>
      <section className="chart-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card chart w-half skeleton tall" />
        ))}
      </section>
    </div>
  )
}
