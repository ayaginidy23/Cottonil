// =============================================================================
// CompareTable.jsx - Products side by side (tool compare_products)
// =============================================================================
import { fmt } from '../lib/format.js'

const price = (p) => (p.min_price === p.max_price
  ? fmt(p.min_price, 'egp', { compact: false })
  : `${fmt(p.min_price, 'egp', { compact: false })} – ${fmt(p.max_price, 'egp', { compact: false })}`)

const ROWS = [
  ['Category · الفئة', (p) => p.category],
  ['For · لمين', (p) => p.audience],
  ['Price · السعر', price],
  ['Sizes · المقاسات', (p) => p.sizes],
  ['Colours · الألوان', (p) => p.colors],
]

export default function CompareTable({ products }) {
  return (
    <div className="compare-wrap">
      <table className="compare-table">
        <thead>
          <tr>
            <th />
            {products.map((p) => (
              <th key={p.product_id}>
                {p.image_url && <img src={p.image_url} alt="" referrerPolicy="no-referrer" />}
                <a href={p.url || '#'} target="_blank" rel="noreferrer" dir="auto">{p.name}</a>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([label, get]) => (
            <tr key={label}>
              <td className="compare-label">{label}</td>
              {products.map((p) => <td key={p.product_id} dir="auto">{get(p) || '—'}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
