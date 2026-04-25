import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { aiRecommendations, checkout, getCart, removeCartItem, setCartItemQuantity, trackEvent } from '../api'
import { useUserId } from '../components/Layout'
import ProductImage from '../components/ProductImage'
import { useToast } from '../components/Toast'
import { money } from '../lib/format'

export default function Cart() {
  const userId = useUserId()
  const nav = useNavigate()
  const toast = useToast()
  const [cart, setCart] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [recs, setRecs] = useState([])

  async function load() {
    setLoading(true)
    setError('')
    try {
      setCart(await getCart(userId))
    } catch (e) {
      setError(e?.message || 'Failed to load cart')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    let alive = true
    async function loadRecs() {
      try {
        const seedIds = (cart?.items || []).map((it) => it.product_id).filter((x) => x != null)
        const res = await aiRecommendations(userId, 6, null, seedIds)
        const items = Array.isArray(res?.items) ? res.items : []
        if (alive) setRecs(items)
      } catch {
        if (alive) setRecs([])
      }
    }
    loadRecs()
    return () => {
      alive = false
    }
  }, [userId, cart?.items?.length])

  const items = cart?.items || []
  const total = useMemo(() => {
    return items.reduce((sum, it) => sum + Number(it.unit_price ?? 0) * Number(it.quantity ?? 0), 0)
  }, [items])

  async function changeQty(item, delta) {
    const next = Number(item.quantity) + delta
    setLoading(true)
    setError('')
    try {
      if (next <= 0) {
        await removeCartItem(userId, item.id)
        trackEvent(userId, 'remove_from_cart', { product_id: item.product_id, metadata: { item_id: item.id } })
        toast.push({ title: 'Removed', message: 'Item removed from cart.' })
      } else {
        await setCartItemQuantity(userId, item.id, next)
        trackEvent(userId, 'update_cart_qty', { product_id: item.product_id, metadata: { item_id: item.id, quantity: next } })
        toast.push({ title: 'Updated', message: `Quantity updated to ${next}.` })
      }
      setCart(await getCart(userId))
    } catch (e) {
      setError(e?.message || 'Update quantity failed')
      toast.push({ type: 'error', title: 'Update failed', message: e?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  async function onCheckout() {
    setLoading(true)
    setError('')
    try {
      const order = await checkout(userId)
      toast.push({ title: 'Order created', message: `Order #${order.id} created successfully.` })
      nav(`/orders/${order.id}`)
    } catch (e) {
      setError(e?.message || 'Checkout failed')
      toast.push({ type: 'error', title: 'Checkout failed', message: e?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="toolbar">
        <div className="toolbarLeft">
          <div className="pageTitle">Cart</div>
          <div className="pageSubtitle">Increase/decrease quantity then checkout</div>
        </div>
        <div className="toolbarRight">
          <button className="btn" onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="alert">{error}</div> : null}

      <div className="panel">
        <div className="panelHeader">
          <div className="panelTitle">Items</div>
          <Link to="/" className="link">
            Continue shopping
          </Link>
        </div>

        <div className="panelBody">
          {!items.length ? <div className="empty">Cart is empty</div> : null}

          {items.map((it) => (
            <div key={it.id} className="lineItem">
              <div className="lineLeft">
                <div className="lineTitle">Product #{it.product_id}</div>
                <div className="lineMeta">
                  <span className="chip">Unit: {money(it.unit_price, it.currency)}</span>
                </div>
              </div>
              <div className="lineRight">
                <div className="qtyBox small">
                  <button className="qtyBtn" onClick={() => changeQty(it, -1)} disabled={loading}>
                    -
                  </button>
                  <div className="qtyValue">{it.quantity}</div>
                  <button className="qtyBtn" onClick={() => changeQty(it, +1)} disabled={loading}>
                    +
                  </button>
                </div>
                <div className="linePrice">{money(Number(it.unit_price ?? 0) * Number(it.quantity), it.currency)}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="panelFooter">
          <div className="sum">
            <div className="sumLabel">Total</div>
            <div className="sumValue">{money(total, 'USD')}</div>
          </div>
          <button className="btnPrimary" onClick={onCheckout} disabled={loading || !items.length}>
            Checkout
          </button>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panelHeader">
          <div className="panelTitle">Gợi ý thêm cho bạn</div>
          <Link to="/recommended" className="link">
            Xem đầy đủ
          </Link>
        </div>
        <div className="panelBody">
          {!recs.length ? <div className="empty">Chưa có gợi ý. Hãy xem sản phẩm hoặc thêm vào giỏ hàng để tăng tín hiệu.</div> : null}
          {recs.length ? (
            <div className="miniRecGrid">
              {recs.slice(0, 6).map((p) => (
                <Link key={p.id} to={`/products/${p.id}`} className="miniRecCard">
                  <div className="miniRecImg">
                    <ProductImage name={p.name} sku={p.sku} size={96} />
                  </div>
                  <div className="miniRecInfo">
                    <div className="miniRecName">{p.name}</div>
                    <div className="miniRecPrice">{money(p.price, 'VND')}</div>
                  </div>
                </Link>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

