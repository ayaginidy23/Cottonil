// =============================================================================
// AppPage.jsx - The ONE page that renders every dashboard app
// -----------------------------------------------------------------------------
// Reads :appId from the URL, asks the API for that app with the current filters,
// then draws the KPI cards and the charts it gets back. Adding a new app needs
// no change here - only a new YAML file in the backend.
// =============================================================================
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Lightbulb } from 'lucide-react'

import ChartCard from '../components/ChartCard.jsx'
import KpiCard from '../components/KpiCard.jsx'
import { api } from '../lib/api.js'
import { useFilters } from '../lib/filters.jsx'

export default function AppPage() {
  const { appId } = useParams()
  const { filters, ready } = useFilters()
  const [state, setState] = useState({ loading: true, data: null, error: null })

  useEffect(() => {
    if (!ready) return
    let cancelled = false            // ignore old answers if filters change quickly
    setState((s) => ({ ...s, loading: true, error: null }))
    api
      .app(appId, filters)
      .then((data) => !cancelled && setState({ loading: false, data, error: null }))
      .catch((e) => !cancelled && setState({ loading: false, data: null, error: e.message }))
    return () => {
      cancelled = true
    }
  }, [appId, filters, ready])

  const { loading, data, error } = state

  if (error) {
    return (
      <div className="error-box page">
        <strong>Could not load this app</strong>
        <code>{error}</code>
      </div>
    )
  }
  if (!data) return <PageSkeleton />

  return (
    <div className={`app-page ${loading ? 'is-loading' : ''}`}>
      <div className="page-head">
        <div>
          <div className="eyebrow">{data.group}</div>
          <h1>{data.title}</h1>
          <p className="muted">{data.description}</p>
        </div>
      </div>

      {data.insights?.length > 0 && (
        <div className="card insights">
          <Lightbulb size={18} />
          <ul>
            {data.insights.map((t, i) => (
              <li key={i}>{t}</li>
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
