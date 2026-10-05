import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth.js'
import { useCart } from '../context/cart.js'

export default function Navbar() {
  const { user, isAdmin, logout } = useAuth()
  const { cart } = useCart()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/')
  }

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <Link to="/" className="brand">
          QuickCart
        </Link>
        <nav aria-label="Main">
          <NavLink to="/" end>
            Products
          </NavLink>
          {user && (
            <>
              <NavLink to="/cart">
                Cart
                {cart.total_items > 0 && (
                  <span className="badge" aria-label={`${cart.total_items} items in cart`}>
                    {cart.total_items}
                  </span>
                )}
              </NavLink>
              <NavLink to="/orders">Orders</NavLink>
            </>
          )}
          {isAdmin && <NavLink to="/admin">Admin</NavLink>}
        </nav>
        <div className="navbar-user">
          {user ? (
            <>
              <span className="muted user-name">{user.full_name}</span>
              <button type="button" className="btn btn-ghost" onClick={handleLogout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn btn-ghost">
                Log in
              </Link>
              <Link to="/register" className="btn btn-primary">
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
