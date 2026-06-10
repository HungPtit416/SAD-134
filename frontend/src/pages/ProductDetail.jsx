import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { addToCart, getProduct, rateProduct, trackEvent } from '../api'
import ProductImage from '../components/ProductImage'
import ProductRateInput from '../components/ProductRateInput'
import ProductRating from '../components/ProductRating'
import { useAuth } from '../components/Auth'
import { useUserId } from '../components/Layout'
import { money } from '../lib/format'

function SubtypeDetails({ product }) {
  if (!product) return null
  if (product.main_category === 'BOOK' && product.book) {
    const b = product.book
    return (
      <div className="metaRow" style={{ marginTop: 8 }}>
        {b.author ? <span className="chip">Author: {b.author}</span> : null}
        {b.publisher ? <span className="chip">Publisher: {b.publisher}</span> : null}
        {b.language ? <span className="chip">Language: {b.language}</span> : null}
        {b.isbn ? <span className="chip">ISBN: {b.isbn}</span> : null}
      </div>
    )
  }
  if (product.main_category === 'ELECTRONICS' && product.electronics) {
    const e = product.electronics
    return (
      <div className="metaRow" style={{ marginTop: 8 }}>
        {e.brand ? <span className="chip">Brand: {e.brand}</span> : null}
        {e.color ? <span className="chip">Color: {e.color}</span> : null}
        {e.warranty_months != null ? <span className="chip">Warranty: {e.warranty_months} months</span> : null}
      </div>
    )
  }
  if (product.main_category === 'FASHION' && product.fashion) {
    const f = product.fashion
    return (
      <div className="metaRow" style={{ marginTop: 8 }}>
        {f.brand ? <span className="chip">Brand: {f.brand}</span> : null}
        {f.size ? <span className="chip">Size: {f.size}</span> : null}
        {f.color ? <span className="chip">Color: {f.color}</span> : null}
        {f.gender ? <span className="chip">Gender: {f.gender}</span> : null}
      </div>
    )
  }
  return null
}

export default function ProductDetail() {
  const userId = useUserId()
  const { auth } = useAuth()
  const { id } = useParams()
  const [product, setProduct] = useState(null)
  const [qty, setQty] = useState(1)
  const [loading, setLoading] = useState(false)
  const [ratingLoading, setRatingLoading] = useState(false)
  const [error, setError] = useState('')
  const canRate = !!auth?.email && userId !== 'guest'

  async function load() {
    setLoading(true)
    setError('')
    try {
      const p = await getProduct(id, userId)
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

  async function onRate(stars) {
    if (!canRate) return
    setRatingLoading(true)
    setError('')
    try {
      const p = await rateProduct(userId, product.id, stars)
      setProduct(p)
    } catch (e) {
      setError(e?.message || 'Gửi đánh giá thất bại')
    } finally {
      setRatingLoading(false)
    }
  }

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
          <ProductImage name={product?.name} sku={product?.sku} url={product?.image} size={320} />
        </div>
        <div className="detailInfo">
          <div className="detailTitle">{product?.name || '...'}</div>
          <div className="metaRow">
            {product?.sku ? <span className="chip">SKU: {product.sku}</span> : null}
            {product?.main_category ? <span className="chip">{product.main_category}</span> : null}
            {product?.category?.name ? <span className="chip">Category: {product.category.name}</span> : null}
          </div>
          <SubtypeDetails product={product} />
          <ProductRating rating={product?.ratings} count={product?.no_of_ratings} />
          {canRate ? (
            <ProductRateInput
              value={product?.my_rating}
              onRate={onRate}
              disabled={!product}
              loading={ratingLoading}
            />
          ) : (
            <div className="mutedSmall" style={{ marginTop: 6 }}>
              Đăng nhập để đánh giá sản phẩm.
            </div>
          )}
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
