import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getOrder } from '../api'
import { useUserId } from '../components/Layout'
import { money } from '../lib/format'

export default function OrderDetail() {
  const userId = useUserId()
  const { id } = useParams()
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      setOrder(await getOrder(id, userId))
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
            {order?.currency ? <span className="chip">Currency: {order.currency}</span> : null}
          </div>
          <div className="detailDesc">Created: {order?.created_at || '-'}</div>
        </div>
        <div className="detailAside">
          <div className="sum compact">
            <div className="sumLabel">Total</div>
            <div className="sumValue">{money(order?.total_amount ?? total, order?.currency || 'USD')}</div>
          </div>
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
                <div className="lineTitle">Product #{it.product_id}</div>
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

