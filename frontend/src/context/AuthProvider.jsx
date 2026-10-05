import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, setSessionExpiredHandler, tokens } from '../api/client.js'
import { AuthContext } from './auth.js'

export default function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // true until we know whether the visitor is already logged in
  const [loading, setLoading] = useState(() => Boolean(tokens.access))

  // On page load: if a token is stored, ask the API who it belongs to.
  useEffect(() => {
    setSessionExpiredHandler(() => setUser(null))
    if (!tokens.access) return

    let cancelled = false
    api
      .me()
      .then((currentUser) => {
        if (!cancelled) setUser(currentUser)
      })
      .catch(() => {
        // Do NOT clear the tokens here. If the session is really over (401 and the
        // refresh failed), client.js has already cleared them. Every other failure
        // (server down, or the request was cancelled because the user reloaded or
        // left the page) must not log the user out: the next page load tries again.
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email, password) => {
    tokens.save(await api.login(email, password))
    setUser(await api.me())
  }, [])

  const register = useCallback(
    async ({ email, password, fullName }) => {
      await api.register({ email, password, full_name: fullName })
      await login(email, password)
    },
    [login],
  )

  const logout = useCallback(() => {
    tokens.clear()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, isAdmin: user?.role === 'admin', login, register, logout }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
