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
