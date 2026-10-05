import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import { useCart } from '../context/cart.js'
import { formatMoney } from '../format.js'

export default function CartPage() {
  const { cart, addItem, removeItem, checkout } = useCart()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // Run one cart action at a time, and show the API's message if it fails
  async function run(action) {
    setBusy(true)
    setError('')
    try {
      return await action()
    } catch (err) {
      setError(err.message)
      return null
    } finally {
      setBusy(false)
    }
  }

  async function handleCheckout() {
    const order = await run(checkout)
    if (order) {
      navigate('/orders', { state: { placedOrderId: order.id } })
    }
    // On failure (409: someone else bought the last unit) the cart was re-read, so it shows the truth.
  }

  if (cart.items.length === 0) {
    return (
      <>
        <h1>Your cart</h1>
        <Alert>{error}</Alert>
        <p className="empty">
          Your cart is empty. <Link to="/">Browse products</Link>
        </p>
      </>
    )
  }

  return (
    <>
      <h1>Your cart</h1>
      <Alert>{error}</Alert>

      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Product</th>
              <th scope="col" className="num">Price</th>
              <th scope="col" className="num">Quantity</th>
              <th scope="col" className="num">Subtotal</th>
              <th scope="col"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {cart.items.map((item) => (
              <tr key={item.id}>
                <td>{item.product_name}</td>
                <td className="num">{formatMoney(item.unit_price)}</td>
                <td className="num">
                  <span className="qty">{item.quantity}</span>
                  <button
                    type="button"
                    className="btn btn-small"
                    disabled={busy}
                    aria-label={`Add one more ${item.product_name}`}
                    onClick={() => run(() => addItem(item.product_id, 1))}
                  >
                    +1
                  </button>
                </td>
                <td className="num">{formatMoney(item.subtotal)}</td>
                <td className="num">
                  <button
                    type="button"
                    className="btn btn-small btn-danger"
                    disabled={busy}
                    aria-label={`Remove ${item.product_name}`}
                    onClick={() => run(() => removeItem(item.id))}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={2}>Total</th>
              <td className="num">{cart.total_items}</td>
              <td className="num total">{formatMoney(cart.total_amount)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="actions">
        <Link to="/" className="btn btn-ghost">
          Continue shopping
        </Link>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={handleCheckout}>
          {busy ? 'Please wait…' : 'Place order'}
        </button>
      </div>
    </>
  )
}
