import { imageSrc } from '../api/client.js'
import { formatMoney } from '../format.js'

function stockLabel(stock) {
  if (stock === 0) return { text: 'Out of stock', className: 'stock stock-none' }
  if (stock <= 5) return { text: `Only ${stock} left`, className: 'stock stock-low' }
  return { text: 'In stock', className: 'stock stock-ok' }
}

export default function ProductCard({ product, onAdd, adding, onCategoryClick }) {
  const stock = stockLabel(product.stock)
  const image = imageSrc(product.image_url)

  return (
    <article className="card product-card">
      <div className="product-image">
        {image ? (
          <img src={image} alt={product.name} loading="lazy" />
        ) : (
          <span className="muted" aria-hidden="true">
            No image
          </span>
        )}
      </div>
      <div className="product-body">
        <button type="button" className="tag" onClick={() => onCategoryClick(product.category)}>
          {product.category}
        </button>
        <h2 className="product-name">{product.name}</h2>
        {product.description && <p className="muted product-description">{product.description}</p>}
        <div className="product-footer">
          <div>
            <div className="price">{formatMoney(product.price)}</div>
            <div className={stock.className}>{stock.text}</div>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={product.stock === 0 || adding}
            onClick={() => onAdd(product)}
          >
            {adding ? 'Adding…' : 'Add to cart'}
          </button>
        </div>
      </div>
    </article>
  )
}
