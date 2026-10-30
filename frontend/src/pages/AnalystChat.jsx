// =============================================================================
// AnalystChat.jsx - Business Analyst for management (questions -> SQL -> answer)
// -----------------------------------------------------------------------------
// Every answer shows: the text answer, an automatic chart of the result
// (reusing ChartCard, with its table view), and the SQL that produced it -
// so managers can trust and check the numbers.
// =============================================================================
import { useEffect, useRef, useState } from 'react'
import { BarChart3, Bot, Send, User } from 'lucide-react'
import ChartCard from '../components/ChartCard.jsx'
import MemoryPanel from '../components/MemoryPanel.jsx'
import { MicButton, SpeakButton } from '../components/VoiceControls.jsx'
import { api } from '../lib/api.js'

const SUGGESTIONS = [
  'أكتر 10 فروع ربحًا في 2025؟',
  'Monthly net sales vs real net sales in 2025',
  'إيه أكتر فئة نمت في الوحدات آخر 12 شهر؟',
  'Which sales channel has the highest return rate?',
  'كام عميل في كل شريحة RFM وإيرادهم كام؟',
  'What is the demand forecast for the next 6 months by category?',
]

// Guess how to show a value column from its name and values
function guessFormat(col, rows) {
  const name = col.toLowerCase()
  const max = Math.max(...rows.map((r) => Math.abs(Number(r[col]) || 0)))
  if (/(pct|rate|share|ratio|margin_pct|growth)/.test(name) && max <= 1.5) return 'pct'
  if (/(egp|sales|revenue|profit|value|cost|amount|spend|refund|margin)/.test(name)) return 'egp'
  if (/usd/.test(name)) return 'usd'
  return 'number'
}

// Build a ChartCard spec from any result table (or null if it isn't chartable)
function autoChart(columns, rows) {
  if (!rows?.length || rows.length < 2 || columns.length < 2) return null
  const isNum = (c) => rows.every((r) => r[c] === null || typeof r[c] === 'number')
  const numeric = columns.filter(isNum)
  const labels = columns.filter((c) => !isNum(c))
  if (!numeric.length) return null
  const x = labels[0] || columns[0]
  let values = numeric.filter((c) => c !== x)
  if (!values.length) return null

  // one axis only: keep extra series only if they have a similar scale to the first
  const maxOf = (c) => Math.max(...rows.map((r) => Math.abs(Number(r[c]) || 0))) || 1
  const base = maxOf(values[0])
  values = values.filter((c, i) => i === 0 || (maxOf(c) / base < 10 && maxOf(c) / base > 0.1)).slice(0, 3)

  const timeLike = rows.every((r) => /^\d{4}(-\d{2})?(-\d{2})?/.test(String(r[x])))
  const type = timeLike ? 'line' : rows.length > 12 ? 'hbar' : 'bar'
  return {
    id: 'auto',
    title: 'Result',
    type: type === 'hbar' && values.length > 1 ? 'bar' : type,
    width: 'full',
    x,
    series: values.map((c) => ({ key: c, label: c })),
    format: guessFormat(values[0], rows),
    data: type === 'hbar' ? rows.slice(0, 25) : rows,
    table_columns: columns.map((c) => ({ key: c, label: c, format: isNum(c) && c !== x ? guessFormat(c, rows) : undefined })),
  }
}

export default function AnalystChat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [memory, setMemory] = useState('')
  const [saving, setSaving] = useState(false)
  const endRef = useRef(null)

  // restore the open chat + memory after a refresh
  useEffect(() => {
    let cancelled = false
    api.chatSession('analyst')
      .then((res) => {
        if (cancelled) return
        setMemory(res.memory || '')
        if (res.session) {
          setSessionId(res.session.session_id)
          setMessages(res.session.messages.map((m) => ({
            role: m.role, content: m.content, result: m.payload?.result,
          })))
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const newChat = async () => {
    setError(null)
    if (!sessionId) { setMessages([]); return }
    setSaving(true)
    try {
      const res = await api.newChat('analyst', null, sessionId)
      setMemory(res.memory || '')
      if (res.warning) setError(res.warning)
    } catch (e) {
      setError(e.message)
    } finally {
      setSessionId(null)
      setMessages([])
      setSaving(false)
    }
  }

  const forget = async () => {
    try {
      await api.forgetMemory('analyst')
      setMemory('')
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    // braces matter: new Chrome returns a Promise from scrollIntoView, and an effect
    // must return nothing or a cleanup function (else: "destroy is not a function")
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  const send = async (text) => {
    const content = (text ?? input).trim()
    if (!content || busy) return
    const next = [...messages, { role: 'user', content }]
    setMessages(next)
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const res = await api.chatAnalyst(next.map(({ role, content: c }) => ({ role, content: c })), sessionId)
      setSessionId(res.session_id || sessionId)
      setMessages([...next, { role: 'assistant', content: res.reply, result: res }])
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="chat-page">
      <div className="page-head">
        <div>
          <div className="eyebrow">AI Assistants</div>
          <h1>Business Analyst</h1>
          <p className="muted">
            Ask any business question in Arabic or English. The assistant finds the right gold tables
            (schema RAG), writes a read-only SQL query, checks the result and explains it - with the
            chart and the SQL so every number can be verified.
          </p>
        </div>
      </div>

      <div className="chat-layout">
        <aside className="card chat-side">
          <MemoryPanel memory={memory} onNewChat={newChat} onForget={forget} busy={busy} saving={saving} />
          <div className="kpi-label" style={{ marginTop: 14 }}>Try asking</div>
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chip suggestion" dir="auto" onClick={() => send(s)} disabled={busy}>
                {s}
              </button>
            ))}
          </div>
          <div className="side-note" style={{ marginTop: 10 }}>
            <BarChart3 size={16} />
            <span>Read-only: queries run as a role that can only SELECT from the gold layer, with a 15 s limit.</span>
          </div>
        </aside>

        <section className="card chat-box">
          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="empty">
                <Bot size={32} />
                <div>اسأل أي سؤال عن المبيعات، الفروع، العملاء أو المخزون</div>
              </div>
            )}
            {messages.map((m, i) => {
              const chart = m.result ? autoChart(m.result.columns, m.result.rows) : null
              return (
                <div key={i} className={`msg ${m.role}`}>
                  <div className="msg-icon">{m.role === 'user' ? <User size={16} /> : <Bot size={16} />}</div>
                  <div className="msg-body" style={{ minWidth: 0, flex: 1 }}>
                    <div className="msg-text" dir="auto">{m.content}</div>
                    {m.role === 'assistant' && <SpeakButton text={m.content} />}
                    {m.result?.images?.length > 0 && (
                      <div className="product-grid">
                        {m.result.images.map((p) => (
                          <a key={p.product_id} className="product-card" href={p.url || '#'} target="_blank" rel="noreferrer">
                            <img className="product-img" src={p.image_url} alt={p.name} loading="lazy" referrerPolicy="no-referrer" />
                            <div className="product-name" dir="auto">{p.name}</div>
                            <div className="muted small">{p.product_id}</div>
                          </a>
                        ))}
                      </div>
                    )}
                    {chart && <div className="analyst-chart"><ChartCard chart={chart} /></div>}
                    {m.result?.sql && (
                      <details className="sql-box">
                        <summary>SQL ({m.result.rows.length} rows · tables: {m.result.tables_used?.slice(0, 5).join(', ')})</summary>
                        <pre>{m.result.sql}</pre>
                      </details>
                    )}
                  </div>
                </div>
              )
            })}
            {busy && <div className="msg assistant"><div className="msg-icon"><Bot size={16} /></div><div className="typing">Analysing…</div></div>}
            {error && <div className="error-box"><strong>Error</strong><code>{error}</code></div>}
            <div ref={endRef} />
          </div>
          <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send() }}>
            <MicButton onText={setInput} disabled={busy} />
            <input className="input" dir="auto" placeholder="اسأل سؤال… / Ask a business question…"
              value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} />
            <button className="send-btn" type="submit" disabled={busy || !input.trim()} aria-label="Send">
              <Send size={16} />
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}