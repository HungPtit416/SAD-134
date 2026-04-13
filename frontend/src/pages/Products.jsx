import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { addToCart, getStockByProducts, listProducts } from '../api'
import { useUserId } from '../components/Layout'
import ProductImage from '../components/ProductImage'
import { useToast } from '../components/Toast'
import { money } from '../lib/format'

export default function Products() {
  const userId = useUserId()
  const toast = useToast()
  const [products, setProducts] = useState([])
  const [stockMap, setStockMap] = useState({})
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const p = await listProducts()
      setProducts(p)
      const ids = p.map((x) => x.id)
      if (ids.length) {
        const stocks = await getStockByProducts(ids)
        const map = {}
        for (const s of stocks) map[s.product_id] = s
        setStockMap(map)
      } else {
        setStockMap({})
      }
    } catch (e) {
      setError(e?.message || 'Failed to load products')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) return products
    return products.filter((p) => `${p.name} ${p.sku}`.toLowerCase().includes(s))
  }, [products, q])

  async function onAdd(productId) {
    setLoading(true)
    setError('')
    try {
      await addToCart(userId, productId, 1)
      toast.push({ title: 'Added to cart', message: 'Product added successfully.' })
      setStockMap((prev) => {
        const cur = prev?.[productId]
        if (!cur || cur.quantity == null) return prev
        return { ...prev, [productId]: { ...cur, quantity: Math.max(0, Number(cur.quantity) - 1) } }
      })
    } catch (e) {
      setError(e?.message || 'Add to cart failed')
      toast.push({ type: 'error', title: 'Add to cart failed', message: e?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="toolbar">
        <div className="toolbarLeft">
          <div className="pageTitle">Products</div>
          <div className="pageSubtitle">Browse catalog (category is data)</div>
        </div>
        <div className="toolbarRight">
          <div className="searchBox">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search name or SKU..."
              className="searchInput"
            />
          </div>
          <button className="btn" onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="alert">{error}</div> : null}

      <div className="gridCards">
        {filtered.map((p) => (
          <div key={p.id} className="card">
            <div className="cardBody">
              {(() => {
                const s = stockMap[p.id]
                const left = s?.quantity ?? null
                const initial = s?.initial_quantity ?? null
                return (
                  <div className="productCardVertical">
                    <div className="productMedia">
                      <ProductImage name={p.name} sku={p.sku} size={220} />
                      <div className="aiBadge">AI</div>
                    </div>
                    <div className="productInfo">
                      <Link to={`/products/${p.id}`} className="productName vertical">
                        {p.name}
                      </Link>
                      <div className="priceBlock">
                        <div className="priceNow">{money(p.price, 'VND')}</div>
                      </div>

                      {left != null && initial != null ? (
                        <div className="stockBox">
                          <div className="stockLabel">Còn {left} sản phẩm</div>
                        </div>
                      ) : (
                        <div className="stockBox">
                          <div className="stockLabel">Đang cập nhật tồn kho</div>
                        </div>
                      )}

                      <button className="buyNow" onClick={() => onAdd(p.id)} disabled={loading || (left != null && left <= 0)}>
                        Mua ngay
                      </button>
                    </div>
                  </div>
                )
              })()}
            </div>
          </div>
        ))}

        {!filtered.length && !loading ? <div className="empty">No products</div> : null}
      </div>
    </div>
  )
}

