// =============================================================================
// format.js - How numbers are shown (driven by "format" in the app YAML)
//   egp | usd | number | pct | days | decimal | text
// compact = short form for KPI cards and chart axes (EGP 1.25M)
// =============================================================================

const full0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const full2 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

// short = fewer decimals, for chart axes
function compactNumber(v, short = false) {
  const a = Math.abs(v)
  if (a >= 1e9) return `${(v / 1e9).toFixed(short ? 1 : 2)}B`
  if (a >= 1e6) return `${(v / 1e6).toFixed(short ? 1 : 2)}M`
  if (a >= 1e4) return `${(v / 1e3).toFixed(short ? 0 : 1)}K`
  return full0.format(v)
}

export function fmt(value, format = 'number', { compact = true, short = false } = {}) {
  if (value === null || value === undefined || value === '') return '—'
  const v = Number(value)
  if (Number.isNaN(v)) return String(value)          // text values (names, categories)
  switch (format) {
    case 'egp':
      return `EGP ${compact ? compactNumber(v, short) : full0.format(v)}`
    case 'usd':
      return `$${compact ? compactNumber(v, short) : full0.format(v)}`
    case 'pct':
      return `${(v * 100).toFixed(1)}%`
    case 'days':
      return `${v.toFixed(1)} days`
    case 'decimal':
      return full2.format(v)
    case 'number':
    default:
      return compact ? compactNumber(v, short) : full0.format(v)
  }
}

// "2025-03-01" -> "Mar 25" for month axes; anything else unchanged
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function fmtAxisLabel(v) {
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v)) {
    return `${MONTHS[Number(v.slice(5, 7)) - 1]} ${v.slice(2, 4)}`
  }
  return v
}
