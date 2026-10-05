export default function Alert({ type = 'error', children }) {
  if (!children) return null
  // role="alert" makes screen readers announce errors as soon as they appear
  return (
    <div className={`alert alert-${type}`} role={type === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}
