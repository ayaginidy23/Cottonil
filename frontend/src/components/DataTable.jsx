// =============================================================================
// DataTable.jsx - Sortable table (used by "table" charts and the table view
//                 of every chart, so no chart depends on colour alone)
//                 + "CSV" button: download exactly the rows shown, in the
//                 current sort order (opens in Excel, Arabic included)
// =============================================================================
import { useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import { fmt, fmtAxisLabel } from '../lib/format.js'

// Quote a value for CSV: wrap in "..." and double any inner quotes
const csvCell = (v) => {
  if (v === null || v === undefined) return ''
  const s = String(v)
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function downloadCsv(rows, columns, filename) {
  const lines = [
    columns.map((c) => csvCell(c.label)).join(','),
    ...rows.map((r) => columns.map((c) => csvCell(r[c.key])).join(',')),   // raw numbers, not formatted
  ]
  // "\uFEFF" (BOM) tells Excel the file is UTF-8, otherwise Arabic shows as garbage
  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${filename}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export default function DataTable({ rows, columns, filename = 'cottonil_export' }) {
  const [sort, setSort] = useState({ key: null, dir: 'desc' })

  const sorted = useMemo(() => {
    if (!sort.key) return rows
    const copy = [...rows]
    copy.sort((a, b) => {
      const x = a[sort.key]
      const y = b[sort.key]
      const nx = Number(x)
      const ny = Number(y)
      const cmp = !Number.isNaN(nx) && !Number.isNaN(ny) ? nx - ny : String(x).localeCompare(String(y))
      return sort.dir === 'asc' ? cmp : -cmp
    })
    return copy
  }, [rows, sort])

  const clickHeader = (key) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }))

  const safeName = String(filename).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'export'

  return (
    <div className="table-wrap">
      <div className="table-tools">
        <button type="button" className="chip" onClick={() => downloadCsv(sorted, columns, safeName)}
          disabled={!rows?.length} title="Download these rows as CSV (opens in Excel)">
          <Download size={12} /> CSV
        </button>
      </div>
      <table className="table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} onClick={() => clickHeader(c.key)} className={c.format ? 'num' : ''}>
                {c.label}
                {sort.key === c.key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} className={c.format ? 'num' : ''} dir="auto">
                  {c.format ? fmt(r[c.key], c.format, { compact: false }) : fmtAxisLabel(r[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}