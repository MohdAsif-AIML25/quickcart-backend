const rupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })
const dateTime = new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' })

// The API sends money as a string ("799.00") so that no precision is lost.
// We convert it to a number ONLY to display it. The frontend never adds or
// multiplies prices: every total on screen was calculated by the server.
export function formatMoney(amount) {
  return rupees.format(Number(amount))
}

export function formatDate(isoString) {
  return dateTime.format(new Date(isoString))
}

const day = new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' })

// "2026-10-15" is a calendar day without a time zone. new Date("2026-10-15")
// would read it as midnight UTC, which is the previous day in the Americas.
// Building the date from its parts keeps the day the admin chose.
export function formatDay(isoDate) {
  const [year, month, dayOfMonth] = isoDate.split('-').map(Number)
  return day.format(new Date(year, month - 1, dayOfMonth))
}

export const ORDER_STATUS_LABELS = {
  confirmed: 'Confirmed',
  processing: 'Processing',
  shipped: 'Shipped',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
}

export const PAYMENT_METHOD_LABELS = {
  cod: 'Cash on Delivery',
}

export const PAYMENT_STATUS_LABELS = {
  pending: 'Payment pending',
  paid: 'Paid',
}
