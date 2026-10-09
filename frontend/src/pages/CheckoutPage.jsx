import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import { useCart } from '../context/cart.js'
import { formatMoney } from '../format.js'

const EMPTY_ADDRESS = {
  recipient_name: '',
  phone: '',
  address_line1: '',
  address_line2: '',
  city: '',
  state: '',
  postal_code: '',
  country: 'India',
}

// The order in which the fields appear, used to focus the first invalid one
const FIELD_ORDER = [
  'recipient_name',
  'phone',
  'address_line1',
  'address_line2',
  'city',
  'state',
  'postal_code',
  'country',
]

const HAS_LETTER = /\p{L}/u

// The same rules as the API (app/schemas/order.py). This copy only saves a
// round trip: the API validates again, and its answer is the one that counts.
function validate(address) {
  const errors = {}
  const value = (name) => address[name].trim()

  if (value('recipient_name').length < 2 || !HAS_LETTER.test(value('recipient_name'))) {
    errors.recipient_name = 'Enter the full name of the person receiving the order.'
  }
  if (!/^\+?\d{7,15}$/.test(value('phone').replace(/[\s\-().]/g, ''))) {
    errors.phone = 'Enter a valid phone number: 7 to 15 digits, optionally starting with +.'
  }
  if (value('address_line1').length < 3) {
    errors.address_line1 = 'Enter the house or flat number and the street.'
  }
  if (value('city').length < 2 || !HAS_LETTER.test(value('city'))) {
    errors.city = 'Enter the city.'
  }
  if (value('state').length < 2 || !HAS_LETTER.test(value('state'))) {
    errors.state = 'Enter the state.'
  }
  if (!/^[A-Za-z][A-Za-z .'-]+$/.test(value('country'))) {
    errors.country = 'Enter the country name using letters only.'
  }
  const postalCode = value('postal_code')
  if (value('country').toLowerCase() === 'india') {
    if (!/^[1-9]\d{5}$/.test(postalCode)) errors.postal_code = 'Enter a valid 6-digit PIN code.'
  } else if (!/^[A-Za-z0-9][A-Za-z0-9 -]{1,10}[A-Za-z0-9]$/.test(postalCode)) {
    errors.postal_code = 'Enter a valid postal code.'
  }
  return errors
}

export default function CheckoutPage() {
  const { cart, checkout } = useCart()
  const navigate = useNavigate()
  const formRef = useRef(null)
  // A ref, not state: it changes immediately, so a second click that arrives
  // before React re-renders the disabled button is still ignored.
  const submittingRef = useRef(false)

  const [address, setAddress] = useState(EMPTY_ADDRESS)
  const [fieldErrors, setFieldErrors] = useState({})
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  function handleChange(event) {
    const { name, value } = event.target
    setAddress((current) => ({ ...current, [name]: value }))
    // The message disappears as soon as the user starts correcting the field
    if (fieldErrors[name]) {
      setFieldErrors((current) => ({ ...current, [name]: undefined }))
    }
  }

  function showFieldErrors(errors) {
    setFieldErrors(errors)
    const firstInvalid = FIELD_ORDER.find((name) => errors[name])
    if (firstInvalid) formRef.current?.elements[firstInvalid]?.focus()
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (submittingRef.current) return

    const errors = validate(address)
    if (Object.keys(errors).length > 0) {
      setError('Please correct the highlighted fields.')
      showFieldErrors(errors)
      return
    }

    submittingRef.current = true
    setSubmitting(true)
    setError('')
    setFieldErrors({})
    try {
      const order = await checkout({ shipping_address: address, payment_method: 'cod' })
      // submitting stays true: the page is about to be replaced
      navigate('/orders', { replace: true, state: { placedOrderId: order.id } })
    } catch (err) {
      const serverFieldErrors = err.fields ?? {}
      if (Object.keys(serverFieldErrors).length > 0) {
        setError('Please correct the highlighted fields.')
        showFieldErrors(serverFieldErrors)
      } else {
        // 409: stock changed, 400: cart is empty ... the cart was re-read, so the summary is current
        setError(err.message)
      }
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  if (cart.items.length === 0 && !submitting) {
    return (
      <>
        <h1>Checkout</h1>
        <Alert>{error}</Alert>
        <p className="empty">
          Your cart is empty. <Link to="/">Browse products</Link>
        </p>
      </>
    )
  }

  const field = (name, label, props = {}) => (
    <Field
      name={name}
      label={label}
      value={address[name]}
      error={fieldErrors[name]}
      onChange={handleChange}
      disabled={submitting}
      {...props}
    />
  )

  return (
    <>
      <h1>Checkout</h1>
      <Alert>{error}</Alert>

      <div className="checkout">
        <form ref={formRef} className="card panel" onSubmit={handleSubmit} noValidate>
          <h2>Delivery address</h2>
          <div className="form form-grid">
            {field('recipient_name', 'Recipient name', { autoComplete: 'name', maxLength: 100, autoFocus: true })}
            {field('phone', 'Phone number', { type: 'tel', autoComplete: 'tel', maxLength: 25 })}
            {field('address_line1', 'Address line 1', {
              autoComplete: 'address-line1',
              maxLength: 200,
              className: 'span-2',
              placeholder: 'House or flat number, street',
            })}
            {field('address_line2', 'Address line 2 (optional)', {
              autoComplete: 'address-line2',
              maxLength: 200,
              className: 'span-2',
              placeholder: 'Area, landmark',
              required: false,
            })}
            {field('city', 'City', { autoComplete: 'address-level2', maxLength: 100 })}
            {field('state', 'State', { autoComplete: 'address-level1', maxLength: 100 })}
            {field('postal_code', 'Postal code', { autoComplete: 'postal-code', maxLength: 12 })}
            {field('country', 'Country', { autoComplete: 'country-name', maxLength: 60 })}
          </div>

          <fieldset className="payment-options" disabled={submitting}>
            <legend>Payment method</legend>
            <label className="payment-option">
              <input type="radio" name="payment_method" value="cod" checked readOnly />
              <span>
                <strong>Cash on Delivery</strong>
                <span className="muted">Pay in cash when the order arrives.</span>
              </span>
            </label>
            {/* Shown so the roadmap is visible, but disabled: nothing here can take a payment */}
            <label className="payment-option payment-option-disabled">
              <input type="radio" name="payment_method" value="upi" disabled />
              <span>
                <strong>UPI</strong>
                <span className="muted">Unavailable: no payment gateway is integrated yet.</span>
              </span>
            </label>
            <label className="payment-option payment-option-disabled">
              <input type="radio" name="payment_method" value="card" disabled />
              <span>
                <strong>Credit or debit card</strong>
                <span className="muted">Unavailable: no payment gateway is integrated yet.</span>
              </span>
            </label>
          </fieldset>

          <div className="actions">
            <Link to="/cart" className="btn btn-ghost">
              Back to cart
            </Link>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Placing order…' : 'Place order'}
            </button>
          </div>
        </form>

        <aside className="card panel" aria-label="Order summary">
          <h2>Order summary</h2>
          <ul className="order-items summary-items">
            {cart.items.map((item) => (
              <li key={item.id}>
                <span>
                  {item.product_name} <span className="muted">× {item.quantity}</span>
                </span>
                <span>{formatMoney(item.subtotal)}</span>
              </li>
            ))}
          </ul>
          <p className="summary-total">
            <span>Total</span>
            <span className="total">{formatMoney(cart.total_amount)}</span>
          </p>
          <p className="muted">You pay this amount in cash on delivery. Nothing is charged now.</p>
        </aside>
      </div>
    </>
  )
}

function Field({ name, label, error, className, required = true, ...inputProps }) {
  const errorId = `${name}-error`
  return (
    <label className={className}>
      <span>{label}</span>
      <input
        name={name}
        required={required}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={error ? errorId : undefined}
        {...inputProps}
      />
      {error && (
        <span id={errorId} className="field-error">
          {error}
        </span>
      )}
    </label>
  )
}
