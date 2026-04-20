import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { addToCart, aiRecommendations, getStockByProducts, trackEvent } from '../api'
import { useUserId } from '../components/Layout'
import ProductImage from '../components/ProductImage'
import { useToast } from '../components/Toast'
import { money } from '../lib/format'

export default function RecommendedForYou() {
  const userId = useUserId()
  const toast = useToast()
  const [items, setItems] = useState([])
  const [stockMap, setStockMap] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await aiRecommendations(userId, 12)
      const list = Array.isArray(res?.items) ? res.items : []
      setItems(list)
      if (list.length) {
        const ids = list.map((x) => x.id).filter(Boolean)
        try {
          const stocks = await getStockByProducts(ids)
          const map = {}
          for (const s of stocks) map[s.product_id] = s
          setStockMap(map)
        } catch {
          setStockMap({})
        }
      } else {
        setStockMap({})
      }
    } catch (e) {
      setItems([])
      setStockMap({})
      setError(e?.message || 'Không tải được gợi ý. Kiểm tra AI service (port 8007).')
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    trackEvent(userId, 'browse_recommended', { metadata: { page: 'recommended_for_you' } })
  }, [userId])

  useEffect(() => {
    load()
  }, [load])

  async function onAdd(productId) {
    setLoading(true)
    try {
      await addToCart(userId, productId, 1)
      toast.push({ title: 'Added to cart', message: 'Product added successfully.' })
      setStockMap((prev) => {
        const cur = prev?.[productId]
        if (!cur || cur.quantity == null) return prev
        return { ...prev, [productId]: { ...cur, quantity: Math.max(0, Number(cur.quantity) - 1) } }
      })
    } catch (e) {
      toast.push({ type: 'error', title: 'Add to cart failed', message: e?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="toolbar">
        <div className="toolbarLeft">
          <div className="pageTitle">Gợi ý cho bạn</div>
          <div className="pageSubtitle">Dựa trên hành vi, đồ thị Neo4j và embedding — tách khỏi catalog</div>
        </div>
        <div className="toolbarRight">
          <Link to="/" className="btn">
            ← Về Products
          </Link>
          <button type="button" className="btn btnPrimary" onClick={() => load()} disabled={loading}>
            Làm mới
          </button>
        </div>
      </div>

      {error ? <div className="alert">{error}</div> : null}

      {loading && !items.length ? <div className="empty">Đang tải gợi ý…</div> : null}

      {!loading && !error && !items.length ? (
        <div className="empty">
          Chưa có gợi ý cá nhân. Hãy xem vài sản phẩm trên trang Products rồi quay lại, hoặc kiểm tra đã train/sync AI.
        </div>
      ) : null}

      {items.length > 0 ? (
        <section className="recSection" aria-labelledby="rec-page-heading">
          <h2 id="rec-page-heading" className="visuallyHidden">
            Danh sách gợi ý
          </h2>
          <div className="recGrid">
            {items.map((p) => {
              const s = stockMap[p.id]
              const left = s?.quantity ?? null
              const initial = s?.initial_quantity ?? null
              return (
                <div key={p.id} className="card">
                  <div className="cardBody">
                    <div className="productCardVertical">
                      <div className="productMedia">
                        <ProductImage name={p.name} sku={p.sku} size={220} />
                      </div>
                      <div className="productInfo">
                        <Link to={`/products/${p.id}`} className="productName vertical">
                          {p.name}
                        </Link>
                        <div className="priceBlock">
                          <div className="priceNow">{money(p.price, 'VND')}</div>
                        </div>
                        {p.rank != null ? (
                          <div className="metaRow">
                            <span className="chip">Gợi ý #{p.rank}</span>
                          </div>
                        ) : null}
                        {left != null && initial != null ? (
                          <div className="stockBox">
                            <div className="stockLabel">Còn {left} sản phẩm</div>
                          </div>
                        ) : (
                          <div className="stockBox">
                            <div className="stockLabel">Đang cập nhật tồn kho</div>
                          </div>
                        )}
                        <button
                          className="buyNow"
                          type="button"
                          onClick={() => onAdd(p.id)}
                          disabled={loading || (left != null && left <= 0)}
                        >
                          Mua ngay
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      ) : null}
    </div>
  )
}
