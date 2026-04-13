const PRODUCT_API = import.meta.env.VITE_PRODUCT_API_BASE || 'http://localhost:8001'
const CART_API = import.meta.env.VITE_CART_API_BASE || 'http://localhost:8002'
const ORDER_API = import.meta.env.VITE_ORDER_API_BASE || 'http://localhost:8003'

async function httpJson(url, options) {
  const resp = await fetch(url, options)
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '')
    throw new Error(`${resp.status} ${resp.statusText}${txt ? ` - ${txt}` : ''}`)
  }
  return await resp.json()
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
  return await httpJson(`${CART_API}/api/cart/items/?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, quantity }),
  })
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
  return await httpJson(`${ORDER_API}/api/checkout/?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
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

