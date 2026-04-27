import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getOrder, getProduct, orderPayNow } from '../api'
import { useUserId } from '../components/Layout'
import { useToast } from '../components/Toast'
import { money } from '../lib/format'

export default function OrderDetail() {
  const userId = useUserId()
  const { id } = useParams()
  const toast = useToast()
  const [order, setOrder] = useState(null)
  const [productMap, setProductMap] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const o = await getOrder(id, userId)
      setOrder(o)
      const ids = [...new Set((o?.items || []).map((it) => it.product_id).filter(Boolean))]
      const entries = await Promise.all(
        ids.map(async (pid) => {
          try {
            const p = await getProduct(pid)
            return [pid, p]
          } catch {
            return [pid, null]
          }
        }),
      )
      const map = {}
      for (const [pid, p] of entries) map[pid] = p
      setProductMap(map)
    } catch (e) {
      setError(e?.message || 'Failed to load order')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [id])

  const items = order?.items || []
  const total = useMemo(() => {
    return items.reduce((sum, it) => sum + Number(it.unit_price ?? 0) * Number(it.quantity ?? 0), 0)
  }, [items])

  const needsPayment = order?.payment_status && order.payment_status !== 'CAPTURED'

  async function onPayNow() {
    setLoading(true)
    setError('')
    try {
      const res = await orderPayNow(userId, id)
      const url = res?.payment_url
      if (!url) throw new Error('Missing payment_url')
      toast.push({ title: 'Redirecting to VNPAY', message: 'Please complete payment to update order status.' })
      window.location.href = url
    } catch (e) {
      setError(e?.message || 'Pay now failed')
      toast.push({ type: 'error', title: 'Pay now failed', message: e?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="breadcrumbs">
        <Link to="/orders" className="link">
          Orders
        </Link>
        <span className="crumbSep">/</span>
        <span>Order detail</span>
      </div>

      {error ? <div className="alert">{error}</div> : null}

      <div className="detailCard orderDetail">
        <div className="detailInfo">
          <div className="detailTitle">Order #{order?.id || '...'}</div>
          <div className="metaRow">
            {order?.status ? <span className="chip">Status: {order.status}</span> : null}
            {order?.payment_status ? <span className="chip">Payment: {order.payment_status}</span> : null}
            {order?.shipping_status ? <span className="chip">Shipping: {order.shipping_status}</span> : null}
            {order?.currency ? <span className="chip">Currency: {order.currency}</span> : null}
          </div>
          <div className="detailDesc">Created: {order?.created_at || '-'}</div>
          {order?.tracking_code ? <div className="detailDesc">Tracking: {order.tracking_code}</div> : null}
        </div>
        <div className="detailAside">
          <div className="sum compact">
            <div className="sumLabel">Total</div>
            <div className="sumValue">{money(order?.total_amount ?? total, order?.currency || 'USD')}</div>
          </div>
          {needsPayment ? (
            <button className="btnPrimary" type="button" onClick={onPayNow} disabled={loading}>
              Pay now (VNPAY)
            </button>
          ) : null}
          <Link to="/orders" className="btn">
            Back to list
          </Link>
        </div>
      </div>

      <div className="panel">
        <div className="panelHeader">
          <div className="panelTitle">Items</div>
          <div className="mutedSmall">{loading ? 'Loading...' : ''}</div>
        </div>
        <div className="panelBody">
          {!items.length ? <div className="empty">No items</div> : null}
          {items.map((it) => (
            <div key={it.id} className="lineItem">
              <div className="lineLeft">
                <div className="lineTitle">
                  {productMap?.[it.product_id]?.name ? (
                    <Link to={`/products/${it.product_id}`} className="link">
                      {productMap[it.product_id].name}
                    </Link>
                  ) : (
                    <>Product #{it.product_id}</>
                  )}
                </div>
                <div className="lineMeta">
                  <span className="chip">Qty: {it.quantity}</span>
                  <span className="chip">Unit: {money(it.unit_price, it.currency)}</span>
                </div>
              </div>
              <div className="lineRight">
                <div className="linePrice">
                  {money(Number(it.unit_price ?? 0) * Number(it.quantity ?? 0), it.currency)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

