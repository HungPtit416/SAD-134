const PRODUCT_API = import.meta.env.VITE_PRODUCT_API_BASE || 'http://localhost:8001'
const CART_API = import.meta.env.VITE_CART_API_BASE || 'http://localhost:8002'
const ORDER_API = import.meta.env.VITE_ORDER_API_BASE || 'http://localhost:8003'
const INTERACTION_API = import.meta.env.VITE_INTERACTION_API_BASE || 'http://localhost:8006'
const AI_API = import.meta.env.VITE_AI_API_BASE || 'http://localhost:8007'
const USER_API = import.meta.env.VITE_USER_API_BASE || 'http://localhost:8004'

const STAFF_AUTH_KEY = 'sad_staff_auth_v1'

function getSessionId() {
  try {
    const key = 'sad_session_id'
    let v = localStorage.getItem(key)
    if (!v) {
      v = `${Date.now()}-${Math.random().toString(16).slice(2)}`
      localStorage.setItem(key, v)
    }
    return v
  } catch {
    return null
  }
}

export function newChatSessionId() {
  try {
    const key = 'sad_chat_session_id'
    const v = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    localStorage.setItem(key, v)
    return v
  } catch {
    return null
  }
}

export function getChatSessionId() {
  try {
    const key = 'sad_chat_session_id'
    let v = localStorage.getItem(key)
    if (!v) {
      v = `${Date.now()}-${Math.random().toString(16).slice(2)}`
      localStorage.setItem(key, v)
    }
    return v
  } catch {
    return null
  }
}

function _looksLikeHtml(text) {
  if (!text) return false
  const s = String(text).trim().toLowerCase()
  return s.startsWith('<!doctype html') || s.startsWith('<html') || s.includes('<head>') || s.includes('<body>')
}

function _extractDetailFromJsonText(text) {
  if (!text) return null
  try {
    const obj = JSON.parse(text)
    if (!obj || typeof obj !== 'object') return null
    if (typeof obj.detail === 'string' && obj.detail.trim()) return obj.detail.trim()
    if (typeof obj.message === 'string' && obj.message.trim()) return obj.message.trim()
    return null
  } catch {
    return null
  }
}

function _friendlyHttpMessage(status, detail) {
  if (status === 401) return 'Bạn chưa đăng nhập hoặc phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.'
  if (status === 403) return 'Bạn không có quyền thực hiện thao tác này.'
  if (status === 404) return 'Không tìm thấy dữ liệu hoặc API không tồn tại.'
  if (status === 408) return 'Hết thời gian chờ. Hãy thử lại.'
  if (status === 429) return 'Bạn thao tác quá nhanh. Hãy thử lại sau ít phút.'
  if (status >= 500) return 'Hệ thống đang bận hoặc gặp lỗi. Hãy thử lại sau.'
  if (detail) return detail
  return 'Có lỗi xảy ra. Hãy thử lại.'
}

async function httpJson(url, options) {
  const authKind = options?.__authKind || 'customer'
  if (options && typeof options === 'object' && '__authKind' in options) {
    try {
      // Remove non-fetch init key
      delete options.__authKind
    } catch {
      // ignore
    }
  }
  let resp
  try {
    resp = await fetch(url, options)
  } catch (e) {
    const err = new Error('Không thể kết nối tới server. Kiểm tra gateway/backend đang chạy và thử lại.')
    err.cause = e
    err.isNetworkError = true
    err.url = url
    throw err
  }

  const contentType = (resp.headers.get('content-type') || '').toLowerCase()
  const rawText = await resp.text().catch(() => '')
  const detail =
    contentType.includes('application/json') && rawText
      ? _extractDetailFromJsonText(rawText)
      : _looksLikeHtml(rawText)
        ? null
        : String(rawText || '').trim().slice(0, 300) || null

  if (!resp.ok) {
    const msg = _friendlyHttpMessage(resp.status, detail)
    const err = new Error(msg)
    err.status = resp.status
    err.statusText = resp.statusText
    err.detail = detail
    err.url = url
    if (resp.status === 401) {
      if (authKind === 'staff') {
        try {
          localStorage.removeItem(STAFF_AUTH_KEY)
        } catch {
          // ignore
        }
        try {
          if (typeof window !== 'undefined' && window.location && !window.location.pathname.startsWith('/staff/login')) {
            window.location.href = '/staff/login'
          }
        } catch {
          // ignore
        }
      } else {
        try {
          localStorage.removeItem('sad_auth_v1')
        } catch {
          // ignore
        }
        try {
          if (typeof window !== 'undefined' && window.location && window.location.pathname !== '/login') {
            window.location.href = '/login'
          }
        } catch {
          // ignore
        }
      }
    }
    throw err
  }

  if (!rawText) return null
  try {
    return JSON.parse(rawText)
  } catch {
    // If an endpoint returns non-JSON unexpectedly, show a generic message.
    const err = new Error('Server trả về dữ liệu không hợp lệ. Hãy thử lại.')
    err.status = resp.status
    err.url = url
    err.detail = _looksLikeHtml(rawText) ? null : String(rawText).slice(0, 300)
    throw err
  }
}

function getAccessToken() {
  try {
    const raw = localStorage.getItem('sad_auth_v1')
    if (!raw) return null
    const obj = JSON.parse(raw)
    return obj?.token?.access || null
  } catch {
    return null
  }
}

function authHeaders(extra) {
  const access = getAccessToken()
  const h = { ...(extra || {}) }
  if (access) h.Authorization = `Bearer ${access}`
  return h
}

function getStaffAccessToken() {
  try {
    const raw = localStorage.getItem(STAFF_AUTH_KEY)
    if (!raw) return null
    const obj = JSON.parse(raw)
    return obj?.token?.access || null
  } catch {
    return null
  }
}

function staffAuthHeaders(extra) {
  const access = getStaffAccessToken()
  const h = { ...(extra || {}) }
  if (access) h.Authorization = `Bearer ${access}`
  return h
}

export async function trackEvent(userId, eventType, payload) {
  if (!userId) return
  const body = {
    user_id: userId,
    session_id: getSessionId(),
    event_type: eventType,
    product_id: payload?.product_id ?? null,
    query: payload?.query ?? null,
    metadata: payload?.metadata ?? {},
  }
  try {
    await fetch(`${INTERACTION_API}/api/events/`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    })
  } catch {
    // best-effort tracking
  }
}

export async function listProducts() {
  const data = await httpJson(`${PRODUCT_API}/api/products/`)
  return Array.isArray(data) ? data : data?.results || []
}

export async function getProduct(productId) {
  return await httpJson(`${PRODUCT_API}/api/products/${productId}/`)
}

export async function listCategories() {
  const data = await httpJson(`${PRODUCT_API}/api/categories/`)
  return Array.isArray(data) ? data : data?.results || []
}

export async function staffLogin(email, password) {
  const token = await httpJson(
    `${USER_API}/api/auth/staff/login/`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: email, password }),
      __authKind: 'staff',
    },
  )
  try {
    localStorage.setItem(STAFF_AUTH_KEY, JSON.stringify({ email, token }))
  } catch {
    // ignore
  }
  return token
}

export function staffLogout() {
  try {
    localStorage.removeItem(STAFF_AUTH_KEY)
  } catch {
    // ignore
  }
}

export function getStaffEmail() {
  try {
    const raw = localStorage.getItem(STAFF_AUTH_KEY)
    if (!raw) return null
    const obj = JSON.parse(raw)
    return obj?.email || null
  } catch {
    return null
  }
}

export async function staffCreateProduct(payload) {
  return await httpJson(`${PRODUCT_API}/api/products/`, {
    method: 'POST',
    headers: staffAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
    __authKind: 'staff',
  })
}

export async function staffUpdateProduct(productId, patch) {
  return await httpJson(`${PRODUCT_API}/api/products/${productId}/`, {
    method: 'PATCH',
    headers: staffAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(patch),
    __authKind: 'staff',
  })
}

export async function staffDeleteProduct(productId) {
  const resp = await fetch(`${PRODUCT_API}/api/products/${productId}/`, {
    method: 'DELETE',
    headers: staffAuthHeaders(),
  })
  if (!resp.ok && resp.status !== 204) {
    const txt = await resp.text().catch(() => '')
    const detail = _looksLikeHtml(txt) ? null : _extractDetailFromJsonText(txt) || String(txt || '').trim().slice(0, 300) || null
    const msg = _friendlyHttpMessage(resp.status, detail)
    const err = new Error(msg)
    err.status = resp.status
    err.statusText = resp.statusText
    err.detail = detail
    err.url = `${PRODUCT_API}/api/products/${productId}/`
    if (resp.status === 401) {
      try {
        localStorage.removeItem(STAFF_AUTH_KEY)
      } catch {
        // ignore
      }
    }
    throw err
  }
}

export async function getCart(userId) {
  return await httpJson(`${CART_API}/api/cart/?user_id=${encodeURIComponent(userId)}`, {
    headers: authHeaders(),
  })
}

const INVENTORY_API = import.meta.env.VITE_INVENTORY_API_BASE || 'http://localhost:8005'

export async function getStockByProducts(productIds) {
  const ids = productIds.join(',')
  const data = await httpJson(`${INVENTORY_API}/api/stock/by-products/?ids=${encodeURIComponent(ids)}`)
  return Array.isArray(data) ? data : []
}

/** Set stock for a product (inventory-service). quantity is on-hand units. */
export async function staffUpsertStock(productId, { quantity, initial_quantity } = {}) {
  const body = { product_id: Number(productId), quantity: Number(quantity) }
  if (initial_quantity != null && initial_quantity !== '') {
    body.initial_quantity = Number(initial_quantity)
  }
  return await httpJson(`${INVENTORY_API}/api/stock/upsert/`, {
    method: 'POST',
    headers: staffAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
    __authKind: 'staff',
  })
}

export async function addToCart(userId, productId, quantity) {
  const res = await httpJson(`${CART_API}/api/cart/items/?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ product_id: productId, quantity }),
  })
  trackEvent(userId, 'add_to_cart', { product_id: productId, metadata: { quantity } })
  return res
}

export async function setCartItemQuantity(userId, itemId, quantity) {
  // cart-service deletes item if quantity <= 0
  return await httpJson(`${CART_API}/api/cart/items/${itemId}/?user_id=${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ quantity }),
  })
}

export async function removeCartItem(userId, itemId) {
  const resp = await fetch(
    `${CART_API}/api/cart/items/${itemId}/remove/?user_id=${encodeURIComponent(userId)}`,
    { method: 'DELETE', headers: authHeaders() },
  )
  if (!resp.ok && resp.status !== 204) {
    const txt = await resp.text().catch(() => '')
    const detail = _looksLikeHtml(txt) ? null : _extractDetailFromJsonText(txt) || String(txt || '').trim().slice(0, 300) || null
    const msg = _friendlyHttpMessage(resp.status, detail)
    const err = new Error(msg)
    err.status = resp.status
    err.statusText = resp.statusText
    err.detail = detail
    throw err
  }
}

export async function checkout(userId) {
  throw new Error('Use checkoutStartVnpay(...) instead')
}

export async function shippingRates() {
  const base = import.meta.env.VITE_SHIPPING_API_BASE || 'http://localhost:8009'
  return await httpJson(`${base}/api/rates/`)
}

export async function checkoutStartVnpay(userId, shippingAddress, shippingMethod) {
  const res = await httpJson(`${ORDER_API}/api/checkout/start/?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      shipping_address: shippingAddress || {},
      shipping_method: shippingMethod || 'STANDARD',
    }),
  })
  const orderId = res?.order?.id
  trackEvent(userId, 'checkout_start', { metadata: { order_id: orderId, shipping_method: shippingMethod } })
  return res
}

export async function checkoutConfirmVnpay(userId, queryParams) {
  const qs = new URLSearchParams(queryParams || {}).toString()
  const res = await httpJson(`${ORDER_API}/api/checkout/confirm/?user_id=${encodeURIComponent(userId)}&${qs}`, {
    headers: authHeaders(),
  })
  const orderId = res?.order?.id
  trackEvent(userId, 'checkout_confirm', { metadata: { order_id: orderId, ok: !!res?.ok } })
  return res
}

export async function orderPayNow(userId, orderId) {
  return await httpJson(`${ORDER_API}/api/orders/${encodeURIComponent(orderId)}/pay/?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({}),
  })
}

export async function listOrders(userId) {
  const data = await httpJson(`${ORDER_API}/api/orders/?user_id=${encodeURIComponent(userId)}`, {
    headers: authHeaders(),
  })
  return Array.isArray(data) ? data : data?.results || []
}

export async function getOrder(orderId, userId) {
  const url =
    userId != null
      ? `${ORDER_API}/api/orders/${orderId}/?user_id=${encodeURIComponent(userId)}`
      : `${ORDER_API}/api/orders/${orderId}/`
  return await httpJson(url, { headers: authHeaders() })
}

export async function aiChat(userId, message) {
  return await httpJson(`${AI_API}/api/chat/`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ user_id: userId, session_id: getChatSessionId(), message }),
  })
}

export async function aiRecommendations(userId, limit = 10, query = null, seedProductIds = null, debug = false) {
  const q = query != null && String(query).trim() ? `&query=${encodeURIComponent(String(query).trim())}` : ''
  const seeds =
    Array.isArray(seedProductIds) && seedProductIds.length
      ? `&seed_product_ids=${encodeURIComponent(seedProductIds.join(','))}`
      : ''
  const dbg = debug ? `&debug=1` : ''
  return await httpJson(
    `${AI_API}/api/recommendations/?user_id=${encodeURIComponent(userId)}&limit=${encodeURIComponent(limit)}${q}${seeds}${dbg}`,
    { headers: authHeaders() },
  )
}

