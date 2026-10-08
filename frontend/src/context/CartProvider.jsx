import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client.js'
import { useAuth } from './auth.js'
import { CartContext } from './cart.js'

const EMPTY_CART = { items: [], total_items: 0, total_amount: '0.00' }

export default function CartProvider({ children }) {
  const { user } = useAuth()
  const [serverCart, setServerCart] = useState(EMPTY_CART)

  // The server is the single source of truth: after every change we re-read the cart.
  const refresh = useCallback(async () => {
    setServerCart(await api.getCart())
  }, [])

  useEffect(() => {
    if (!user) return
    let cancelled = false
    api
      .getCart()
      .then((cart) => {
        if (!cancelled) setServerCart(cart)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [user])

  const addItem = useCallback(
    async (productId, quantity = 1) => {
      await api.addToCart(productId, quantity)
      await refresh()
    },
    [refresh],
  )

  const removeItem = useCallback(
    async (itemId) => {
      await api.removeCartItem(itemId)
      await refresh()
    },
    [refresh],
  )

  const checkout = useCallback(async (data) => {
    try {
      return await api.checkout(data)
    } finally {
      // Success empties the cart; failure (409) may mean the stock changed. Re-read either way.
      await refresh().catch(() => {})
    }
  }, [refresh])

  // A logged-out visitor has no cart, whatever the last user left in memory.
  const cart = user ? serverCart : EMPTY_CART

  const value = useMemo(
    () => ({ cart, refresh, addItem, removeItem, checkout }),
    [cart, refresh, addItem, removeItem, checkout],
  )

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}
