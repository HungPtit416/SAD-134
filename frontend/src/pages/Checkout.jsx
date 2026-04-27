import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { checkoutStartVnpay, getCart, shippingRates } from '../api'
import { useUserId } from '../components/Layout'
import { useToast } from '../components/Toast'
import { money } from '../lib/format'

export default function Checkout() {
  const userId = useUserId()
  const nav = useNavigate()
  const toast = useToast()
  const [cart, setCart] = useState(null)
  const [rates, setRates] = useState(null)
  const [method, setMethod] = useState('STANDARD')
  const [address, setAddress] = useState({
    full_name: '',
    phone: '',
    address_line: '',
    city: '',
    note: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const items = cart?.items || []
  const itemsTotal = useMemo(() => {
    return items.reduce((sum, it) => sum + Number(it.unit_price ?? 0) * Number(it.quantity ?? 0), 0)
  }, [items])

  const fee = useMemo(() => {
    const methods = rates?.methods || []
    const m = methods.find((x) => x.code === method)
    return Number(m?.fee ?? 0)
  }, [rates, method])

  async function load() {
    setLoading(true)
    setError('')
    try {
      setCart(await getCart(userId))
      setRates(await shippingRates())
    } catch (e) {
      setError(e?.message || 'Failed to load checkout')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function onPay() {
    if (!items.length) return
    setLoading(true)
    setError('')
    try {
      const shipping_address = { ...address }
      const res = await checkoutStartVnpay(userId, shipping_address, method)
      const paymentUrl = res?.payment_url
      if (!paymentUrl) throw new Error('Missing payment_url')
      toast.push({ title: 'Redirecting to VNPAY', message: 'Please complete payment in the new page.' })
      window.location.href = paymentUrl
    } catch (e) {
      setError(e?.message || 'Payment start failed')
      toast.push({ type: 'error', title: 'Payment start failed', message: e?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  const disabled = loading || !items.length

  return (
    <div>
      <div className="toolbar">
        <div className="toolbarLeft">
          <div className="pageTitle">Checkout</div>
          <div className="pageSubtitle">Shipping address → shipping method → pay with VNPAY (sandbox)</div>
        </div>
        <div className="toolbarRight">
          <button className="btn" onClick={() => nav('/cart')} disabled={loading}>
            Back to cart
          </button>
        </div>
      </div>

      {error ? <div className="alert">{error}</div> : null}

      <div className="panel">
        <div className="panelHeader">
          <div className="panelTitle">Shipping address</div>
        </div>
        <div className="panelBody">
          <div className="grid2">
            <label className="field">
              <div className="fieldLabel">Full name</div>
              <input className="input" value={address.full_name} onChange={(e) => setAddress((p) => ({ ...p, full_name: e.target.value }))} />
            </label>
            <label className="field">
              <div className="fieldLabel">Phone</div>
              <input className="input" value={address.phone} onChange={(e) => setAddress((p) => ({ ...p, phone: e.target.value }))} />
            </label>
          </div>
          <label className="field">
            <div className="fieldLabel">Address line</div>
            <input className="input" value={address.address_line} onChange={(e) => setAddress((p) => ({ ...p, address_line: e.target.value }))} />
          </label>
          <div className="grid2">
            <label className="field">
              <div className="fieldLabel">City</div>
              <input className="input" value={address.city} onChange={(e) => setAddress((p) => ({ ...p, city: e.target.value }))} />
            </label>
            <label className="field">
              <div className="fieldLabel">Note</div>
              <input className="input" value={address.note} onChange={(e) => setAddress((p) => ({ ...p, note: e.target.value }))} />
            </label>
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panelHeader">
          <div className="panelTitle">Shipping method</div>
        </div>
        <div className="panelBody">
          {!rates?.methods?.length ? <div className="empty">Loading shipping methods…</div> : null}
          {rates?.methods?.length ? (
            <div className="gridCards">
              {rates.methods.map((m) => (
                <button
                  key={m.code}
                  type="button"
                  className={m.code === method ? 'card cardSelected' : 'card'}
                  onClick={() => setMethod(m.code)}
                  disabled={loading}
                >
                  <div className="cardBody">
                    <div className="productName vertical">{m.name}</div>
                    <div className="mutedSmall">Fee: {money(m.fee, rates.currency || 'VND')}</div>
                  </div>
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <div className="panelFooter">
          <div className="sum">
            <div className="sumLabel">Items</div>
            <div className="sumValue">{money(itemsTotal, 'VND')}</div>
          </div>
          <div className="sum">
            <div className="sumLabel">Shipping</div>
            <div className="sumValue">{money(fee, 'VND')}</div>
          </div>
          <div className="sum">
            <div className="sumLabel">Total</div>
            <div className="sumValue">{money(itemsTotal + fee, 'VND')}</div>
          </div>
          <button className="btnPrimary" onClick={onPay} disabled={disabled}>
            Pay with VNPAY
          </button>
        </div>
      </div>
    </div>
  )
}

