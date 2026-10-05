import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import { useAuth } from '../context/auth.js'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const redirectTo = location.state?.from ?? '/'

  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setSubmitting(true)
    setError('')
    try {
      await login(form.get('email').trim(), form.get('password'))
      navigate(redirectTo, { replace: true })
    } catch (err) {
      // 401 "Invalid email or password" or 429 "Too many attempts. Try again in N seconds."
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-box card">
      <h1>Log in</h1>
      <Alert>{error}</Alert>
      <form onSubmit={handleSubmit} className="form">
        <label>
          <span>Email</span>
          <input name="email" type="email" autoComplete="email" required autoFocus />
        </label>
        <label>
          <span>Password</span>
          <input name="password" type="password" autoComplete="current-password" required />
        </label>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? 'Logging in…' : 'Log in'}
        </button>
      </form>
      <p className="muted">
        New here? <Link to="/register" state={location.state}>Create an account</Link>
      </p>
    </div>
  )
}
