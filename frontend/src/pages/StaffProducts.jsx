import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useToast } from '../components/Toast'
import {
  getStaffEmail,
  listCategories,
  listProducts,
  staffCreateProduct,
  staffDeleteProduct,
  staffLogout,
  staffUpdateProduct,
} from '../api'

function emptyDraft() {
  return {
    sku: '',
    name: '',
    description: '',
    price: '',
    currency: 'VND',
    category_id: '',
    is_active: true,
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

  const categoriesById = useMemo(() => {
    const m = new Map()
    for (const c of categories) m.set(String(c.id), c)
    return m
  }, [categories])

  async function reload() {
    setLoading(true)
    try {
      const [cats, prods] = await Promise.all([listCategories(), listProducts()])
      setCategories(cats)
      setProducts(prods)
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
    setDraft({
      sku: p.sku || '',
      name: p.name || '',
      description: p.description || '',
      price: p.price != null ? String(p.price) : '',
      currency: p.currency || 'VND',
      category_id: p.category?.id != null ? String(p.category.id) : '',
      is_active: !!p.is_active,
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
      category_id: draft.category_id ? Number(draft.category_id) : null,
      is_active: !!draft.is_active,
    }
    if (!payload.sku || !payload.name || !payload.price) {
      toast.push({ type: 'error', title: 'Thiếu dữ liệu', message: 'SKU, tên và giá là bắt buộc.' })
      return
    }

    try {
      if (editingId) {
        await staffUpdateProduct(editingId, payload)
        toast.push({ title: 'Updated', message: 'Đã cập nhật sản phẩm.' })
      } else {
        await staffCreateProduct(payload)
        toast.push({ title: 'Created', message: 'Đã tạo sản phẩm.' })
      }
      await reload()
      startCreate()
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

  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <div className="panelHeader">
        <div className="panelTitle">Products</div>
      </div>

      <div className="panelBody" style={{ display: 'grid', gridTemplateColumns: '1.3fr 0.9fr', gap: 14 }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div style={{ fontWeight: 600 }}>Danh sách sản phẩm</div>
            <button className="btn" type="button" onClick={reload} disabled={loading}>
              Refresh
            </button>
          </div>

          <div style={{ overflow: 'auto', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 12 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ textAlign: 'left', fontSize: 13, opacity: 0.9 }}>
                  <th style={{ padding: '10px 12px' }}>SKU</th>
                  <th style={{ padding: '10px 12px' }}>Tên</th>
                  <th style={{ padding: '10px 12px' }}>Category</th>
                  <th style={{ padding: '10px 12px' }}>Giá</th>
                  <th style={{ padding: '10px 12px' }}>Active</th>
                  <th style={{ padding: '10px 12px' }} />
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.id} style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>{p.sku}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ fontWeight: 600 }}>{p.name}</div>
                      <div style={{ fontSize: 12, opacity: 0.75 }}>#{p.id}</div>
                    </td>
                    <td style={{ padding: '10px 12px' }}>{p.category?.name || '-'}</td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                      {p.price} {p.currency}
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
                    <td colSpan={6} style={{ padding: 14, opacity: 0.7 }}>
                      No products.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div style={{ fontWeight: 600 }}>{editingId ? `Sửa sản phẩm #${editingId}` : 'Thêm sản phẩm'}</div>
            <button className="btn" type="button" onClick={startCreate}>
              New
            </button>
          </div>

          <form onSubmit={onSave} className="panel" style={{ padding: 12 }}>
            <label className="field">
              <div className="fieldLabel">SKU *</div>
              <input className="input" value={draft.sku} onChange={(e) => setDraft((d) => ({ ...d, sku: e.target.value }))} />
            </label>
            <label className="field">
              <div className="fieldLabel">Tên *</div>
              <input className="input" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
            </label>
            <label className="field">
              <div className="fieldLabel">Mô tả</div>
              <textarea
                className="input"
                rows={4}
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
              />
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 0.7fr', gap: 10 }}>
              <label className="field">
                <div className="fieldLabel">Giá *</div>
                <input
                  className="input"
                  value={draft.price}
                  onChange={(e) => setDraft((d) => ({ ...d, price: e.target.value }))}
                  placeholder="Ví dụ: 19990000.00"
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
            <label className="field">
              <div className="fieldLabel">Category</div>
              <select
                className="input"
                value={draft.category_id}
                onChange={(e) => setDraft((d) => ({ ...d, category_id: e.target.value }))}
              >
                <option value="">(None)</option>
                {categories.map((c) => (
                  <option key={c.id} value={String(c.id)}>
                    {c.name} ({c.slug})
                  </option>
                ))}
              </select>
              {draft.category_id ? (
                <div style={{ fontSize: 12, opacity: 0.7, marginTop: 6 }}>
                  Selected: {categoriesById.get(String(draft.category_id))?.name || ''}
                </div>
              ) : null}
            </label>
            <label className="field" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={!!draft.is_active}
                onChange={(e) => setDraft((d) => ({ ...d, is_active: e.target.checked }))}
              />
              <div className="fieldLabel" style={{ margin: 0 }}>
                Active
              </div>
            </label>

            <button className="btnPrimary" type="submit">
              {editingId ? 'Save changes' : 'Create'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

