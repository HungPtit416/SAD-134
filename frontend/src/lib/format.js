export function money(value, currency = 'USD') {
  if (value == null) return '-'
  const num = Number(value)
  if (Number.isNaN(num)) return `${value} ${currency}`.trim()
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: currency || 'VND',
    maximumFractionDigits: 0,
  }).format(num)
}

