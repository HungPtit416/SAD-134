import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getStaffEmail, staffLogout } from '../api'

function StaffLink({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => (isActive ? 'staffNavLink staffNavLinkActive' : 'staffNavLink')}
      end={to === '/staff/products'}
    >
      {children}
    </NavLink>
  )
}

export default function StaffLayout() {
  const nav = useNavigate()
  const staffEmail = getStaffEmail()

  function onLogout() {
    staffLogout()
    nav('/staff/login')
  }

  return (
    <div className="staffShell">
      <header className="staffHeader">
        <div className="container headerInner">
          <div className="brand">
            <div className="brandName">ElecShop Staff</div>
            <div className="brandTag" style={{ color: 'rgba(255,255,255,0.7)' }}>
              Quản trị sản phẩm
            </div>
          </div>
          <nav className="nav">
            <span className="staffBadge">STAFF</span>
            <StaffLink to="/staff/products">Products</StaffLink>
            <NavLink to="/" className="staffNavLink">
              Shop
            </NavLink>
            <button className="btn" type="button" onClick={onLogout}>
              Logout
            </button>
          </nav>
        </div>
      </header>

      <main className="container main">
        {!staffEmail ? (
          <div className="alert">Bạn chưa đăng nhập staff. Hãy vào trang Staff Login.</div>
        ) : (
          <div className="staffHint">Đang đăng nhập staff: {staffEmail}</div>
        )}
        <Outlet />
      </main>
    </div>
  )
}

