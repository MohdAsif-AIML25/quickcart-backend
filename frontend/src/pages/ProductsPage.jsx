import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client.js'
import Alert from '../components/Alert.jsx'
import ProductCard from '../components/ProductCard.jsx'
import { useAuth } from '../context/auth.js'
import { useCart } from '../context/cart.js'

const PAGE_SIZE = 12

export default function ProductsPage() {
  // The filters live in the URL (?search=mouse&page=2), not in component state.
  // Result: the page survives a refresh, the back button works, and the link can be shared.
  const [searchParams, setSearchParams] = useSearchParams()
  const page = Math.max(1, Number(searchParams.get('page')) || 1)
  const search = searchParams.get('search') ?? ''
  const category = searchParams.get('category') ?? ''

  // The result remembers which query produced it, so we can tell "still loading" from "loaded"
  const queryKey = `${page}|${search}|${category}`
  const [result, setResult] = useState({ key: null, data: null, error: '' })
  const [notice, setNotice] = useState({ type: '', text: '' })
  const [addingId, setAddingId] = useState(null)

  const { user } = useAuth()
  const { addItem } = useCart()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    // If the filters change before the response arrives, ignore the old response.
    // Without this, a slow first request could overwrite a faster second one.
    let cancelled = false
    api
      .listProducts({ page, limit: PAGE_SIZE, search, category })
      .then((data) => {
        if (!cancelled) setResult({ key: queryKey, data, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setResult({ key: queryKey, data: null, error: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [page, search, category, queryKey])

  const loading = result.key !== queryKey
  const data = loading ? null : result.data
  const loadError = loading ? '' : result.error

  function updateFilters(changes) {
    const next = { search, category, ...changes }
    const params = {}
    if (next.search) params.search = next.search
    if (next.category) params.category = next.category
    if (next.page && next.page > 1) params.page = String(next.page)
    setSearchParams(params)
  }

  function handleFilterSubmit(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    updateFilters({
      search: form.get('search').trim(),
      category: form.get('category').trim(),
      page: 1,
    })
  }

  async function handleAdd(product) {
    if (!user) {
      navigate('/login', { state: { from: location.pathname + location.search } })
      return
    }
    setAddingId(product.id)
    setNotice({ type: '', text: '' })
    try {
      await addItem(product.id, 1)
      setNotice({ type: 'success', text: `Added "${product.name}" to your cart.` })
    } catch (err) {
      setNotice({ type: 'error', text: err.message }) // e.g. 409 "Only 2 unit(s) available"
    } finally {
      setAddingId(null)
    }
  }

  return (
    <>
      <h1>Products</h1>

      {/* key: when the URL filters change (back button, tag click), reset the inputs */}
      <form className="filters" onSubmit={handleFilterSubmit} key={`${search}|${category}`} role="search">
        <label>
          <span>Search</span>
          <input name="search" type="search" defaultValue={search} placeholder="Name or description" maxLength={100} />
        </label>
        <label>
          <span>Category</span>
          <input name="category" type="text" defaultValue={category} placeholder="e.g. electronics" maxLength={50} />
        </label>
        <button type="submit" className="btn btn-primary">
          Apply
        </button>
        {(search || category) && (
          <button type="button" className="btn btn-ghost" onClick={() => setSearchParams({})}>
            Clear
          </button>
        )}
      </form>

      <Alert type={notice.type || 'error'}>{notice.text}</Alert>
      <Alert>{loadError}</Alert>

      {loading && <p className="muted">Loading products…</p>}

      {data && data.items.length === 0 && (
        <p className="empty">No products match your filters.</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <p className="muted result-count">
            {data.total} product{data.total === 1 ? '' : 's'}
          </p>
          <div className="product-grid">
            {data.items.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                adding={addingId === product.id}
                onAdd={handleAdd}
                onCategoryClick={(value) => updateFilters({ category: value, page: 1 })}
              />
            ))}
          </div>

          {data.pages > 1 && (
            <nav className="pagination" aria-label="Pagination">
              <button
                type="button"
                className="btn btn-ghost"
                disabled={page <= 1}
                onClick={() => updateFilters({ page: page - 1 })}
              >
                ← Previous
              </button>
              <span>
                Page {data.page} of {data.pages}
              </span>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={page >= data.pages}
                onClick={() => updateFilters({ page: page + 1 })}
              >
                Next →
              </button>
            </nav>
          )}
        </>
      )}
    </>
  )
}
