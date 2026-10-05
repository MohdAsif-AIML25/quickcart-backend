import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="empty">
      <h1>Page not found</h1>
      <p>
        <Link to="/">Go to the products page</Link>
      </p>
    </div>
  )
}
