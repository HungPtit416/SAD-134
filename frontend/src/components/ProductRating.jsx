function clampRating(value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return null
  return Math.min(5, Math.max(0, n))
}

export default function ProductRating({ rating, count, compact = false }) {
  const r = clampRating(rating)
  const n = Number(count)
  const hasCount = Number.isFinite(n) && n > 0

  if (r == null) {
    return compact ? null : <div className="productRating productRating--empty mutedSmall">Chưa có đánh giá</div>
  }

  const full = Math.round(r)
  const stars = `${'★'.repeat(full)}${'☆'.repeat(Math.max(0, 5 - full))}`

  return (
    <div className={`productRating${compact ? ' productRating--compact' : ''}`} aria-label={`Đánh giá ${r.toFixed(1)} trên 5`}>
      <span className="productRatingStars" aria-hidden="true">
        {stars}
      </span>
      <span className="productRatingValue">{r.toFixed(1)}</span>
      {hasCount ? <span className="productRatingCount">({n} đánh giá)</span> : null}
    </div>
  )
}
