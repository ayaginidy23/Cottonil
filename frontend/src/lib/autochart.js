// =============================================================================
// autochart.js - Turn any SQL result (columns + rows) into a ChartCard spec
//   used by the Business Analyst chat and the Report Agent
// =============================================================================

// Guess how to show a value column from its name and values
export function guessFormat(col, rows) {
  const name = col.toLowerCase()
  const max = Math.max(...rows.map((r) => Math.abs(Number(r[col]) || 0)))
  if (/(pct|rate|share|ratio|margin_pct|growth)/.test(name) && max <= 1.5) return 'pct'
  if (/(egp|sales|revenue|profit|value|cost|amount|spend|refund|margin)/.test(name)) return 'egp'
  if (/usd/.test(name)) return 'usd'
  return 'number'
}

// Build a ChartCard spec from any result table (or null if it isn't chartable)
// Numbers saved as text in older chats ("10717782.0666") are turned back into numbers
const NUMERIC_TEXT = /^-?\d+(\.\d+)?$/
export function cleanRows(rows = []) {
  return rows.map((r) => Object.fromEntries(Object.entries(r).map(([k, v]) =>
    [k, typeof v === 'string' && NUMERIC_TEXT.test(v) ? Number(v) : v])))
}

export function autoChart(columns, rawRows, preferred) {
  const rows = cleanRows(rawRows)
  if (!rows?.length || rows.length < 2 || columns.length < 2) return null
  const isNum = (c) => rows.every((r) => r[c] === null || typeof r[c] === 'number')
  const numeric = columns.filter(isNum)
  const labels = columns.filter((c) => !isNum(c))
  if (!numeric.length) return null
  const x = labels[0] || columns[0]
  let values = numeric.filter((c) => c !== x)
  if (!values.length) return null

  // one axis only: keep extra series only if they have a similar scale to the first
  const maxOf = (c) => Math.max(...rows.map((r) => Math.abs(Number(r[c]) || 0))) || 1
  const base = maxOf(values[0])
  values = values.filter((c, i) => i === 0 || (maxOf(c) / base < 10 && maxOf(c) / base > 0.1)).slice(0, 3)

  const timeLike = rows.every((r) => /^\d{4}(-\d{2})?(-\d{2})?/.test(String(r[x])))
  let type = timeLike ? 'line' : rows.length > 12 ? 'hbar' : 'bar'
  if (['line', 'bar', 'hbar'].includes(preferred)) type = preferred     // the Report Agent's choice
  return {
    id: 'auto',
    title: 'Result',
    type: type === 'hbar' && values.length > 1 ? 'bar' : type,
    width: 'full',
    x,
    series: values.map((c) => ({ key: c, label: c })),
    format: guessFormat(values[0], rows),
    data: type === 'hbar' ? rows.slice(0, 25) : rows,
    table_columns: columns.map((c) => ({ key: c, label: c, format: isNum(c) && c !== x ? guessFormat(c, rows) : undefined })),
  }
}