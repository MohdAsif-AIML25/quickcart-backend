// Every HTTP call in the app goes through this file.
// Components never call fetch() directly, so authentication, token refresh,
// and error handling are written once.

const API_URL = import.meta.env.VITE_API_URL ?? '/api'

const ACCESS_KEY = 'quickcart.access_token'
const REFRESH_KEY = 'quickcart.refresh_token'

// Trade-off: localStorage survives a page reload and is simple, but any script
// running on the page can read it (XSS). A stricter design keeps the refresh
// token in an httpOnly cookie that JavaScript cannot read.
export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  save({ access_token, refresh_token }) {
    localStorage.setItem(ACCESS_KEY, access_token)
    localStorage.setItem(REFRESH_KEY, refresh_token)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export class ApiError extends Error {
  constructor(status, message, code) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

// The auth provider registers a function here, so this file can tell React
// "the session is over" without importing any React code.
let onSessionExpired = () => {}
export function setSessionExpiredHandler(handler) {
  onSessionExpired = handler
}

// The API has two error shapes. Turn both into one ApiError with a readable message.
async function toApiError(response) {
  let body = null
  try {
    body = await response.json()
  } catch {
    // Not JSON: for example an HTML error page from nginx
  }

  // 1. Our own errors: {"error": {"code": "...", "message": "..."}}
  if (body?.error?.message) {
    return new ApiError(response.status, body.error.message, body.error.code)
  }
  // 2. FastAPI validation errors (422): {"detail": [{"loc": [...], "msg": "..."}]}
  if (Array.isArray(body?.detail) && body.detail.length > 0) {
    const first = body.detail[0]
    const field = first.loc?.[first.loc.length - 1]
    const message = typeof field === 'string' ? `${field}: ${first.msg}` : first.msg
    return new ApiError(response.status, message, 'validation_error')
  }
  if (response.status === 413) {
    return new ApiError(413, 'The file is too large.', 'payload_too_large')
  }
  return new ApiError(response.status, `Request failed (HTTP ${response.status}).`, 'http_error')
}

// If five requests fail with 401 at the same moment, only ONE refresh call is
// sent. The other four wait for the same promise ("single flight").
let refreshInProgress = null

function refreshAccessToken() {
  if (!refreshInProgress) {
    refreshInProgress = (async () => {
      if (!tokens.refresh) return false
      try {
        const response = await fetch(`${API_URL}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: tokens.refresh }),
        })
        if (!response.ok) return false
        tokens.save(await response.json())
        return true
      } catch {
        return false
      }
    })().finally(() => {
      refreshInProgress = null
    })
  }
  return refreshInProgress
}

async function request(path, options = {}, isRetry = false) {
  const { method = 'GET', json, form, formData, auth = true } = options

  const headers = {}
  let body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (form) {
    body = new URLSearchParams(form) // the browser sets the form Content-Type itself
  } else if (formData) {
    body = formData // file upload: the browser adds the multipart boundary
  }
  if (auth && tokens.access) {
    headers.Authorization = `Bearer ${tokens.access}`
  }

  let response
  try {
    response = await fetch(`${API_URL}${path}`, { method, headers, body })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Please check your connection.', 'network_error')
  }

  // The access token lives for 15 minutes. When it expires, get a new one with
  // the refresh token and repeat the original request once. The user notices nothing.
  if (response.status === 401 && auth && tokens.access && !isRetry) {
    if (await refreshAccessToken()) {
      return request(path, options, true)
    }
    tokens.clear()
    onSessionExpired()
  }

  if (!response.ok) {
    throw await toApiError(response)
  }
  return response.status === 204 ? null : response.json()
}

export const api = {
  // --- Auth ---
  register: (data) => request('/auth/register', { method: 'POST', json: data, auth: false }),
  // OAuth2 password flow: form-encoded, and the email goes in the "username" field
  login: (email, password) =>
    request('/auth/login', { method: 'POST', form: { username: email, password }, auth: false }),
  me: () => request('/auth/me'),

  // --- Catalogue ---
  listProducts: ({ page = 1, limit = 12, category = '', search = '' } = {}) => {
    const query = new URLSearchParams({ page, limit })
    if (category) query.set('category', category)
    if (search) query.set('search', search)
    return request(`/products?${query}`, { auth: false })
  },

  // --- Cart and orders ---
  getCart: () => request('/cart'),
  addToCart: (productId, quantity = 1) =>
    request('/cart/items', { method: 'POST', json: { product_id: productId, quantity } }),
  removeCartItem: (itemId) => request(`/cart/items/${itemId}`, { method: 'DELETE' }),
  checkout: () => request('/orders/checkout', { method: 'POST' }),
  myOrders: () => request('/orders/me'),

  // --- Admin ---
  createProduct: (data) => request('/admin/products', { method: 'POST', json: data }),
  updateProduct: (id, changes) => request(`/admin/products/${id}`, { method: 'PATCH', json: changes }),
  deactivateProduct: (id) => request(`/admin/products/${id}`, { method: 'DELETE' }),
  uploadProductImage: (id, file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request(`/admin/products/${id}/image`, { method: 'POST', formData })
  },
  listAllOrders: ({ page = 1, limit = 20 } = {}) => request(`/admin/orders?page=${page}&limit=${limit}`),
}

// The API returns image paths such as "/uploads/products/abc.png".
export function imageSrc(imageUrl) {
  return imageUrl ? `${API_URL}${imageUrl}` : null
}
