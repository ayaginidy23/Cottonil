// =============================================================================
// ReportsPage.jsx - Report Agent: type a topic, get a full management report
// -----------------------------------------------------------------------------
// The agent plans the angles, runs 3-6 read-only queries on gold, then writes
// the report in English and Egyptian Arabic. "PDF" opens the bilingual print page.
// The last reports of this browser are listed so they can be reopened.
// =============================================================================
import { useState } from 'react'
import { FileDown, FileText, Loader2 } from 'lucide-react'
import ReportView from '../components/ReportView.jsx'
import { api } from '../lib/api.js'
import { useLang } from '../lib/i18n.jsx'

const TOPICS = [
  'Sales performance in the last 12 months: trend, categories and channels',
  'أداء الفروع في 2025: أكتر وأقل فروع ربحًا وليه',
  'Customer segments and who we are losing',
  'تقرير عن المرتجعات: أنهي منتجات ومقاسات بترجع أكتر',
  'Inventory health: where to replenish and where we are overstocked',
]

const HISTORY_KEY = 'cottonil_reports'
function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]') } catch { return [] }
}
function saveHistory(list) {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, 10))) } catch { /* storage blocked */ }
}

export default function ReportsPage() {
  const { lang: uiLang } = useLang()
  const [topic, setTopic] = useState('')
  const [report, setReport] = useState(null)
  const [lang, setLang] = useState(uiLang)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState(loadHistory)
  const ar = uiLang === 'ar'

  const generate = async (text) => {
    const t = (text ?? topic).trim()
    if (t.length < 3 || busy) return
    setTopic(t)
    setBusy(true)
    setError(null)
    setReport(null)
    try {
      const r = await api.makeReport(t)
      setReport(r)
      const next = [{ id: r.report_id, title: r.title_en, title_ar: r.title_ar, at: new Date().toISOString().slice(0, 16) },
        ...history.filter((h) => h.id !== r.report_id)]
      setHistory(next)
      saveHistory(next)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const open = async (id) => {
    setBusy(true)
    setError(null)
    try { setReport(await api.report(id)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="app-page">
      <div className="page-head">
        <div>
          <div className="eyebrow">{ar ? 'أدوات الذكاء الاصطناعي' : 'AI Tools'}</div>
          <h1>{ar ? 'وكيل التقارير' : 'Report Agent'}</h1>
          <p className="muted">
            {ar
              ? 'اكتب موضوع، والوكيل يخطط ويشغّل كذا استعلام (قراءة بس) ويكتب تقرير إداري بالرسومات والتوصيات - بالإنجليزي والمصري - وتقدر تنزله PDF.'
              : 'Write a topic; the agent plans the angles, runs several read-only queries and writes a management report with charts and recommendations - in English and Egyptian Arabic - ready as a PDF.'}
          </p>
        </div>
      </div>

      <div className="report-layout">
        <aside className="card report-side">
          <form onSubmit={(e) => { e.preventDefault(); generate() }}>
            <label className="kpi-label" htmlFor="topic">{ar ? 'موضوع التقرير' : 'Report topic'}</label>
            <textarea id="topic" className="input textarea" dir="auto" rows={3} value={topic}
              placeholder={ar ? 'مثال: أداء فروع إسكندرية في 2025' : 'e.g. Alexandria branches performance in 2025'}
              onChange={(e) => setTopic(e.target.value)} disabled={busy} />
            <button className="new-chat-btn" type="submit" disabled={busy || topic.trim().length < 3}>
              {busy ? <Loader2 size={16} className="spin" /> : <FileText size={16} />}
              {busy ? (ar ? 'بيكتب التقرير…' : 'Writing the report…') : (ar ? 'اعمل التقرير' : 'Generate report')}
            </button>
          </form>
          <div className="kpi-label" style={{ marginTop: 14 }}>{ar ? 'أفكار' : 'Ideas'}</div>
          <div className="suggestions">
            {TOPICS.map((t) => (
              <button key={t} className="chip suggestion" dir="auto" onClick={() => generate(t)} disabled={busy}>{t}</button>
            ))}
          </div>
          {history.length > 0 && (
            <>
              <div className="kpi-label" style={{ marginTop: 14 }}>{ar ? 'تقاريرك الأخيرة' : 'Your recent reports'}</div>
              <div className="suggestions">
                {history.map((h) => (
                  <button key={h.id} className="chip suggestion" dir="auto" onClick={() => open(h.id)} disabled={busy}>
                    {ar ? h.title_ar || h.title : h.title} <span className="muted small">· {h.at.replace('T', ' ')}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </aside>

        <section className="report-main">
          {error && <div className="error-box"><strong>Error</strong><code>{error}</code></div>}
          {busy && !report && (
            <div className="card empty">
              <Loader2 size={28} className="spin" />
              <div>{ar ? 'الوكيل بيحلل الداتا ويكتب… (ممكن ياخد دقيقة)' : 'The agent is querying the data and writing… (up to a minute)'}</div>
            </div>
          )}
          {!busy && !report && !error && (
            <div className="card empty"><FileText size={28} /><div>{ar ? 'اختار موضوع أو اكتب واحد' : 'Pick or type a topic'}</div></div>
          )}
          {report && (
            <div className="card report-card">
              <div className="report-toolbar">
                <div className="segmented small-seg">
                  <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>English</button>
                  <button className={lang === 'ar' ? 'active' : ''} onClick={() => setLang('ar')}>العربي</button>
                </div>
                <span className="spacer" />
                <span className="muted small">{report.sections.length} sections · {report.attempts?.length || 0} queries</span>
                <a className="action-btn primary" href={`/print/report/${report.report_id}`} target="_blank" rel="noreferrer">
                  <FileDown size={16} /> PDF (EN + عربي)
                </a>
              </div>
              <ReportView report={report} lang={lang} />
              {report.sections.some((s) => s.sql) && (
                <details className="sql-box">
                  <summary>SQL used ({report.sections.filter((s) => s.sql).length})</summary>
                  {report.sections.filter((s) => s.sql).map((s, i) => <pre key={i}>{s.sql}</pre>)}
                </details>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
