import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from './Auth'

export function useUserId() {
  const { auth } = useAuth()
  return auth?.email || 'guest'
}

function TopLink({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => (isActive ? 'navLink navLinkActive' : 'navLink')}
      end={to === '/'}
    >
      {children}
    </NavLink>
  )
}

export default function Layout() {
  const { auth, logout } = useAuth()
  return (
    <div className="appShell">
      <div className="topPromo">
        <div className="container promoInner">
          <div className="promoLeft">
            <span className="promoBadge">SAD</span>
            <span>E-commerce Microservices Demo</span>
          </div>
          <div className="promoRight"></div>
        </div>
      </div>

      <header className="header">
        <div className="container headerInner">
          <div className="brand">
            <div className="brandName">SAD Shop</div>
            <div className="brandTag">Docker • Django microservices • Frontend</div>
          </div>
          <nav className="nav">
            <TopLink to="/">Products</TopLink>
            <TopLink to="/cart">Cart</TopLink>
            <TopLink to="/orders">Orders</TopLink>
            {auth?.email ? (
              <button className="btn" onClick={logout} type="button">
                Logout
              </button>
            ) : (
              <>
                <TopLink to="/login">Login</TopLink>
                <TopLink to="/register">Register</TopLink>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="container main">
        <Outlet />
      </main>

      <footer className="footer">
        <div className="container footerInner">
          <div>User: {auth?.email || 'guest'}</div>
        </div>
      </footer>
    </div>
  )
}

