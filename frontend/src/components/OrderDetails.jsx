import { formatDate, formatDay, PAYMENT_METHOD_LABELS, PAYMENT_STATUS_LABELS } from '../format.js'

// Delivery, address and payment of one order. Used by the customer's order
// history and by the admin order list, so both always show the same facts.
export default function OrderDetails({ order }) {
  const address = order.shipping_address

  return (
    <dl className="order-details">
      <div>
        <dt>Estimated delivery</dt>
        <dd>{deliveryText(order)}</dd>
      </div>
      {order.delivered_at && (
        <div>
          <dt>Delivered</dt>
          <dd>{formatDate(order.delivered_at)}</dd>
        </div>
      )}
      <div>
        <dt>Payment</dt>
        <dd>
          {order.payment_method ? (
            <>
              {PAYMENT_METHOD_LABELS[order.payment_method] ?? order.payment_method}
              {' · '}
              {PAYMENT_STATUS_LABELS[order.payment_status] ?? order.payment_status}
            </>
          ) : (
            // Older orders: the API sends null, and we do not guess
            <span className="muted">Not recorded for this order</span>
          )}
        </dd>
      </div>
      <div>
        <dt>Delivery address</dt>
        <dd>
          {address ? (
            <address>
              {address.recipient_name}
              <br />
              {address.address_line1}
              {address.address_line2 && (
                <>
                  <br />
                  {address.address_line2}
                </>
              )}
              <br />
              {address.city}, {address.state} {address.postal_code}
              <br />
              {address.country}
              <br />
              Phone: {address.phone}
            </address>
          ) : (
            <span className="muted">
              Not recorded. This order was placed before delivery addresses were collected.
            </span>
          )}
        </dd>
      </div>
    </dl>
  )
}

function deliveryText(order) {
  if (order.status === 'cancelled') return 'Order cancelled'
  if (order.estimated_delivery_date) return formatDay(order.estimated_delivery_date)
  return 'Not scheduled'
}
