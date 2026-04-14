function hashToHue(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 360
  return h
}

export default function ProductImage({ name, sku, size = 72 }) {
  const key = `${sku || ''}${name || ''}`
  const hue = hashToHue(key || 'product')
  const bg = `linear-gradient(135deg, hsl(${hue} 35% 94%), hsl(${(hue + 28) % 360} 35% 92%))`
  const title = (name || sku || 'Product').toString()

  return (
    <div
      className="pimg"
      style={{
        width: size,
        height: size,
        background: bg,
      }}
      aria-label="Product image placeholder (missing)"
      role="img"
    >
      <div className="pimgMissing">
        <div className="pimgMissingName" title={title}>
          {title}
        </div>
        <div className="pimgMissingIcon" aria-hidden="true">
          <svg viewBox="0 0 64 64" width="36" height="36">
            <path
              d="M14 10h36a4 4 0 0 1 4 4v36a4 4 0 0 1-4 4H14a4 4 0 0 1-4-4V14a4 4 0 0 1 4-4z"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              opacity="0.55"
            />
            <path
              d="M18 44l10-12 10 12 8-10 10 14"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.55"
            />
            <circle cx="26" cy="24" r="4" fill="currentColor" opacity="0.45" />
            <path
              d="M18 18l28 28"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              opacity="0.45"
            />
          </svg>
        </div>
      </div>
    </div>
  )
}

