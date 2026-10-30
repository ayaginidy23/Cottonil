// =============================================================================
// ShopChat.jsx - Customer & reseller chatbot page
// -----------------------------------------------------------------------------
// "Log in as" picks a real customer id from the data (demo login), so the bot
// can answer about THAT customer's orders only. Product suggestions come back
// as cards with a link to the real product page.
// Extras: voice notes (mic), read replies aloud, and photo -> similar products.
// =============================================================================
import { useEffect, useRef, useState } from 'react'
import { Bot, ImagePlus, Send, ShieldCheck, User, Wrench } from 'lucide-react'
import MemoryPanel from '../components/MemoryPanel.jsx'
import { MicButton, SpeakButton } from '../components/VoiceControls.jsx'
import { api } from '../lib/api.js'
import { fmt } from '../lib/format.js'
import { resizeImage } from '../lib/image.js'
import { stopSpeaking } from '../lib/speech.js'

const SUGGESTIONS = {
  guest: [
    'عايز تيشيرت قطن رجالي خفيف للصيف',
    'بيجامة أطفال مقاس 4 تحت 400 جنيه',
    'أقرب فرع في الإسكندرية؟',
    'What is your return policy?',
  ],
  customer: ['آخر أوردرات ليا إيه؟', 'أوردري الأخير وصل ولا لسه؟', 'اقترحلي حاجات زي اللي بشتريها'],
  reseller: ['إيه أكتر المنتجات اللي بطلبها؟ واقترحلي reorder', 'إجمالي مشترياتي كل سنة', 'إيه طرق الدفع للتجار؟'],
}

function ProductCard({ p }) {
  return (
    <a className="product-card" href={p.url || '#'} target="_blank" rel="noreferrer">
      {p.image_url && (
        <img className="product-img" src={p.image_url} alt={p.name} loading="lazy"
          referrerPolicy="no-referrer" onError={(e) => { e.currentTarget.style.display = 'none' }} />
      )}
      <div className="product-name" dir="auto">{p.name}</div>
      <div className="muted small">{p.category} · {p.audience}</div>
      <div className="product-price">
        {p.min_price === p.max_price ? fmt(p.min_price, 'egp', { compact: false })
          : `${fmt(p.min_price, 'egp', { compact: false })} – ${fmt(p.max_price, 'egp', { compact: false })}`}
      </div>
      <div className="muted small">Sizes: {p.sizes}</div>
    </a>
  )
}

export default function ShopChat() {
  const [users, setUsers] = useState([])
  const [customerId, setCustomerId] = useState('')
  const [messages, setMessages] = useState([])     // {role, content, products?, tools?}
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sessionId, setSessionId] = useState(null)   // the saved chat on the server
  const [memory, setMemory] = useState('')           // long-term memory of this user
  const [saving, setSaving] = useState(false)
  const endRef = useRef(null)
  const fileRef = useRef(null)

  useEffect(() => {
    api.demoUsers().then(setUsers).catch(() => setUsers([]))
  }, [])

  // load this account's open chat + memory (on page load and when switching account)
  useEffect(() => {
    let cancelled = false
    setMessages([])
    setSessionId(null)
    setMemory('')
    api.chatSession('shop', customerId || null)
      .then((res) => {
        if (cancelled) return
        setMemory(res.memory || '')
        if (res.session) {
          setSessionId(res.session.session_id)
          setMessages(res.session.messages.map((m) => ({
            role: m.role, content: m.content, products: m.payload?.products, tools: m.payload?.tools,
          })))
        }
      })
      .catch(() => {})                                 // no history yet: start empty
    return () => { cancelled = true }
  }, [customerId])

  // "New chat": the server folds this chat into memory, then we clear the screen
  const newChat = async () => {
    stopSpeaking()
    setError(null)
    if (!sessionId) { setMessages([]); return }
    setSaving(true)
    try {
      const res = await api.newChat('shop', customerId || null, sessionId)
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
      await api.forgetMemory('shop', customerId || null)
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

  const current = users.find((u) => u.customer_key === customerId)
  const kind = !current ? 'guest' : current.customer_segment === 'B2B reseller' ? 'reseller' : 'customer'

  // switching account loads THAT account's own chat and memory (privacy)
  const switchUser = (id) => {
    setCustomerId(id)
    setError(null)
    stopSpeaking()
  }

  // photo -> the vision model describes it -> semantic search in the catalog
  const sendImage = async (file) => {
    if (!file || busy) return
    setError(null)
    let dataUrl
    try {
      dataUrl = await resizeImage(file)
    } catch (e) {
      setError(e.message)
      return
    }
    const note = input.trim()                        // optional text typed with the photo
    const next = [...messages, { role: 'user', content: note || '📷 دوّرلي على حاجة زي الصورة دي', image: dataUrl }]
    setMessages(next)
    setInput('')
    setBusy(true)
    try {
      const res = await api.chatShopImage(dataUrl, note)
      setMessages([...next, { role: 'assistant', content: res.reply, products: res.products, tools: [{ name: 'image_search' }] }])
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const send = async (text) => {
    const content = (text ?? input).trim()
    if (!content || busy) return
    const next = [...messages, { role: 'user', content }]
    setMessages(next)
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const res = await api.chatShop(
        customerId || null,
        next.map(({ role, content: c }) => ({ role, content: c })),
        sessionId,
      )
      setSessionId(res.session_id || sessionId)
      setMessages([...next, { role: 'assistant', content: res.reply, products: res.products, tools: res.tools }])
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
          <h1>Cottonil Shopping Assistant</h1>
          <p className="muted">
            Chatbot for customers and resellers: product search by meaning (RAG + pgvector on the real
            catalog), branches, store policy, and - when logged in - their own orders and reorders.
          </p>
        </div>
      </div>

      <div className="chat-layout">
        <aside className="card chat-side">
          <label className="kpi-label" htmlFor="login-as">Log in as (demo)</label>
          <select id="login-as" className="input" value={customerId} onChange={(e) => switchUser(e.target.value)}>
            <option value="">Guest (not logged in)</option>
            {users.map((u) => (
              <option key={u.customer_key} value={u.customer_key}>
                {u.customer_key} · {u.customer_segment} · {u.orders} orders
              </option>
            ))}
          </select>
          <MemoryPanel memory={memory} onNewChat={newChat} onForget={forget} busy={busy} saving={saving} />
          <div className="side-note">
            <ShieldCheck size={16} />
            <span>The bot can only read this account's own orders. Company figures are never exposed.</span>
          </div>
          <div className="kpi-label" style={{ marginTop: 14 }}>Try asking</div>
          <div className="suggestions">
            {SUGGESTIONS[kind].map((s) => (
              <button key={s} className="chip suggestion" dir="auto" onClick={() => send(s)} disabled={busy}>
                {s}
              </button>
            ))}
          </div>
        </aside>

        <section className="card chat-box">
          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="empty">
                <Bot size={32} />
                <div>اسألني عن أي منتج، مقاس، فرع أو أوردر</div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="msg-icon">{m.role === 'user' ? <User size={16} /> : <Bot size={16} />}</div>
                <div className="msg-body">
                  {m.image && <img className="msg-image" src={m.image} alt="Uploaded product photo" />}
                  <div className="msg-text" dir="auto">{m.content}</div>
                  {m.role === 'assistant' && <SpeakButton text={m.content} />}
                  {m.products?.length > 0 && (
                    <div className="product-grid">
                      {m.products.map((p) => <ProductCard key={p.product_id} p={p} />)}
                    </div>
                  )}
                  {m.tools?.length > 0 && (
                    <div className="tool-chips">
                      <Wrench size={12} />
                      {m.tools.map((t, j) => <span key={j} className="tool-chip">{t.name}</span>)}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && <div className="msg assistant"><div className="msg-icon"><Bot size={16} /></div><div className="typing">…</div></div>}
            {error && <div className="error-box"><strong>Error</strong><code>{error}</code></div>}
            <div ref={endRef} />
          </div>
          <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send() }}>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              hidden
              onChange={(e) => { sendImage(e.target.files?.[0]); e.target.value = '' }}
            />
            <button type="button" className="chat-icon-btn" onClick={() => fileRef.current?.click()}
              disabled={busy} aria-label="Search by photo" title="Search by photo">
              <ImagePlus size={16} />
            </button>
            <MicButton onText={setInput} disabled={busy} />
            <input
              className="input"
              dir="auto"
              placeholder="اكتب رسالتك… / Type your message…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
            />
            <button className="send-btn" type="submit" disabled={busy || !input.trim()} aria-label="Send">
              <Send size={16} />
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}