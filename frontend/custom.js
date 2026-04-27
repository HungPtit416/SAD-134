;(function () {
  const PRODUCT_LIST_URLS = ['http://localhost:8080/product/api/products/', 'http://localhost:8001/api/products/']
  const CACHE_TTL_MS = 5 * 60 * 1000
  let _patchScheduled = false
  let _patchInFlight = false
  let _lastPatchAt = 0

  function removeIfTextMatches(sel, targets) {
    const els = Array.from(document.querySelectorAll(sel))
    for (const el of els) {
      const t = (el.textContent || '').trim()
      if (!t) continue
      if (targets.some((x) => t === x)) el.remove()
    }
  }

  function removeChipsByPrefix(prefixes) {
    const chips = Array.from(document.querySelectorAll('.chip'))
    for (const el of chips) {
      const t = (el.textContent || '').trim()
      if (!t) continue
      if (prefixes.some((p) => t.startsWith(p))) el.remove()
    }
  }

  async function fetchProducts() {
    try {
      const c = window.__sadProductsCache
      if (c && Array.isArray(c.rows) && c.rows.length && Date.now() - Number(c.at || 0) < CACHE_TTL_MS) {
        return c.rows
      }
    } catch {
      // ignore
    }
    for (const url of PRODUCT_LIST_URLS) {
      try {
        const r = await fetch(url, { credentials: 'include' })
        if (!r.ok) continue
        const data = await r.json()
        const rows = Array.isArray(data) ? data : data?.results || []
        if (Array.isArray(rows) && rows.length) {
          try {
            window.__sadProductsCache = { at: Date.now(), rows }
          } catch {
            // ignore
          }
          return rows
        }
      } catch {
        // ignore and try next
      }
    }
    return []
  }

  function idFromHref(href) {
    if (!href) return null
    const m = String(href).match(/\/products\/(\d+)/)
    return m ? Number(m[1]) : null
  }

  function ensureCategoryLabel(cardEl, categoryName) {
    if (!cardEl || !categoryName) return
    // If the built UI already shows category (or we injected before), don't duplicate.
    const existing = Array.from(cardEl.querySelectorAll('.mutedSmall'))
      .map((x) => (x.textContent || '').trim())
      .filter(Boolean)
    if (existing.some((t) => t.toLowerCase() === String(categoryName).trim().toLowerCase())) return
    if (cardEl.querySelector('.sadCategoryLabel')) return
    const label = document.createElement('div')
    label.className = 'mutedSmall sadCategoryLabel'
    label.textContent = categoryName
    const priceBlock = cardEl.querySelector('.priceBlock')
    if (priceBlock && priceBlock.parentElement) priceBlock.parentElement.insertBefore(label, priceBlock.nextSibling)
  }

  async function applyPatches() {
    if (_patchInFlight) return
    _patchInFlight = true
    // Remove specific subtitles
    removeIfTextMatches('.pageSubtitle', [
      'Dựa trên hành vi, đồ thị Neo4j và embedding — tách khỏi catalog',
      'Browse catalog (category is data)',
    ])

    // Remove "Gợi ý #..." and "Source: ..." chips on recommendation cards
    removeChipsByPrefix(['Gợi ý #', 'Source:'])

    // Add category labels on Products page cards (and other product card grids)
    const rows = await fetchProducts()
    if (!rows.length) return
    const idToCat = {}
    for (const p of rows) {
      const pid = p?.id
      const catName = p?.category?.name
      if (pid != null && catName) idToCat[String(pid)] = String(catName)
    }

    const nameLinks = Array.from(document.querySelectorAll('a.productName, a.miniRecCard'))
    for (const a of nameLinks) {
      const pid = idFromHref(a.getAttribute('href') || a.href)
      if (!pid) continue
      const cat = idToCat[String(pid)]
      if (!cat) continue
      const card = a.closest('.card') || a.closest('.miniRecCard') || a.closest('.productCardVertical') || a.parentElement
      if (!card) continue
      // For mini cards: append to its info block
      const miniInfo = card.querySelector?.('.miniRecInfo')
      if (miniInfo) {
        const existing = Array.from(miniInfo.querySelectorAll('.mutedSmall'))
          .map((x) => (x.textContent || '').trim())
          .filter(Boolean)
        if (existing.some((t) => t.toLowerCase() === String(cat).trim().toLowerCase())) continue
        if (!miniInfo.querySelector('.sadCategoryLabel')) {
          const d = document.createElement('div')
          d.className = 'mutedSmall sadCategoryLabel'
          d.textContent = cat
          miniInfo.appendChild(d)
        }
        continue
      }
      // For normal cards
      ensureCategoryLabel(card, cat)
    }
    _lastPatchAt = Date.now()
    _patchInFlight = false
  }

  function schedule() {
    if (_patchScheduled) return
    _patchScheduled = true
    setTimeout(() => {
      _patchScheduled = false
      // Avoid re-running too aggressively during heavy renders
      if (Date.now() - _lastPatchAt < 250) return
      applyPatches().catch(() => {
        _patchInFlight = false
      })
    }, 50)
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule)
  else schedule()

  function isProductsRoute() {
    const p = (window.location && window.location.pathname) || '/'
    return p === '/' || p.startsWith('/products')
  }

  function getCurrentUserFromFooter() {
    try {
      const t = (document.body && document.body.innerText) || ''
      const m = t.match(/User:\s*([^\s]+)/)
      return m ? String(m[1]).trim() : null
    } catch {
      return null
    }
  }

  function resetChatUIAndSession() {
    try {
      // rotate session id used by frontend api.js
      const v = `${Date.now()}-${Math.random().toString(16).slice(2)}`
      localStorage.setItem('sad_chat_session_id', v)
    } catch {
      // ignore
    }
    try {
      // click "New chat" button if panel exists (resets messages state in React component)
      const btn = document.querySelector('button[aria-label=\"New chat\"]')
      if (btn) btn.click()
    } catch {
      // ignore
    }
    try {
      // close panel if open
      const closeBtn = document.querySelector('button[aria-label=\"Close chat\"]')
      if (closeBtn) closeBtn.click()
    } catch {
      // ignore
    }
  }

  function applyChatVisibilityRules() {
    const dock = document.querySelector('.chatDock')
    if (!dock) return

    // Fix "New" label if needed
    const newBtn = document.querySelector('button[aria-label=\"New chat\"]')
    if (newBtn) {
      newBtn.classList.add('sadNewChatBtn')
      // Always force a stable label to avoid inconsistent renders.
      newBtn.textContent = 'Mới'
      newBtn.setAttribute('title', 'Bắt đầu cuộc chat mới')
    }

    const allow = isProductsRoute()
    dock.classList.toggle('sadChatHidden', !allow)
    if (!allow) {
      resetChatUIAndSession()
    }

    // Reset when user changes (login/register/switch account)
    const user = getCurrentUserFromFooter()
    const key = '__sadChatUser'
    const prev = window[key]
    if (user && prev && prev !== user) {
      resetChatUIAndSession()
    }
    if (user) window[key] = user
  }

  function scheduleChatRules() {
    setTimeout(() => applyChatVisibilityRules(), 30)
  }

  // Observe client-side route changes / async rendering
  try {
    const mo = new MutationObserver(() => {
      schedule()
      scheduleChatRules()
    })
    mo.observe(document.documentElement, { childList: true, subtree: true })
  } catch {
    // ignore
  }

  // Patch again on SPA navigations
  try {
    const _ps = history.pushState
    history.pushState = function () {
      const r = _ps.apply(this, arguments)
      schedule()
      scheduleChatRules()
      return r
    }
    const _rs = history.replaceState
    history.replaceState = function () {
      const r = _rs.apply(this, arguments)
      schedule()
      scheduleChatRules()
      return r
    }
    window.addEventListener('popstate', () => schedule())
    window.addEventListener('hashchange', () => schedule())
    window.addEventListener('popstate', () => scheduleChatRules())
    window.addEventListener('hashchange', () => scheduleChatRules())
  } catch {
    // ignore
  }

  // Initial chat rule application
  scheduleChatRules()
})()

