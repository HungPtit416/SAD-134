import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const ToastCtx = createContext(null)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const push = useCallback((toast) => {
    const id = crypto?.randomUUID?.() || String(Date.now() + Math.random())
    const t = { id, type: 'success', durationMs: 2500, ...toast }
    setToasts((prev) => [...prev, t])
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id))
    }, t.durationMs)
  }, [])

  const api = useMemo(() => ({ push }), [push])

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div className="toastWrap" aria-live="polite" aria-relevant="additions removals">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            <div className="toastTitle">{t.title}</div>
            {t.message ? <div className="toastMsg">{t.message}</div> : null}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  const v = useContext(ToastCtx)
  if (!v) throw new Error('useToast must be used within ToastProvider')
  return v
}

