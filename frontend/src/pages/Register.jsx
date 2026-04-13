import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useToast } from '../components/Toast'

const USER_API = import.meta.env.VITE_USER_API_BASE || 'http://localhost:8004'

async function register(email, password, fullName) {
  const resp = await fetch(`${USER_API}/api/auth/register/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, full_name: fullName }),
  })
  if (!resp.ok) throw new Error(await resp.text())
  return await resp.json()
}

export default function Register() {
  const nav = useNavigate()
  const toast = useToast()
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      await register(email.trim().toLowerCase(), password, fullName)
      toast.push({ title: 'Registered', message: 'Account created. Please login.' })
      nav('/login')
    } catch (err) {
      toast.push({ type: 'error', title: 'Register failed', message: err?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="authWrap">
      <div className="panel authPanel">
        <div className="panelHeader">
          <div className="panelTitle">Register</div>
          <Link className="link" to="/login">
            Login
          </Link>
        </div>
        <form className="panelBody authBody" onSubmit={onSubmit}>
          <label className="field">
            <div className="fieldLabel">Email</div>
            <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field">
            <div className="fieldLabel">Full name</div>
            <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>
          <label className="field">
            <div className="fieldLabel">Password</div>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button className="btnPrimary" disabled={loading} type="submit">
            Create account
          </button>
        </form>
      </div>
    </div>
  )
}

