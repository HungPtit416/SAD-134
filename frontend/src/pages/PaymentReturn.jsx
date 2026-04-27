import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { checkoutConfirmVnpay } from '../api'
import { useUserId } from '../components/Layout'

export default function PaymentReturn() {
  const userId = useUserId()
  const loc = useLocation()
  const nav = useNavigate()
  const [status, setStatus] = useState('Verifying payment…')
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    async function run() {
      const qs = new URLSearchParams(loc.search || '')
      const obj = {}
      for (const [k, v] of qs.entries()) obj[k] = v
      try {
        const res = await checkoutConfirmVnpay(userId, obj)
        setDetail(res)
        if (res?.ok && res?.order?.id) {
          setStatus('Payment successful. Creating shipment…')
          setTimeout(() => nav(`/orders/${res.order.id}`), 800)
        } else if (res?.order?.id) {
          setStatus('Payment failed.')
        } else {
          setStatus('Verification finished.')
        }
      } catch (e) {
        setStatus(e?.message || 'Verification failed')
      }
    }
    run()
  }, [loc.search])

  return (
    <div className="panel">
      <div className="panelHeader">
        <div className="panelTitle">Payment return</div>
        <Link className="link" to="/">
          Back to home
        </Link>
      </div>
      <div className="panelBody">
        <div>{status}</div>
        {detail?.order?.id ? (
          <div style={{ marginTop: 10 }}>
            Order: <Link className="link" to={`/orders/${detail.order.id}`}>#{detail.order.id}</Link>
          </div>
        ) : null}
      </div>
    </div>
  )
}

