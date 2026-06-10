import { useState } from 'react'

export default function ProductRateInput({ value, onRate, disabled = false, loading = false }) {
  const [hover, setHover] = useState(0)
  const current = Number(value) || 0

  return (
    <div className="productRateInput">
      <div className="productRateInputLabel">Đánh giá của bạn</div>
      <div className="productRateInputStars" role="radiogroup" aria-label="Chọn số sao đánh giá">
        {[1, 2, 3, 4, 5].map((star) => {
          const active = (hover || current) >= star
          return (
            <button
              key={star}
              type="button"
              className={`productRateStar${active ? ' productRateStar--active' : ''}`}
              disabled={disabled || loading}
              aria-label={`${star} sao`}
              onMouseEnter={() => setHover(star)}
              onMouseLeave={() => setHover(0)}
              onFocus={() => setHover(star)}
              onBlur={() => setHover(0)}
              onClick={() => onRate?.(star)}
            >
              {active ? '★' : '☆'}
            </button>
          )
        })}
      </div>
      {current > 0 ? (
        <div className="mutedSmall">Bạn đã chấm {current}/5 — bấm lại để đổi đánh giá.</div>
      ) : (
        <div className="mutedSmall">Chưa đánh giá — chọn số sao để gửi.</div>
      )}
    </div>
  )
}
