// =============================================================================
// api.js - All calls to the FastAPI backend in one place
// =============================================================================

// Builds "?date_from=...&branch=BR001&branch=BR002" (arrays repeat the key)
function toQuery(params = {}) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    if (Array.isArray(value)) value.forEach((v) => q.append(key, v))
    else q.append(key, value)
  })
  const s = q.toString()
  return s ? `?${s}` : ''
}

async function postJSON(path, body) {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 300)}`)
  }
  return res.json()
}

async function sendJSON(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 300)}`)
  }
  return res.json()
}

async function sendDelete(path, params) {
  const res = await fetch(`/api${path}${toQuery(params)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// A random id for this browser, kept in localStorage: it is the "owner" of the
// chat history and memory when nobody is logged in. If storage is blocked we
// fall back to an id that lives until the page is closed.
let memoryId = null
export function clientId() {
  if (memoryId) return memoryId
  try {
    memoryId = localStorage.getItem('cottonil_client_id')
    if (!memoryId) {
      memoryId = crypto.randomUUID()
      localStorage.setItem('cottonil_client_id', memoryId)
    }
  } catch {
    memoryId = memoryId || Math.random().toString(36).slice(2) + Date.now().toString(36)
  }
  return memoryId
}

async function getJSON(path, params) {
  const res = await fetch(`/api${path}${toQuery(params)}`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`)
  }
  return res.json()
}

// Dashboard data only changes when the pipeline re-runs, so answers are kept in the
// browser for 10 minutes: going back to a page or to a filter you already used is
// instant. A request already on its way is shared instead of being sent twice.
const CACHE_MS = 10 * 60 * 1000
const cache = new Map()
function cachedJSON(path, params) {
  const key = path + toQuery(params)
  const hit = cache.get(key)
  if (hit && Date.now() - hit.at < CACHE_MS) return hit.promise
  const promise = getJSON(path, params).catch((e) => { cache.delete(key); throw e })
  cache.set(key, { at: Date.now(), promise })
  if (cache.size > 200) cache.delete(cache.keys().next().value)
  return promise
}

export const api = {
  apps: () => getJSON('/apps'),
  filterOptions: () => getJSON('/meta/filters'),
  app: (appId, f) =>
    cachedJSON(`/apps/${appId}`, {
      date_from: f.dateFrom,
      date_to: f.dateTo,
      branch: f.branches,
      channel: f.channels,
    }),
  demoUsers: () => getJSON('/chat/demo-users'),
  chatShop: (customerId, messages, sessionId, cart = []) =>
    postJSON('/chat/shop', { customer_id: customerId, messages, client_id: clientId(), session_id: sessionId, cart }),
  chatConfig: () => getJSON('/chat/config'),
  chatOffers: () => getJSON('/chat/offers'),

  // offers (management page)
  offers: () => getJSON('/offers'),
  addOffer: (offer) => postJSON('/offers', offer),
  setOfferActive: (id, active) => sendJSON('PATCH', `/offers/${id}`, { active }),
  deleteOffer: (id) => sendJSON('DELETE', `/offers/${id}`),
  quote: (id) => getJSON(`/chat/quote/${encodeURIComponent(id)}`),
  chatShopImage: (image, note) => postJSON('/chat/shop/image', { image, note: note || null }),
  chatAnalyst: (messages, sessionId) =>
    postJSON('/chat/analyst', { messages, client_id: clientId(), session_id: sessionId }),
  // memory: restore the open chat, start a new chat (saves memory), forget memory
  chatSession: (assistant, customerId) =>
    getJSON('/chat/session', { assistant, client_id: clientId(), customer_id: customerId }),
  newChat: (assistant, customerId, sessionId) =>
    postJSON('/chat/new', { assistant, client_id: clientId(), customer_id: customerId || null, session_id: sessionId }),
  forgetMemory: (assistant, customerId) =>
    sendDelete('/chat/memory', { assistant, client_id: clientId(), customer_id: customerId }),

  // AI tools for management
  explain: (appId, f) => postJSON(`/apps/${appId}/explain${toQuery(filterParams(f))}`, {}),
  forgetInsights: () => cache.delete('/insights'),     // after "Refresh", the next visit asks the server again
  insights: (refresh = false) => (refresh ? getJSON('/insights', { refresh: true }) : cachedJSON('/insights')),
  makeReport: (topic) => postJSON('/analyst/report', { topic, client_id: clientId() }),
  report: (id) => getJSON(`/analyst/report/${encodeURIComponent(id)}`),
  securityEvents: (limit = 200) => getJSON('/security/events', { limit }),
  securitySummary: (days = 30) => getJSON('/security/summary', { days }),

  // products + simulator
  products: (f) => cachedJSON('/products', filterParams(f)),
  product: (id, f) => cachedJSON(`/products/${encodeURIComponent(id)}`, filterParams(f)),
  simulatorBaseline: (months, f) =>
    cachedJSON('/simulator/baseline', { months, branch: f?.branches, channel: f?.channels }),
}

// the global filters as API query parameters
function filterParams(f = {}) {
  return { date_from: f.dateFrom, date_to: f.dateTo, branch: f.branches, channel: f.channels }
}
