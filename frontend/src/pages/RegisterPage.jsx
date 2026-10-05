import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import { useAuth } from '../context/auth.js'

export default function RegisterPage() {
  const { register } = useAuth()
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
      await register({
        fullName: form.get('fullName').trim(),
        email: form.get('email').trim(),
        password: form.get('password'),
      })
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(err.message) // e.g. 409 "Email is already registered"
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-box card">
      <h1>Create an account</h1>
      <Alert>{error}</Alert>
      <form onSubmit={handleSubmit} className="form">
        <label>
          <span>Full name</span>
          <input name="fullName" type="text" autoComplete="name" required maxLength={100} autoFocus />
        </label>
        <label>
          <span>Email</span>
          <input name="email" type="email" autoComplete="email" required />
        </label>
        <label>
          <span>Password</span>
          {/* The same rules as the API (8 to 72 characters): instant feedback for the user.
              The API still validates, because browser checks can be bypassed. */}
          <input name="password" type="password" autoComplete="new-password" required minLength={8} maxLength={72} />
          <small className="muted">At least 8 characters.</small>
        </label>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Sign up'}
        </button>
      </form>
      <p className="muted">
        Already registered? <Link to="/login" state={location.state}>Log in</Link>
      </p>
    </div>
  )
}
