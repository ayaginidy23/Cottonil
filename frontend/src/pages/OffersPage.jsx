// =============================================================================
// OffersPage.jsx - Management adds, pauses and deletes the current offers
// -----------------------------------------------------------------------------
// An offer is a discount on: one category, one audience (Men / Women / Kids...),
// or the whole order when it has N+ pieces. Running offers are told to customers
// by the Shopping Assistant (tool current_offers) and applied in its cart
// (the best offer only - offers are not combined).
// =============================================================================
import { useEffect, useState } from 'react'
import { Pause, Play, Plus, Trash2 } from 'lucide-react'
import { api } from '../lib/api.js'
import { useLang } from '../lib/i18n.jsx'

const today = () => new Date().toISOString().slice(0, 10)
const plusDays = (n) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10)
const EMPTY = { title_en: '', title_ar: '', scope: 'category', target: '', min_units: 3, pct: 15, starts_on: today(), ends_on: plusDays(30) }

export default function OffersPage() {
  const { lang, tl } = useLang()
  const ar = lang === 'ar'
  const [data, setData] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () => api.offers().then(setData).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const add = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.addOffer({
        title_en: form.title_en, title_ar: form.title_ar, scope: form.scope,
        target: form.scope === 'order' ? null : form.target,
        min_units: Number(form.min_units) || 1, discount_pct: Number(form.pct) / 100,
        starts_on: form.starts_on, ends_on: form.ends_on,
      })
      setForm(EMPTY)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  const toggle = async (o) => { await api.setOfferActive(o.promo_id, !o.active).catch((e) => setError(e.message)); load() }
  const remove = async (o) => { await api.deleteOffer(o.promo_id).catch((e) => setError(e.message)); load() }

  const targets = form.scope === 'category' ? data?.categories : data?.audiences
  const appliesTo = (o) => (o.scope === 'order'
    ? (ar ? `الأوردر كله لو فيه ${o.min_units} قطع أو أكتر` : `whole order with ${o.min_units}+ pieces`)
    : `${o.scope === 'category' ? (ar ? 'الفئة' : 'Category') : (ar ? 'الفئة العمرية / النوع' : 'Audience')}: ${tl(o.target)}`)

  return (
    <div className="app-page">
      <div className="page-head">
        <div>
          <div className="eyebrow">{ar ? 'أدوات الذكاء الاصطناعي' : 'AI Tools'}</div>
          <h1>{ar ? 'العروض' : 'Offers'}</h1>
          <p className="muted">
            {ar ? 'الإدارة بتضيف العروض هنا. مساعد التسوق بيقولها للعملاء لما يسألوا، والسلة بتطبّق أحسن عرض أوتوماتيك (العروض مش بتتجمع). عروض الجملة ليها شرائح الكمية بتاعتها.'
              : 'Management adds the offers here. The Shopping Assistant tells customers about them, and its cart applies the best offer automatically (offers are not combined). Wholesale quotes keep their volume tiers.'}
          </p>
        </div>
      </div>
      {error && <div className="error-box"><strong>Error</strong><code>{error}</code></div>}

      <div className="offers-layout">
        <section className="offer-list">
          {!data && <div className="card skeleton tall" />}
          {data?.offers.length === 0 && <div className="card empty">{ar ? 'مفيش عروض' : 'No offers yet'}</div>}
          {data?.offers.map((o) => (
            <article key={o.promo_id} className={`card offer-card ${o.running_now ? '' : 'off'}`}>
              <div className="offer-pct">{(Number(o.discount_pct) * 100).toFixed(0)}%</div>
              <div className="offer-info">
                <strong dir="auto">{ar ? o.title_ar : o.title_en}</strong>
                <span className="muted small">{appliesTo(o)}</span>
                <span className="muted small">{o.starts_on} → {o.ends_on}</span>
                <span>
                  <span className={`badge ${o.running_now ? 'live' : ''}`}>
                    {o.running_now ? (ar ? 'شغال دلوقتي' : 'Running now') : !o.active ? (ar ? 'متوقف' : 'Paused') : (ar ? 'مش في فترته' : 'Outside its dates')}
                  </span>
                </span>
              </div>
              <div className="offer-actions">
                <button className="icon-btn" title={o.active ? (ar ? 'وقّف' : 'Pause') : (ar ? 'شغّل' : 'Resume')} onClick={() => toggle(o)}>
                  {o.active ? <Pause size={15} /> : <Play size={15} />}
                </button>
                <button className="icon-btn" title={ar ? 'امسح' : 'Delete'} onClick={() => remove(o)}><Trash2 size={15} /></button>
              </div>
            </article>
          ))}
        </section>

        <form className="card offer-form" onSubmit={add}>
          <strong>{ar ? 'عرض جديد' : 'New offer'}</strong>
          <label><span className="kpi-label">{ar ? 'الاسم بالعربي' : 'Name (Arabic)'}</span>
            <input className="input" dir="rtl" required minLength={3} value={form.title_ar} onChange={set('title_ar')} placeholder="خصم 15% على البيجامات" /></label>
          <label><span className="kpi-label">{ar ? 'الاسم بالإنجليزي' : 'Name (English)'}</span>
            <input className="input" required minLength={3} value={form.title_en} onChange={set('title_en')} placeholder="15% off pajamas" /></label>
          <label><span className="kpi-label">{ar ? 'العرض على' : 'Applies to'}</span>
            <select className="input select" value={form.scope} onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value, target: '' }))}>
              <option value="category">{ar ? 'فئة منتجات' : 'A category'}</option>
              <option value="audience">{ar ? 'رجالي / حريمي / أطفال' : 'An audience'}</option>
              <option value="order">{ar ? 'الأوردر كله (عدد قطع)' : 'Whole order (pieces)'}</option>
            </select></label>
          {form.scope === 'order' ? (
            <label><span className="kpi-label">{ar ? 'أقل عدد قطع' : 'Minimum pieces'}</span>
              <input className="input" type="number" min="2" max="1000" value={form.min_units} onChange={set('min_units')} /></label>
          ) : (
            <label><span className="kpi-label">{form.scope === 'category' ? (ar ? 'الفئة' : 'Category') : (ar ? 'لمين' : 'Audience')}</span>
              <select className="input select" required value={form.target} onChange={set('target')}>
                <option value="">—</option>
                {(targets || []).map((t) => <option key={t} value={t}>{tl(t)}</option>)}
              </select></label>
          )}
          <label><span className="kpi-label">{ar ? 'نسبة الخصم %' : 'Discount %'}</span>
            <input className="input" type="number" min="1" max="70" required value={form.pct} onChange={set('pct')} /></label>
          <div className="offer-row-2">
            <label><span className="kpi-label">{ar ? 'من' : 'From'}</span>
              <input className="input" type="date" required value={form.starts_on} onChange={set('starts_on')} /></label>
            <label><span className="kpi-label">{ar ? 'لحد' : 'Until'}</span>
              <input className="input" type="date" required value={form.ends_on} onChange={set('ends_on')} /></label>
          </div>
          <button className="new-chat-btn" type="submit" disabled={busy}>
            <Plus size={16} /> {ar ? 'ضيف العرض' : 'Add offer'}
          </button>
        </form>
      </div>
    </div>
  )
}
