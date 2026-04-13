import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { checkout, getCart, removeCartItem, setCartItemQuantity } from '../api'
import { useUserId } from '../components/Layout'
import { useToast } from '../components/Toast'
import { money } from '../lib/format'

export default function Cart() {
  const userId = useUserId()
  const nav = useNavigate()
  const toast = useToast()
  const [cart, setCart] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

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
        toast.push({ title: 'Removed', message: 'Item removed from cart.' })
      } else {
        await setCartItemQuantity(userId, item.id, next)
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
    </div>
  )
}

