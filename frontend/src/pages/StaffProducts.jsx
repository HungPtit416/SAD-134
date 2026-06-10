import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ProductImage from '../components/ProductImage'
import ProductRating from '../components/ProductRating'
import { useToast } from '../components/Toast'
import {
  getStaffEmail,
  getStockByProducts,
  listCategories,
  listProducts,
  staffCreateProduct,
  staffDeleteProduct,
  staffLogout,
  staffUpdateProduct,
  staffUpsertStock,
} from '../api'

function emptyDraft() {
  return {
    sku: '',
    name: '',
    description: '',
    price: '',
    currency: 'VND',
    main_category: 'ELECTRONICS',
    category_id: '',
    is_active: true,
    stock_quantity: '',
    image_url: '',
    author: '',
    publisher: '',
    isbn: '',
    language: '',
    brand: '',
    color: '',
    warranty_months: '',
    size: '',
    gender: '',
  }
}

function subtypeFromProduct(p) {
  if (p.main_category === 'BOOK') {
    return {
      author: p.book?.author || '',
      publisher: p.book?.publisher || '',
      isbn: p.book?.isbn || '',
      language: p.book?.language || '',
    }
  }
  if (p.main_category === 'FASHION') {
    return {
      brand: p.fashion?.brand || '',
      color: p.fashion?.color || '',
      size: p.fashion?.size || '',
      gender: p.fashion?.gender || '',
    }
  }
  return {
    brand: p.electronics?.brand || '',
    color: p.electronics?.color || '',
    warranty_months: p.electronics?.warranty_months != null ? String(p.electronics.warranty_months) : '',
  }
}

export default function StaffProducts() {
  const nav = useNavigate()
  const toast = useToast()

  const staffEmail = getStaffEmail()
  const [loading, setLoading] = useState(true)
  const [products, setProducts] = useState([])
  const [categories, setCategories] = useState([])
  const [draft, setDraft] = useState(emptyDraft())
  const [editingId, setEditingId] = useState(null)
  const [stockByProductId, setStockByProductId] = useState({})
  const tableScrollRef = useRef(null)
  const topScrollRef = useRef(null)

  const categoriesById = useMemo(() => {
    const m = new Map()
    for (const c of categories) m.set(String(c.id), c)
    return m
  }, [categories])

  const filteredCategories = useMemo(() => {
    const tagByMain = {
      ELECTRONICS: 'electronics',
      BOOK: 'book',
      FASHION: 'fashion',
    }
    const tag = tagByMain[draft.main_category]
    if (!tag) return categories
    return categories.filter((c) => (c.tag || '').toLowerCase() === tag)
  }, [categories, draft.main_category])

  async function reload() {
    setLoading(true)
    try {
      const [cats, prods] = await Promise.all([listCategories(), listProducts()])
      setCategories(cats)
      setProducts(prods)
      const ids = prods.map((p) => p.id).filter((id) => id != null)
      if (ids.length) {
        const rows = await getStockByProducts(ids)
        const m = {}
        for (const row of rows) {
          if (row?.product_id != null) m[row.product_id] = row
        }
        setStockByProductId(m)
      } else {
        setStockByProductId({})
      }
    } catch (err) {
      toast.push({ type: 'error', title: 'Load failed', message: err?.message || '' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!staffEmail) {
      nav('/staff/login')
      return
    }
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function startCreate() {
    setEditingId(null)
    setDraft(emptyDraft())
  }

  function startEdit(p) {
    setEditingId(p.id)
    const st = stockByProductId[p.id]
    setDraft({
      sku: p.sku || '',
      name: p.name || '',
      description: p.description || '',
      price: p.price != null ? String(p.price) : '',
      currency: p.currency || 'VND',
      main_category: p.main_category || 'ELECTRONICS',
      category_id: p.category?.id != null ? String(p.category.id) : '',
      is_active: !!p.is_active,
      stock_quantity: st?.quantity != null ? String(st.quantity) : '',
      image_url: p.image || '',
      ...subtypeFromProduct(p),
    })
  }

  async function onSave(e) {
    e.preventDefault()
    const payload = {
      sku: String(draft.sku || '').trim(),
      name: String(draft.name || '').trim(),
      description: String(draft.description || ''),
      price: String(draft.price || '').trim(),
      currency: String(draft.currency || 'VND').trim().toUpperCase(),
      main_category: draft.main_category || 'ELECTRONICS',
      category_id: draft.category_id ? Number(draft.category_id) : null,
      is_active: !!draft.is_active,
      image: String(draft.image_url || '').trim() || null,
    }
    if (payload.main_category === 'BOOK') {
      payload.book = {
        author: String(draft.author || '').trim(),
        publisher: String(draft.publisher || '').trim(),
        isbn: String(draft.isbn || '').trim(),
        language: String(draft.language || '').trim(),
      }
    } else if (payload.main_category === 'FASHION') {
      payload.fashion = {
        brand: String(draft.brand || '').trim(),
        color: String(draft.color || '').trim(),
        size: String(draft.size || '').trim(),
        gender: String(draft.gender || '').trim(),
      }
    } else {
      const wm = String(draft.warranty_months || '').trim()
      payload.electronics = {
        brand: String(draft.brand || '').trim(),
        color: String(draft.color || '').trim(),
        warranty_months: wm !== '' ? Number(wm) : null,
      }
    }
    if (!payload.sku || !payload.name || !payload.price) {
      toast.push({ type: 'error', title: 'Thiếu dữ liệu', message: 'SKU, tên và giá là bắt buộc.' })
      return
    }

    try {
      let productId = editingId
      if (editingId) {
        const updated = await staffUpdateProduct(editingId, payload)
        productId = updated?.id ?? editingId
        toast.push({ title: 'Updated', message: 'Đã cập nhật sản phẩm.' })
        setDraft((d) => ({ ...d, image_url: updated?.image || '' }))
      } else {
        const created = await staffCreateProduct(payload)
        productId = created?.id
        toast.push({ title: 'Created', message: 'Đã tạo sản phẩm.' })
      }
      const sq = String(draft.stock_quantity ?? '').trim()
      if (productId != null && sq !== '') {
        const qty = Number(sq)
        if (!Number.isFinite(qty) || qty < 0 || !Number.isInteger(qty)) {
          toast.push({ type: 'error', title: 'Stock', message: 'Số lượng tồn kho phải là số nguyên >= 0.' })
          await reload()
          return
        }
        await staffUpsertStock(productId, { quantity: qty })
      }
      await reload()
      if (!editingId) startCreate()
    } catch (err) {
      toast.push({ type: 'error', title: 'Save failed', message: err?.message || '' })
    }
  }

  async function onDelete(p) {
    if (!confirm(`Xóa sản phẩm "${p?.name}" (SKU ${p?.sku})?`)) return
    try {
      await staffDeleteProduct(p.id)
      toast.push({ title: 'Deleted', message: 'Đã xóa sản phẩm.' })
      await reload()
      if (editingId === p.id) startCreate()
    } catch (err) {
      toast.push({ type: 'error', title: 'Delete failed', message: err?.message || '' })
    }
  }

  function onLogout() {
    staffLogout()
    nav('/staff/login')
  }

  function syncHorizontalScroll(source, target) {
    if (!source || !target) return
    if (target.scrollLeft !== source.scrollLeft) {
      target.scrollLeft = source.scrollLeft
    }
  }

  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <div className="panelHeader">
        <div className="panelTitle">Products</div>
      </div>

      <div
        className="panelBody"
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.65fr) minmax(360px, 0.9fr)',
          gap: 16,
          alignItems: 'start',
        }}
      >
        <section style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div style={{ fontWeight: 600 }}>Danh sách sản phẩm</div>
            <button className="btn" type="button" onClick={reload} disabled={loading}>
              Refresh
            </button>
          </div>

          <div
            ref={topScrollRef}
            onScroll={(e) => syncHorizontalScroll(e.currentTarget, tableScrollRef.current)}
            style={{
              overflowX: 'auto',
              overflowY: 'hidden',
              border: '1px solid rgba(255,255,255,0.08)',
              borderBottom: 0,
              borderTopLeftRadius: 12,
              borderTopRightRadius: 12,
              height: 16,
            }}
          >
            <div style={{ minWidth: 1100, height: 1 }} />
          </div>

          <div
            ref={tableScrollRef}
            onScroll={(e) => syncHorizontalScroll(e.currentTarget, topScrollRef.current)}
            style={{
              overflow: 'auto',
              maxHeight: '68vh',
              border: '1px solid rgba(255,255,255,0.08)',
              borderTop: 0,
              borderBottomLeftRadius: 12,
              borderBottomRightRadius: 12,
            }}
          >
            <table style={{ width: '100%', minWidth: 1100, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ textAlign: 'left', fontSize: 13, opacity: 0.9 }}>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>Ảnh</th>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>SKU</th>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>Tên</th>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>Loại</th>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>Category</th>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>Rating</th>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>Giá</th>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>Tồn kho</th>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>Active</th>
                  <th style={{ padding: '10px 12px', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }} />
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.id} style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <td style={{ padding: '10px 12px' }}>
                      <ProductImage name={p.name} sku={p.sku} url={p.image} size={48} />
                    </td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>{p.sku}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ fontWeight: 600 }}>{p.name}</div>
                      <div style={{ fontSize: 12, opacity: 0.75 }}>#{p.id}</div>
                    </td>
                    <td style={{ padding: '10px 12px' }}>{p.main_category || '—'}</td>
                    <td style={{ padding: '10px 12px' }}>{p.category?.name || '-'}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <ProductRating rating={p.ratings} count={p.no_of_ratings} compact />
                    </td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                      {p.price} {p.currency}
                    </td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                      {stockByProductId[p.id]?.quantity != null ? stockByProductId[p.id].quantity : '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>{p.is_active ? 'Yes' : 'No'}</td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                      <button className="btn" type="button" onClick={() => startEdit(p)} style={{ marginRight: 8 }}>
                        Edit
                      </button>
                      <button className="btn" type="button" onClick={() => onDelete(p)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
                {!products.length && !loading ? (
                  <tr>
                    <td colSpan={10} style={{ padding: 14, opacity: 0.7 }}>
                      No products.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel" style={{ width: '100%', minWidth: 0 }}>
          <div className="panelHeader">
            <div className="panelTitle">{editingId ? `Sửa sản phẩm #${editingId}` : 'Thêm sản phẩm'}</div>
            <button className="btn" type="button" onClick={startCreate}>
              New
            </button>
          </div>

          <form onSubmit={onSave} className="panelBody" style={{ padding: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10, alignItems: 'end' }}>
              <label className="field" style={{ margin: 0 }}>
                <div className="fieldLabel">Loại sản phẩm *</div>
                <select
                  className="input"
                  value={draft.main_category}
                  onChange={(e) => setDraft((d) => ({ ...d, main_category: e.target.value, category_id: '' }))}
                >
                  <option value="ELECTRONICS">Electronics</option>
                  <option value="BOOK">Book</option>
                  <option value="FASHION">Fashion</option>
                </select>
              </label>
              <label className="field" style={{ display: 'flex', gap: 8, alignItems: 'center', margin: 0, paddingBottom: 6 }}>
                <input
                  type="checkbox"
                  checked={!!draft.is_active}
                  onChange={(e) => setDraft((d) => ({ ...d, is_active: e.target.checked }))}
                />
                <div className="fieldLabel" style={{ margin: 0 }}>
                  Active
                </div>
              </label>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <label className="field">
                <div className="fieldLabel">SKU *</div>
                <input className="input" value={draft.sku} onChange={(e) => setDraft((d) => ({ ...d, sku: e.target.value }))} />
              </label>
              <label className="field">
                <div className="fieldLabel">Category</div>
                <select
                  className="input"
                  value={draft.category_id}
                  onChange={(e) => setDraft((d) => ({ ...d, category_id: e.target.value }))}
                >
                  <option value="">(None)</option>
                  {filteredCategories.map((c) => (
                    <option key={c.id} value={String(c.id)}>
                      {c.name} ({c.slug})
                    </option>
                  ))}
                </select>
                {draft.category_id ? (
                  <div style={{ fontSize: 12, opacity: 0.7, marginTop: 4 }}>
                    {categoriesById.get(String(draft.category_id))?.name || ''}
                  </div>
                ) : null}
              </label>
            </div>

            <label className="field">
              <div className="fieldLabel">Tên *</div>
              <input className="input" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
            </label>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 0.5fr', gap: 10 }}>
              <label className="field">
                <div className="fieldLabel">Giá *</div>
                <input
                  className="input"
                  value={draft.price}
                  onChange={(e) => setDraft((d) => ({ ...d, price: e.target.value }))}
                  placeholder="19990000.00"
                />
              </label>
              <label className="field">
                <div className="fieldLabel">Currency</div>
                <input
                  className="input"
                  value={draft.currency}
                  onChange={(e) => setDraft((d) => ({ ...d, currency: e.target.value }))}
                  placeholder="VND"
                />
              </label>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '0.5fr 1fr', gap: 10 }}>
              <label className="field">
                <div className="fieldLabel">Tồn kho</div>
                <input
                  className="input"
                  inputMode="numeric"
                  value={draft.stock_quantity}
                  onChange={(e) => setDraft((d) => ({ ...d, stock_quantity: e.target.value }))}
                  placeholder="50"
                />
              </label>
              <label className="field">
                <div className="fieldLabel">Image URL</div>
                <input
                  className="input"
                  value={draft.image_url}
                  onChange={(e) => setDraft((d) => ({ ...d, image_url: e.target.value }))}
                  placeholder="https://example.com/image.jpg"
                />
              </label>
            </div>

            <label className="field">
              <div className="fieldLabel">Mô tả</div>
              <textarea
                className="input"
                rows={3}
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
              />
            </label>

            <div className="mutedSmall">Điểm rating được tính tự động từ đánh giá của khách hàng.</div>

            {draft.main_category === 'BOOK' ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <label className="field">
                  <div className="fieldLabel">Author</div>
                  <input className="input" value={draft.author} onChange={(e) => setDraft((d) => ({ ...d, author: e.target.value }))} />
                </label>
                <label className="field">
                  <div className="fieldLabel">Publisher</div>
                  <input className="input" value={draft.publisher} onChange={(e) => setDraft((d) => ({ ...d, publisher: e.target.value }))} />
                </label>
                <label className="field">
                  <div className="fieldLabel">ISBN</div>
                  <input className="input" value={draft.isbn} onChange={(e) => setDraft((d) => ({ ...d, isbn: e.target.value }))} />
                </label>
                <label className="field">
                  <div className="fieldLabel">Language</div>
                  <input className="input" value={draft.language} onChange={(e) => setDraft((d) => ({ ...d, language: e.target.value }))} />
                </label>
              </div>
            ) : null}

            {draft.main_category === 'ELECTRONICS' ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <label className="field">
                  <div className="fieldLabel">Brand</div>
                  <input className="input" value={draft.brand} onChange={(e) => setDraft((d) => ({ ...d, brand: e.target.value }))} />
                </label>
                <label className="field">
                  <div className="fieldLabel">Color</div>
                  <input className="input" value={draft.color} onChange={(e) => setDraft((d) => ({ ...d, color: e.target.value }))} />
                </label>
                <label className="field" style={{ gridColumn: 'span 2' }}>
                  <div className="fieldLabel">Warranty (months)</div>
                  <input
                    className="input"
                    value={draft.warranty_months}
                    onChange={(e) => setDraft((d) => ({ ...d, warranty_months: e.target.value }))}
                  />
                </label>
              </div>
            ) : null}

            {draft.main_category === 'FASHION' ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <label className="field">
                  <div className="fieldLabel">Brand</div>
                  <input className="input" value={draft.brand} onChange={(e) => setDraft((d) => ({ ...d, brand: e.target.value }))} />
                </label>
                <label className="field">
                  <div className="fieldLabel">Size</div>
                  <input className="input" value={draft.size} onChange={(e) => setDraft((d) => ({ ...d, size: e.target.value }))} />
                </label>
                <label className="field">
                  <div className="fieldLabel">Color</div>
                  <input className="input" value={draft.color} onChange={(e) => setDraft((d) => ({ ...d, color: e.target.value }))} />
                </label>
                <label className="field">
                  <div className="fieldLabel">Gender</div>
                  <input className="input" value={draft.gender} onChange={(e) => setDraft((d) => ({ ...d, gender: e.target.value }))} />
                </label>
              </div>
            ) : null}

            <button className="btnPrimary" type="submit" style={{ marginTop: 4, width: '100%' }}>
              {editingId ? 'Save changes' : 'Create'}
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}
