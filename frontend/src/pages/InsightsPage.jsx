// =============================================================================
// InsightsPage.jsx - Insight Scout: what changed in the business, found by AI
// -----------------------------------------------------------------------------
// The backend runs fixed SQL "probes" (latest months vs the past) and the model
// writes the cards in English and Egyptian Arabic. Every card has a suggested
// action and an "Ask the analyst" button that opens the Business Analyst with a
// ready follow-up question. Cards are cached for a few hours; "Refresh" re-runs.
// =============================================================================
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Info, MessageSquareText, RefreshCw, Volume2 } from 'lucide-react'
import { api } from '../lib/api.js'
import { useLang } from '../lib/i18n.jsx'
import { canSpeak, speak } from '../lib/speech.js'

const ICONS = { warning: AlertTriangle, good: CheckCircle2, info: Info }

export default function InsightsPage() {
  const { lang } = useLang()
  const navigate = useNavigate()
  const [state, setState] = useState({ loading: true, data: null, error: null })

  const load = (refresh = false) => {
    setState((s) => ({ ...s, loading: true, error: null }))
    ;(refresh ? api.insights(true).then((d) => { api.forgetInsights(); return d }) : api.insights())
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((e) => setState({ loading: false, data: null, error: e.message }))
  }
  useEffect(() => { load(false) }, [])

  const L = (card, field) => card[`${field}_${lang}`] || card[`${field}_en`]
  const { loading, data, error } = state

  return (
    <div className="app-page">
      <div className="page-head">
        <div>
          <div className="eyebrow">{lang === 'ar' ? 'أدوات الذكاء الاصطناعي' : 'AI Tools'}</div>
          <h1>{lang === 'ar' ? 'مستكشف الملاحظات' : 'Insight Scout'}</h1>
          <p className="muted">
            {lang === 'ar'
              ? 'بيدوّر لوحده في الداتا على اللي اتغير: الفئات والفروع والقنوات والهامش والمرتجعات والعملاء والمخزون والتوقع - ويقترح الخطوة الجاية. النمو محسوب بالقطع أو بالأسعار الحقيقية (من غير تضخم).'
              : 'Scans the data on its own for what changed - categories, branches, channels, margin, returns, customers, stock and the forecast - and suggests the next step. Growth is measured in units or real (inflation-free) values.'}
          </p>
        </div>
        <div className="page-actions">
          <button className="action-btn" onClick={() => load(true)} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> {lang === 'ar' ? 'حدّث' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && <div className="error-box"><strong>Error</strong><code>{error}</code></div>}
      {loading && !data && <div className="insight-grid">{[1, 2, 3, 4].map((i) => <div key={i} className="card skeleton tall" />)}</div>}

      {data && (
        <>
          <p className="muted small">
            {lang === 'ar' ? 'آخر شهر كامل' : 'Latest complete month'}: {data.latest_complete_month} ·{' '}
            {lang === 'ar' ? 'اتعمل' : 'generated'} {data.generated_at}
            {data.source === 'template' && (lang === 'ar'
              ? ' · الذكاء الاصطناعي مش متاح دلوقتي، دي كروت بسيطة من الأرقام'
              : ' · AI not available right now - simple cards from the numbers')}
          </p>
          <div className="insight-grid">
            {data.cards.map((c, i) => {
              const Icon = ICONS[c.severity] || Info
              return (
                <article key={i} className={`card insight-card sev-${c.severity || 'info'}`} dir={lang === 'ar' ? 'rtl' : 'ltr'}>
                  <div className="insight-top">
                    <Icon size={18} />
                    <h3>{L(c, 'title')}</h3>
                  </div>
                  <p>{L(c, 'insight')}</p>
                  <p className="insight-action"><strong>{lang === 'ar' ? 'الخطوة الجاية: ' : 'Next step: '}</strong>{L(c, 'action')}</p>
                  <div className="insight-buttons">
                    {L(c, 'ask') && (
                      <button className="chip" onClick={() => navigate('/chat/analyst', { state: { ask: L(c, 'ask') } })}>
                        <MessageSquareText size={13} /> {lang === 'ar' ? 'اسأل المحلل' : 'Ask the analyst'}
                      </button>
                    )}
                    {canSpeak && (
                      <button className="chip" onClick={() => speak(`${L(c, 'title')}. ${L(c, 'insight')}. ${L(c, 'action')}`)}>
                        <Volume2 size={13} />
                      </button>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
          {data.cards.length === 0 && <div className="empty">No notable changes found.</div>}
        </>
      )}
    </div>
  )
}