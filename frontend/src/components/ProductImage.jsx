function hashToHue(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 360
  return h
}

export default function ProductImage({ name, sku, size = 72 }) {
  const key = `${sku || ''}${name || ''}`
  const hue = hashToHue(key || 'product')
  const bg = `linear-gradient(135deg, hsl(${hue} 90% 92%), hsl(${(hue + 40) % 360} 90% 88%))`
  const initials = (name || sku || 'P')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()

  return (
    <div
      className="pimg"
      style={{
        width: size,
        height: size,
        background: bg,
      }}
      aria-label="Product image placeholder"
      role="img"
    >
      <div className="pimgInner">{initials}</div>
    </div>
  )
}

