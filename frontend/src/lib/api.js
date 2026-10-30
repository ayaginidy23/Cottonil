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

export const api = {
  apps: () => getJSON('/apps'),
  filterOptions: () => getJSON('/meta/filters'),
  app: (appId, f) =>
    getJSON(`/apps/${appId}`, {
      date_from: f.dateFrom,
      date_to: f.dateTo,
      branch: f.branches,
      channel: f.channels,
    }),
  demoUsers: () => getJSON('/chat/demo-users'),
  chatShop: (customerId, messages, sessionId) =>
    postJSON('/chat/shop', { customer_id: customerId, messages, client_id: clientId(), session_id: sessionId }),
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
}