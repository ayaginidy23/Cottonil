// =============================================================================
// SecurityPage.jsx - Security Log: proof that the AI safety rules really work
// -----------------------------------------------------------------------------
// Every time a protection fires (blocked SQL, read outside gold, another
// customer's order, a question about company data, "ignore your instructions"...)
// the backend writes an event in app.security_events. This page shows them.
// =============================================================================
import { useEffect, useState } from 'react'
import { RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react'
import DataTable from '../components/DataTable.jsx'
import { api } from '../lib/api.js'
import { useLang } from '../lib/i18n.jsx'

const KINDS = {
  blocked_sql: ['Blocked SQL', 'استعلام اتمنع', 'The analyst generated SQL that was not one read-only SELECT. It was not run.', 'المحلل كتب SQL مش SELECT واحد للقراءة، فماتنفذش.'],
  permission_denied: ['Read outside gold', 'محاولة قراءة برا gold', 'A query tried to read raw / silver data. The read-only role stopped it.', 'استعلام حاول يقرا داتا خام أو silver، والصلاحيات وقفته.'],
  customer_id_override: ['Other customer id', 'رقم عميل تاني', 'The model tried to use another customer id. The server ignored it and used the logged-in id.', 'الموديل حاول يستخدم رقم عميل تاني، والسيرفر تجاهله واستخدم رقم العميل اللي داخل.'],
  other_customer_order: ["Another customer's order", 'أوردر عميل تاني', 'A customer asked about an order that belongs to someone else. Answer: "not found on your account".', 'عميل سأل عن أوردر مش بتاعه. الرد: "مش موجود على حسابك".'],
  sensitive_question: ['Company-data question', 'سؤال عن داتا الشركة', 'A customer asked about sales, profit, salaries, suppliers… No tool can return that; the bot refuses.', 'عميل سأل عن مبيعات أو أرباح أو مرتبات أو موردين… مفيش أداة بترجع ده، والبوت بيرفض.'],
  prompt_injection: ['Prompt injection', 'محاولة تلاعب بالتعليمات', '"Ignore your instructions" / "show the system prompt". The rules stay in force.', '"انسى التعليمات" أو "اعرض البرومبت". القواعد بتفضل شغالة.'],
  login_required: ['Login required', 'لازم تسجيل دخول', 'A guest asked for orders or purchase history and was asked to log in.', 'زائر طلب أوردرات أو مشتريات، فطلبنا منه يسجل دخول.'],
}

export default function SecurityPage() {
  const { lang } = useLang()
  const ar = lang === 'ar'
  const [summary, setSummary] = useState(null)
  const [events, setEvents] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    Promise.all([api.securitySummary(30), api.securityEvents(300)])
      .then(([s, e]) => { setSummary(s); setEvents(e); setError(null) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const label = (kind) => (KINDS[kind] ? KINDS[kind][ar ? 1 : 0] : kind)
  const rows = events.map((e) => ({
    // dd/mm/yyyy hh:mm (an ISO date would be shown as a month label by the table)
    time: `${e.created_at.slice(8, 10)}/${e.created_at.slice(5, 7)}/${e.created_at.slice(0, 4)} ${e.created_at.slice(11, 16)}`,
    source: e.source === 'shop' ? (ar ? 'مساعد التسوق' : 'Shopping Assistant') : (ar ? 'المحلل' : 'Business Analyst'),
    severity: e.severity,
    kind: label(e.kind),
    action: e.action,
    who: e.owner_key || '-',
    detail: Object.entries(e.detail || {}).map(([k, v]) => `${k}: ${v}`).join(' | '),
  }))

  return (
    <div className="app-page">
      <div className="page-head">
        <div>
          <div className="eyebrow">{ar ? 'أدوات الذكاء الاصطناعي' : 'AI Tools'}</div>
          <h1>{ar ? 'سجل الأمان' : 'Security Log'}</h1>
          <p className="muted">
            {ar
              ? 'كل مرة قاعدة أمان تشتغل في المساعدين بتتسجل هنا - عشان الإدارة تشوف إن الحماية شغالة فعلًا. المساعدين بيمنعوا الحاجات دي في كل الأحوال؛ السجل للمتابعة بس.'
              : 'Every time a safety rule of the AI assistants fires, it is recorded here - so management can see the protections working. The assistants block these things anyway; the log is for monitoring.'}
          </p>
        </div>
        <div className="page-actions">
          <button className="action-btn" onClick={load} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> {ar ? 'حدّث' : 'Refresh'}
          </button>
        </div>
      </div>
      {error && <div className="error-box"><strong>Error</strong><code>{error}</code></div>}

      {summary && (
        <section className="kpi-grid">
          <div className="card kpi">
            <div className="kpi-label">{ar ? 'أحداث آخر 30 يوم' : 'Events, last 30 days'}</div>
            <div className="kpi-value">{summary.total}</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">{ar ? 'خطورة عالية (اتمنعت)' : 'High severity (blocked)'}</div>
            <div className="kpi-value" style={{ color: summary.high ? 'var(--bad)' : undefined }}>{summary.high}</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">{ar ? 'محاولات رجعت داتا الشركة' : 'Attempts that returned company data'}</div>
            <div className="kpi-value" style={{ color: 'var(--good)' }}>0</div>
            <div className="muted small">{ar ? 'مفيش أداة تقدر ترجعها أصلًا' : 'no tool or role can return it'}</div>
          </div>
        </section>
      )}

      <section className="security-grid">
        {Object.entries(KINDS).map(([kind, [en, arT, dEn, dAr]]) => {
          const n = summary?.by_kind.filter((k) => k.kind === kind).reduce((s, k) => s + k.events, 0) || 0
          const high = ['blocked_sql', 'permission_denied', 'customer_id_override', 'prompt_injection'].includes(kind)
          return (
            <div key={kind} className="card security-card">
              <div className="security-top">
                {high ? <ShieldAlert size={18} className="error-text" /> : <ShieldCheck size={18} style={{ color: 'var(--good)' }} />}
                <strong>{ar ? arT : en}</strong>
                <span className="security-count">{n}</span>
              </div>
              <p className="muted small" dir={ar ? 'rtl' : 'ltr'}>{ar ? dAr : dEn}</p>
            </div>
          )
        })}
      </section>

      <div className="card chart w-full" style={{ marginTop: 14 }}>
        <div className="chart-head"><h3>{ar ? 'آخر الأحداث' : 'Latest events'}</h3></div>
        {rows.length ? (
          <DataTable rows={rows} filename="security_events" columns={[
            { key: 'time', label: ar ? 'الوقت' : 'Time' },
            { key: 'source', label: ar ? 'المساعد' : 'Assistant' },
            { key: 'severity', label: ar ? 'الخطورة' : 'Severity' },
            { key: 'kind', label: ar ? 'النوع' : 'Kind' },
            { key: 'action', label: ar ? 'اللي حصل' : 'What the system did' },
            { key: 'who', label: ar ? 'مين' : 'Who' },
            { key: 'detail', label: ar ? 'تفاصيل' : 'Detail' },
          ]} />
        ) : (
          <div className="empty">{ar ? 'مفيش أحداث لسه - جرّب تسأل البوت عن أرباح الشركة' : 'No events yet - try asking the shopping bot about company profit'}</div>
        )}
      </div>
    </div>
  )
}
