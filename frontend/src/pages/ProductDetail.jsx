import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { addToCart, getProduct, trackEvent } from '../api'
import { useUserId } from '../components/Layout'
import { money } from '../lib/format'

export default function ProductDetail() {
  const userId = useUserId()
  const { id } = useParams()
  const [product, setProduct] = useState(null)
  const [qty, setQty] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const p = await getProduct(id)
      setProduct(p)
      trackEvent(userId, 'view', { product_id: p?.id, metadata: { source: 'product_detail' } })
    } catch (e) {
      setError(e?.message || 'Failed to load product')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [id, userId])

  async function onAdd() {
    setLoading(true)
    setError('')
    try {
      await addToCart(userId, product.id, qty)
    } catch (e) {
      setError(e?.message || 'Add to cart failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="breadcrumbs">
        <Link to="/" className="link">
          Products
        </Link>
        <span className="crumbSep">/</span>
        <span>Product detail</span>
      </div>

      {error ? <div className="alert">{error}</div> : null}

      <div className="detailCard">
        <div className="detailMedia">
          <div className="detailPlaceholder">
            <div className="phBrand">ElecShop</div>
            <div className="phName">{product?.name || 'Loading...'}</div>
          </div>
        </div>
        <div className="detailInfo">
          <div className="detailTitle">{product?.name || '...'}</div>
          <div className="metaRow">
            {product?.sku ? <span className="chip">SKU: {product.sku}</span> : null}
            {product?.category?.name ? <span className="chip">Category: {product.category.name}</span> : null}
          </div>
          <div className="detailPrice">{product ? money(product.price, product.currency) : '-'}</div>
          <div className="detailDesc">{product?.description || 'No description'}</div>

          <div className="detailActions">
            <div className="qtyBox">
              <button className="qtyBtn" onClick={() => setQty((v) => Math.max(1, v - 1))} disabled={loading}>
                -
              </button>
              <input
                className="qtyInput"
                value={qty}
                onChange={(e) => setQty(Math.max(1, Number(e.target.value || 1)))}
              />
              <button className="qtyBtn" onClick={() => setQty((v) => v + 1)} disabled={loading}>
                +
              </button>
            </div>
            <button className="btnPrimary" onClick={onAdd} disabled={loading || !product}>
              Add to cart
            </button>
            <Link className="btn" to="/cart">
              View cart
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

