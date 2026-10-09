import { Fragment, useCallback, useEffect, useState } from 'react'
import { api, imageSrc } from '../api/client.js'
import Alert from '../components/Alert.jsx'
import OrderDetails from '../components/OrderDetails.jsx'
import {
  formatDate,
  formatDay,
  formatMoney,
  ORDER_STATUS_LABELS,
  PAYMENT_METHOD_LABELS,
  PAYMENT_STATUS_LABELS,
} from '../format.js'

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
  const [reloadCount, setReloadCount] = useState(0)
  const [result, setResult] = useState({ page: null, orders: null, error: '' })
  const [message, setMessage] = useState({ type: '', text: '' })
  const [openOrderId, setOpenOrderId] = useState(null)
  const [busyOrderId, setBusyOrderId] = useState(null)

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
    // reloadCount: an admin action finished, so read the same page again
  }, [page, reloadCount])

  // "Loading" only when another page was requested. After an action the old
  // rows stay on screen until the fresh ones arrive, so the table does not jump.
  const loading = result.page !== page
  const orders = loading ? null : result.orders
  const error = loading ? '' : result.error

  // Shared wrapper: run one admin action on one order, show the result, re-read the list.
  // busyOrderId disables every button, so a double click cannot send the request twice.
  async function run(orderId, action, successText) {
    if (busyOrderId !== null) return
    setBusyOrderId(orderId)
    setMessage({ type: '', text: '' })
    try {
      await action()
      setMessage({ type: 'success', text: successText })
    } catch (err) {
      // 409: the order changed in the meantime (another admin, another tab). Show why.
      setMessage({ type: 'error', text: err.message })
    } finally {
      setBusyOrderId(null)
      setReloadCount((count) => count + 1) // success or failure: show what the server has now
    }
  }

  function changePage(nextPage) {
    setMessage({ type: '', text: '' })
    setOpenOrderId(null)
    setPage(nextPage)
  }

  return (
    <>
      <Alert type={message.type || 'error'}>{message.text}</Alert>
      <Alert>{error}</Alert>
      <section className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Order</th>
              <th scope="col">Customer</th>
              <th scope="col">Placed</th>
              <th scope="col">Status</th>
              <th scope="col">Payment</th>
              <th scope="col">Est. delivery</th>
              <th scope="col" className="num">Total</th>
              <th scope="col"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={8} className="muted">Loading…</td>
              </tr>
            )}
            {orders?.length === 0 && (
              <tr>
                <td colSpan={8} className="muted">No orders on this page.</td>
              </tr>
            )}
            {orders?.map((order) => (
              <Fragment key={order.id}>
                <tr>
                  <td>#{order.id}</td>
                  <td>User #{order.user_id}</td>
                  <td>{formatDate(order.created_at)}</td>
                  <td>
                    <span className={`tag tag-static status-${order.status}`}>
                      {ORDER_STATUS_LABELS[order.status] ?? order.status}
                    </span>
                  </td>
                  <td>
                    {order.payment_method ? (
                      <>
                        {PAYMENT_METHOD_LABELS[order.payment_method] ?? order.payment_method}
                        <div className="muted">
                          {PAYMENT_STATUS_LABELS[order.payment_status] ?? order.payment_status}
                        </div>
                      </>
                    ) : (
                      <span className="muted">Not recorded</span>
                    )}
                  </td>
                  <td>
                    {order.estimated_delivery_date ? (
                      formatDay(order.estimated_delivery_date)
                    ) : (
                      <span className="muted">{order.status === 'cancelled' ? '—' : 'Not scheduled'}</span>
                    )}
                  </td>
                  <td className="num">{formatMoney(order.total_amount)}</td>
                  <td className="num">
                    <button
                      type="button"
                      className="btn btn-small"
                      aria-expanded={openOrderId === order.id}
                      onClick={() => setOpenOrderId(openOrderId === order.id ? null : order.id)}
                    >
                      {openOrderId === order.id ? 'Close' : 'Manage'}
                    </button>
                  </td>
                </tr>
                {openOrderId === order.id && (
                  <tr className="order-manage-row">
                    <td colSpan={8}>
                      {/* The key includes the saved values: after a change the form starts fresh */}
                      <OrderManager
                        key={`${order.id}-${order.status}-${order.estimated_delivery_date}`}
                        order={order}
                        busy={busyOrderId !== null}
                        run={run}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>

      <nav className="pagination" aria-label="Pagination">
        <button type="button" className="btn btn-ghost" disabled={page <= 1} onClick={() => changePage(page - 1)}>
          ← Previous
        </button>
        <span>Page {page}</span>
        {/* The API returns a plain list with no total, so "a full page" means there may be more */}
        <button
          type="button"
          className="btn btn-ghost"
          disabled={!orders || orders.length < ORDERS_PAGE_SIZE}
          onClick={() => changePage(page + 1)}
        >
          Next →
        </button>
      </nav>
    </>
  )
}

function OrderManager({ order, busy, run }) {
  const savedDate = order.estimated_delivery_date ?? ''
  const [nextStatus, setNextStatus] = useState('')
  const [deliveryDate, setDeliveryDate] = useState(savedDate)

  // The API says what is possible (allowed_next_statuses, can_delete) and enforces it.
  // The frontend only decides which controls to show.
  const isFinal = order.allowed_next_statuses.length === 0
  const changed = nextStatus !== '' || deliveryDate !== savedDate
  const statusLabel = ORDER_STATUS_LABELS[order.status] ?? order.status

  function handleSave(event) {
    event.preventDefault()
    // PATCH: send only the fields that changed
    const changes = {}
    if (nextStatus !== '') changes.status = nextStatus
    if (deliveryDate !== savedDate) changes.estimated_delivery_date = deliveryDate || null

    if (
      changes.status === 'cancelled' &&
      !window.confirm(`Cancel order #${order.id}? Its items go back into stock. This cannot be undone.`)
    ) {
      return
    }
    run(order.id, () => api.updateOrder(order.id, changes), `Order #${order.id} updated.`)
  }

  function handleDelete() {
    const confirmed = window.confirm(
      `Delete order #${order.id}?\n\n` +
        'It disappears from the customer’s order history and from this list, ' +
        'and its items go back into stock. The record is kept in the database.',
    )
    if (confirmed) {
      run(order.id, () => api.deleteOrder(order.id), `Order #${order.id} deleted. Its items are back in stock.`)
    }
  }

  return (
    <div className="order-manage">
      <div>
        <h3>Items</h3>
        <ul className="order-items">
          {order.items.map((item) => (
            <li key={item.product_id}>
              <span>{item.product_name}</span>
              <span className="muted">
                {item.quantity} × {formatMoney(item.unit_price)}
              </span>
            </li>
          ))}
        </ul>
        <OrderDetails order={order} />
      </div>

      <div>
        <h3>Manage</h3>
        {isFinal ? (
          <p className="muted">This order is {statusLabel.toLowerCase()}. Nothing more can be changed.</p>
        ) : (
          <form className="form" onSubmit={handleSave}>
            <label>
              <span>Status</span>
              <select value={nextStatus} disabled={busy} onChange={(event) => setNextStatus(event.target.value)}>
                <option value="">{statusLabel} (no change)</option>
                {order.allowed_next_statuses.map((status) => (
                  <option key={status} value={status}>
                    Change to: {ORDER_STATUS_LABELS[status] ?? status}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Estimated delivery date</span>
              <input
                type="date"
                value={deliveryDate}
                min={order.created_at.slice(0, 10)}
                disabled={busy}
                onChange={(event) => setDeliveryDate(event.target.value)}
              />
              <span className="muted">Leave empty to show the customer “Not scheduled”.</span>
            </label>
            <div>
              <button type="submit" className="btn btn-primary" disabled={busy || !changed}>
                {busy ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          </form>
        )}

        <div className="order-delete">
          <button type="button" className="btn btn-danger" disabled={busy || !order.can_delete} onClick={handleDelete}>
            Delete order
          </button>
          {!order.can_delete && (
            <p className="muted">Only a confirmed order that has not shipped can be deleted.</p>
          )}
        </div>
      </div>
    </div>
  )
}
