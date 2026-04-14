const PRODUCT_API = import.meta.env.VITE_PRODUCT_API_BASE || 'http://localhost:8001'
const CART_API = import.meta.env.VITE_CART_API_BASE || 'http://localhost:8002'
const ORDER_API = import.meta.env.VITE_ORDER_API_BASE || 'http://localhost:8003'
const INTERACTION_API = import.meta.env.VITE_INTERACTION_API_BASE || 'http://localhost:8006'
const AI_API = import.meta.env.VITE_AI_API_BASE || 'http://localhost:8007'

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

async function httpJson(url, options) {
  const resp = await fetch(url, options)
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '')
    throw new Error(`${resp.status} ${resp.statusText}${txt ? ` - ${txt}` : ''}`)
  }
  return await resp.json()
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
      headers: { 'Content-Type': 'application/json' },
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

export async function getCart(userId) {
  return await httpJson(`${CART_API}/api/cart/?user_id=${encodeURIComponent(userId)}`)
}

export async function getStockByProducts(productIds) {
  const ids = productIds.join(',')
  const data = await httpJson(`${import.meta.env.VITE_INVENTORY_API_BASE || 'http://localhost:8005'}/api/stock/by-products/?ids=${encodeURIComponent(ids)}`)
  return Array.isArray(data) ? data : []
}

export async function addToCart(userId, productId, quantity) {
  const res = await httpJson(`${CART_API}/api/cart/items/?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, quantity }),
  })
  trackEvent(userId, 'add_to_cart', { product_id: productId, metadata: { quantity } })
  return res
}

export async function setCartItemQuantity(userId, itemId, quantity) {
  // cart-service deletes item if quantity <= 0
  return await httpJson(`${CART_API}/api/cart/items/${itemId}/?user_id=${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quantity }),
  })
}

export async function removeCartItem(userId, itemId) {
  const resp = await fetch(
    `${CART_API}/api/cart/items/${itemId}/remove/?user_id=${encodeURIComponent(userId)}`,
    { method: 'DELETE' },
  )
  if (!resp.ok && resp.status !== 204) throw new Error(`${resp.status} ${resp.statusText}`)
}

export async function checkout(userId) {
  const order = await httpJson(`${ORDER_API}/api/checkout/?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  trackEvent(userId, 'checkout', { metadata: { order_id: order?.id } })
  return order
}

export async function listOrders(userId) {
  const data = await httpJson(`${ORDER_API}/api/orders/?user_id=${encodeURIComponent(userId)}`)
  return Array.isArray(data) ? data : data?.results || []
}

export async function getOrder(orderId, userId) {
  const url =
    userId != null
      ? `${ORDER_API}/api/orders/${orderId}/?user_id=${encodeURIComponent(userId)}`
      : `${ORDER_API}/api/orders/${orderId}/`
  return await httpJson(url)
}

export async function aiChat(userId, message) {
  return await httpJson(`${AI_API}/api/chat/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, message }),
  })
}

export async function aiRecommendations(userId, limit = 10) {
  return await httpJson(`${AI_API}/api/recommendations/?user_id=${encodeURIComponent(userId)}&limit=${encodeURIComponent(limit)}`)
}

