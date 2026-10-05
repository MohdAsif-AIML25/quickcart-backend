import { useCallback, useEffect, useState } from 'react'
import { api, imageSrc } from '../api/client.js'
import Alert from '../components/Alert.jsx'
import { formatDate, formatMoney } from '../format.js'

const ORDERS_PAGE_SIZE = 20

export default function AdminPage() {
  const [tab, setTab] = useState('products')

  return (
    <>
      <h1>Admin</h1>
      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'products'}
          className={tab === 'products' ? 'tab active' : 'tab'}
          onClick={() => setTab('products')}
        >
          Products
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'orders'}
          className={tab === 'orders' ? 'tab active' : 'tab'}
          onClick={() => setTab('orders')}
        >
          Orders
        </button>
      </div>
      {tab === 'products' ? <ProductsAdmin /> : <OrdersAdmin />}
    </>
  )
}

function ProductsAdmin() {
  const [products, setProducts] = useState(null)
  const [message, setMessage] = useState({ type: '', text: '' })
  const [creating, setCreating] = useState(false)

  const reload = useCallback(async () => {
    // The public catalogue returns active products only (at most 100 per page)
    const data = await api.listProducts({ page: 1, limit: 100 })
    setProducts(data.items)
  }, [])

  useEffect(() => {
    let cancelled = false
    api
      .listProducts({ page: 1, limit: 100 })
      .then((data) => {
        if (!cancelled) setProducts(data.items)
      })
      .catch((err) => {
        if (!cancelled) setMessage({ type: 'error', text: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Shared wrapper: run an admin action, show the result, refresh the list
  async function run(action, successText) {
    setMessage({ type: '', text: '' })
    try {
      await action()
      await reload()
      setMessage({ type: 'success', text: successText })
      return true
    } catch (err) {
      setMessage({ type: 'error', text: err.message }) // 403, 413, 415, 422 ... all arrive here
      return false
    }
  }

  async function handleCreate(event) {
    event.preventDefault()
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    setCreating(true)
    const created = await run(
      () =>
        api.createProduct({
          name: form.get('name').trim(),
          description: form.get('description').trim() || null,
          price: form.get('price'), // sent as a string: the API parses it as an exact Decimal
          stock: Number(form.get('stock')),
          category: form.get('category').trim(),
        }),
      'Product created.',
    )
    setCreating(false)
    if (created) formElement.reset()
  }

  return (
    <>
      <Alert type={message.type || 'error'}>{message.text}</Alert>

      <section className="card panel">
        <h2>New product</h2>
        <form className="form form-grid" onSubmit={handleCreate}>
          <label>
            <span>Name</span>
            <input name="name" required minLength={2} maxLength={200} />
          </label>
          <label>
            <span>Category</span>
            <input name="category" required minLength={2} maxLength={50} placeholder="electronics" />
          </label>
          <label>
            <span>Price (₹)</span>
            <input name="price" type="number" required min="0.01" step="0.01" />
          </label>
          <label>
            <span>Stock</span>
            <input name="stock" type="number" required min="0" step="1" defaultValue="0" />
          </label>
          <label className="span-2">
            <span>Description</span>
            <textarea name="description" rows={2} maxLength={2000} />
          </label>
          <div className="span-2">
            <button type="submit" className="btn btn-primary" disabled={creating}>
              {creating ? 'Creating…' : 'Create product'}
            </button>
          </div>
        </form>
      </section>

      <section className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Product</th>
              <th scope="col">Price (₹)</th>
              <th scope="col">Stock</th>
              <th scope="col">Image</th>
              <th scope="col"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {products === null && (
              <tr>
                <td colSpan={5} className="muted">Loading…</td>
              </tr>
            )}
            {products?.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">No active products yet.</td>
              </tr>
            )}
            {products?.map((product) => (
              // The key includes the saved values: when the server's price or stock
              // changes, React builds a fresh row, so the inputs show the saved values.
              <ProductRow
                key={`${product.id}-${product.price}-${product.stock}-${product.image_url}`}
                product={product}
                run={run}
              />
            ))}
          </tbody>
        </table>
      </section>
    </>
  )
}

function ProductRow({ product, run }) {
  const [price, setPrice] = useState(product.price)
  const [stock, setStock] = useState(String(product.stock))
  const [busy, setBusy] = useState(false)

  const changed = Number(price) !== Number(product.price) || Number(stock) !== product.stock

  async function withBusy(action, successText) {
    setBusy(true)
    await run(action, successText)
    setBusy(false)
  }

  function handleSave(event) {
    event.preventDefault()
    // PATCH: send only the fields that changed
    const changes = {}
    if (Number(price) !== Number(product.price)) changes.price = price
    if (Number(stock) !== product.stock) changes.stock = Number(stock)
    withBusy(() => api.updateProduct(product.id, changes), `Updated "${product.name}".`)
  }

  function handleImage(event) {
    const file = event.target.files[0]
    event.target.value = '' // allow choosing the same file again
    if (file) {
      withBusy(() => api.uploadProductImage(product.id, file), `Image uploaded for "${product.name}".`)
    }
  }

  function handleDeactivate() {
    if (window.confirm(`Remove "${product.name}" from the catalogue?`)) {
      withBusy(() => api.deactivateProduct(product.id), `Removed "${product.name}" from the catalogue.`)
    }
  }

  const formId = `product-${product.id}`
  const image = imageSrc(product.image_url)

  return (
    <tr>
      <td>
        <strong>{product.name}</strong>
        <div className="muted">{product.category}</div>
        {/* The form is empty on purpose: the inputs in the next cells join it through form={formId} */}
        <form id={formId} onSubmit={handleSave} />
      </td>
      <td>
        <input
          form={formId}
          className="input-small"
          type="number"
          min="0.01"
          step="0.01"
          required
          value={price}
          aria-label={`Price of ${product.name}`}
          onChange={(event) => setPrice(event.target.value)}
        />
      </td>
      <td>
        <input
          form={formId}
          className="input-small"
          type="number"
          min="0"
          step="1"
          required
          value={stock}
          aria-label={`Stock of ${product.name}`}
          onChange={(event) => setStock(event.target.value)}
        />
      </td>
      <td>
        <div className="image-cell">
          {image && <img src={image} alt="" className="thumb" />}
          <label className="btn btn-small">
            {image ? 'Replace' : 'Upload'}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="sr-only"
              disabled={busy}
              aria-label={`Upload image for ${product.name}`}
              onChange={handleImage}
            />
          </label>
        </div>
      </td>
      <td className="num">
        <button type="submit" form={formId} className="btn btn-small btn-primary" disabled={busy || !changed}>
          Save
        </button>{' '}
        <button type="button" className="btn btn-small btn-danger" disabled={busy} onClick={handleDeactivate}>
          Remove
        </button>
      </td>
    </tr>
  )
}

function OrdersAdmin() {
  const [page, setPage] = useState(1)
  const [result, setResult] = useState({ page: null, orders: null, error: '' })

  useEffect(() => {
    let cancelled = false
    api
      .listAllOrders({ page, limit: ORDERS_PAGE_SIZE })
      .then((orders) => {
        if (!cancelled) setResult({ page, orders, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setResult({ page, orders: null, error: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [page])

  const loading = result.page !== page
  const orders = loading ? null : result.orders
  const error = loading ? '' : result.error

  return (
    <>
      <Alert>{error}</Alert>
      <section className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Order</th>
              <th scope="col">Customer</th>
              <th scope="col">Placed</th>
              <th scope="col">Status</th>
              <th scope="col" className="num">Items</th>
              <th scope="col" className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="muted">Loading…</td>
              </tr>
            )}
            {orders?.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">No orders on this page.</td>
              </tr>
            )}
            {orders?.map((order) => (
              <tr key={order.id}>
                <td>#{order.id}</td>
                <td>User #{order.user_id}</td>
                <td>{formatDate(order.created_at)}</td>
                <td>{order.status}</td>
                <td className="num">{order.items.reduce((sum, item) => sum + item.quantity, 0)}</td>
                <td className="num">{formatMoney(order.total_amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <nav className="pagination" aria-label="Pagination">
        <button type="button" className="btn btn-ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          ← Previous
        </button>
        <span>Page {page}</span>
        {/* The API returns a plain list with no total, so "a full page" means there may be more */}
        <button
          type="button"
          className="btn btn-ghost"
          disabled={!orders || orders.length < ORDERS_PAGE_SIZE}
          onClick={() => setPage(page + 1)}
        >
          Next →
        </button>
      </nav>
    </>
  )
}
