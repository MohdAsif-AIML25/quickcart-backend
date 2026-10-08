import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api/client.js'
import Alert from '../components/Alert.jsx'
import OrderDetails from '../components/OrderDetails.jsx'
import { formatDate, formatMoney, ORDER_STATUS_LABELS } from '../format.js'

export default function OrdersPage() {
  const location = useLocation()
  const placedOrderId = location.state?.placedOrderId

  const [orders, setOrders] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api
      .myOrders()
      .then((data) => {
        if (!cancelled) setOrders(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <h1>Your orders</h1>
      {placedOrderId && (
        <Alert type="success">
          Order #{placedOrderId} is confirmed. Pay in cash when it is delivered. Thank you!
        </Alert>
      )}
      <Alert>{error}</Alert>

      {!orders && !error && <p className="muted">Loading orders…</p>}

      {orders && orders.length === 0 && (
        <p className="empty">
          You have no orders yet. <Link to="/">Browse products</Link>
        </p>
      )}

      {orders?.map((order) => (
        <section key={order.id} className="card order">
          <header className="order-header">
            <div>
              <h2>Order #{order.id}</h2>
              <span className="muted">Placed {formatDate(order.created_at)}</span>
            </div>
            <div className="order-summary">
              <span className={`tag tag-static status-${order.status}`}>
                {ORDER_STATUS_LABELS[order.status] ?? order.status}
              </span>
              <span className="total">{formatMoney(order.total_amount)}</span>
            </div>
          </header>
          <ul className="order-items">
            {order.items.map((item) => (
              <li key={item.product_id}>
                {/* The name stored in the order at checkout, not the product's current name */}
                <span>{item.product_name}</span>
                <span className="muted">
                  {item.quantity} × {formatMoney(item.unit_price)}
                </span>
              </li>
            ))}
          </ul>
          <OrderDetails order={order} />
        </section>
      ))}
    </>
  )
}
