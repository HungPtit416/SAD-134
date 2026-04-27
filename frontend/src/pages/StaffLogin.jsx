import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useToast } from '../components/Toast'
import { staffLogin } from '../api'

export default function StaffLogin() {
  const nav = useNavigate()
  const toast = useToast()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      await staffLogin(email.trim().toLowerCase(), password)
      toast.push({ title: 'Staff login', message: 'Đăng nhập staff thành công.' })
      nav('/staff/products')
    } catch (err) {
      toast.push({ type: 'error', title: 'Staff login failed', message: err?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="authWrap">
      <div className="panel authPanel">
        <div className="panelHeader">
          <div className="panelTitle">Staff Login</div>
          <Link className="link" to="/">
            Back to shop
          </Link>
        </div>
        <form className="panelBody authBody" onSubmit={onSubmit}>
          <div className="alert" style={{ marginTop: 0 }}>
            Khu vực này chỉ dành cho nhân viên (staff). Nếu bạn là khách hàng, hãy dùng trang Login bình thường.
          </div>
          <label className="field">
            <div className="fieldLabel">Email</div>
            <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field">
            <div className="fieldLabel">Password</div>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button className="btnPrimary" disabled={loading} type="submit">
            Login
          </button>
        </form>
      </div>
    </div>
  )
}

