import { createContext, useContext } from 'react'

export const CartContext = createContext(null)

export function useCart() {
  const value = useContext(CartContext)
  if (!value) throw new Error('useCart must be used inside <CartProvider>')
  return value
}
