import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listOrders } from '../api'
import { useUserId } from '../components/Layout'
import { money } from '../lib/format'

export default function Orders() {
  const userId = useUserId()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      setOrders(await listOrders(userId))
    } catch (e) {
      setError(e?.message || 'Failed to load orders')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div>
      <div className="toolbar">
        <div className="toolbarLeft">
          <div className="pageTitle">Orders</div>
          <div className="pageSubtitle">Order list and detail view</div>
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
          <div className="panelTitle">Order list</div>
          <Link to="/cart" className="link">
            Go to cart
          </Link>
        </div>

        <div className="panelBody">
          {!orders.length ? <div className="empty">No orders yet</div> : null}
          {orders.map((o) => (
            <div key={o.id} className="orderRow">
              <div className="orderLeft">
                <div className="orderTitle">Order #{o.id}</div>
                <div className="orderMeta">
                  <span className="chip">Status: {o.status}</span>
                  <span className="chip">Items: {o.items?.length || 0}</span>
                </div>
              </div>
              <div className="orderRight">
                <div className="orderTotal">{money(o.total_amount, o.currency)}</div>
                <Link className="btn" to={`/orders/${o.id}`}>
                  View detail
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

