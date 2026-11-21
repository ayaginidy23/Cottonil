// =============================================================================
// CartPanel.jsx - The shopping cart of the Shopping Assistant
// -----------------------------------------------------------------------------
// The chatbot fills it (tool add_to_cart returns the real SKU, size and price);
// the customer can change quantities here. "Order on WhatsApp" opens WhatsApp
// with the order written out (items, sizes, quantities, total) - there is no
// online payment in this demo. WHATSAPP_NUMBER in .env sets the shop's number;
// without it WhatsApp opens and the customer chooses the chat.
// The cart is kept in this browser per account (localStorage), never on the server.
//
// Offers (from the Offers page, GET /api/chat/offers) are applied automatically:
// every running offer is tried on the cart and the one that saves the most is
// used - offers are not combined (one offer per order).
// =============================================================================
import { useEffect, useState } from 'react'
import { Minus, Plus, ShoppingCart, Trash2 } from 'lucide-react'
import { api } from '../lib/api.js'
import { fmt } from '../lib/format.js'

const key = (customerId) => `cottonil_cart_${customerId || 'guest'}`

export function loadCart(customerId) {
  try {
    const v = JSON.parse(localStorage.getItem(key(customerId)) || '[]')
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}

export function saveCart(customerId, cart) {
  try { localStorage.setItem(key(customerId), JSON.stringify(cart)) } catch { /* storage blocked */ }
}

// apply what the bot asked: {type:'add', item} / {type:'remove', product_id, size}
export function applyCartActions(cart, actions) {
  let next = [...cart]
  actions.forEach((a) => {
    if (a.type === 'add' && a.item) {
      const i = next.findIndex((c) => c.sku_id === a.item.sku_id)
      if (i >= 0) next[i] = { ...next[i], quantity: next[i].quantity + a.item.quantity }
      else next.push({ ...a.item, unit_price: Number(a.item.unit_price) })
    }
    if (a.type === 'remove') {
      next = next.filter((c) => !(c.product_id === a.product_id && (!a.size || c.size?.toUpperCase() === a.size.toUpperCase())))
    }
  })
  return next
}

let whatsappNumber = null                         // read once from GET /api/chat/config

// the offer that saves the most on this cart (or null)
export function bestOffer(cart, offers) {
  const subtotal = cart.reduce((s, c) => s + c.unit_price * c.quantity, 0)
  const units = cart.reduce((s, c) => s + c.quantity, 0)
  let best = null
  offers.forEach((o) => {
    const pct = Number(o.discount_pct)
    let base = 0
    if (o.scope === 'order') base = units >= o.min_units ? subtotal : 0
    else {
      const field = o.scope === 'category' ? 'category' : 'audience'
      base = cart.filter((c) => c[field] === o.target).reduce((s, c) => s + c.unit_price * c.quantity, 0)
    }
    const saving = Math.round(base * pct * 100) / 100
    if (saving > 0 && (!best || saving > best.saving)) best = { offer: o, saving }
  })
  return best
}

export default function CartPanel({ cart, onChange, customer }) {
  const [number, setNumber] = useState(whatsappNumber)
  const [offers, setOffers] = useState([])
  useEffect(() => {
    api.chatOffers().then(setOffers).catch(() => setOffers([]))
  }, [])
  useEffect(() => {
    if (whatsappNumber !== null) return
    api.chatConfig().then((c) => { whatsappNumber = c.whatsapp_number || ''; setNumber(whatsappNumber) })
      .catch(() => setNumber(''))
  }, [])

  const subtotal = cart.reduce((s, c) => s + c.unit_price * c.quantity, 0)
  const units = cart.reduce((s, c) => s + c.quantity, 0)
  const deal = bestOffer(cart, offers)
  const total = subtotal - (deal?.saving || 0)
  // a hint when the customer is close to an order offer ("add 1 more piece")
  const near = offers.find((o) => o.scope === 'order' && units > 0 && units < o.min_units)
  const setQty = (sku, q) => onChange(cart.map((c) => (c.sku_id === sku ? { ...c, quantity: Math.max(1, q) } : c)))
  const remove = (sku) => onChange(cart.filter((c) => c.sku_id !== sku))

  const orderText = () => {
    const lines = cart.map((c, i) =>
      `${i + 1}) ${c.name} - مقاس ${c.size}${c.color ? ` - ${c.color}` : ''} × ${c.quantity} = ${fmt(c.unit_price * c.quantity, 'egp', { compact: false })}`)
    return [
      'طلب تجريبي (Demo) - مشروع تعليمي، مش متجر كوتونيل الرسمي',
      'Demo order - learning project, not the official Cottonil store',
      ...lines,
      deal ? `العرض / Offer: ${deal.offer.title_ar} (− ${fmt(deal.saving, 'egp', { compact: false })})` : '',
      `الإجمالي / Total: ${fmt(total, 'egp', { compact: false })} (${units} قطعة)`,
      customer ? `رقم العميل / Customer: ${customer.customer_key}` : '',
      'الاسم والعنوان / Name & address: ',
    ].filter(Boolean).join('\n')
  }
  const whatsappUrl = `https://wa.me/${number || ''}?text=${encodeURIComponent(orderText())}`

  return (
    <div className="cart-panel">
      <div className="cart-head">
        <ShoppingCart size={16} />
        <strong>Cart · السلة</strong>
        <span className="muted small">{units} items</span>
      </div>
      {cart.length === 0 ? (
        <div className="muted small">Ask the bot to add a product · قول للبوت "ضيفه للسلة"</div>
      ) : (
        <>
          <ul className="cart-list">
            {cart.map((c) => (
              <li key={c.sku_id} className="cart-item">
                {c.image_url && <img src={c.image_url} alt="" referrerPolicy="no-referrer" />}
                <div className="cart-info">
                  <div className="cart-name" dir="auto">{c.name}</div>
                  <div className="muted small">Size {c.size}{c.color ? ` · ${c.color}` : ''} · {fmt(c.unit_price, 'egp', { compact: false })}</div>
                  <div className="qty">
                    <button onClick={() => setQty(c.sku_id, c.quantity - 1)} aria-label="Less"><Minus size={12} /></button>
                    <span>{c.quantity}</span>
                    <button onClick={() => setQty(c.sku_id, c.quantity + 1)} aria-label="More"><Plus size={12} /></button>
                    <button className="cart-remove" onClick={() => remove(c.sku_id)} aria-label="Remove"><Trash2 size={12} /></button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {deal && (
            <div className="cart-offer">
              <span dir="auto">🏷️ {deal.offer.title_ar}</span>
              <strong>− {fmt(deal.saving, 'egp', { compact: false })}</strong>
            </div>
          )}
          <div className="cart-total">
            <span>Total · الإجمالي</span>
            <strong>{fmt(total, 'egp', { compact: false })}</strong>
          </div>
          {!deal && near && (
            <div className="muted small" dir="auto">
              زوّد {near.min_units - units} قطعة وخد خصم {(Number(near.discount_pct) * 100).toFixed(0)}%
            </div>
          )}
          <a className="whatsapp-btn" href={whatsappUrl} target="_blank" rel="noreferrer">
            WhatsApp order · اطلب واتساب
          </a>
          <div className="demo-note" dir="auto">Demo: no real order is placed · ديمو: مفيش أوردر حقيقي بيتعمل</div>
          <button className="link-btn small" onClick={() => onChange([])}>Empty cart · فضّي السلة</button>
        </>
      )}
    </div>
  )
}
