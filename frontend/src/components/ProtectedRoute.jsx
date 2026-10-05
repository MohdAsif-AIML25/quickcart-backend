import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/auth.js'

// This is a convenience for the user, NOT security. Anyone can edit JavaScript
// in their browser. The real protection is the API, which answers 401 or 403.
export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading, isAdmin } = useAuth()
  const location = useLocation()

  if (loading) return <p className="muted">Loading…</p>
  if (!user) {
    // Remember where the visitor wanted to go, and send them back there after login
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (adminOnly && !isAdmin) {
    return <Navigate to="/" replace />
  }
  return children
}
