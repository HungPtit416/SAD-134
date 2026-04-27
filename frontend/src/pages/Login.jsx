import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../components/Auth'
import { useToast } from '../components/Toast'

const USER_API = import.meta.env.VITE_USER_API_BASE || 'http://localhost:8004'

async function login(email, password) {
  const resp = await fetch(`${USER_API}/api/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: email, password }),
  })
  if (!resp.ok) throw new Error(await resp.text())
  return await resp.json()
}

export default function Login() {
  const nav = useNavigate()
  const { setAuth } = useAuth()
  const toast = useToast()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const token = await login(email.trim().toLowerCase(), password)
      setAuth({ email: email.trim().toLowerCase(), token })
      toast.push({ title: 'Logged in', message: 'Welcome back.' })
      nav('/')
    } catch (err) {
      toast.push({ type: 'error', title: 'Login failed', message: err?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="authWrap">
      <div className="panel authPanel">
        <div className="panelHeader">
          <div className="panelTitle">Login</div>
          <Link className="link" to="/register">
            Register
          </Link>
        </div>
        <form className="panelBody authBody" onSubmit={onSubmit}>
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

