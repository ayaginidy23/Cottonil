// =============================================================================
// QuoteCard.jsx - Summary of a B2B price quote in the chat + link to its PDF page
// =============================================================================
import { FileDown } from 'lucide-react'
import { fmt } from '../lib/format.js'

export default function QuoteCard({ quote }) {
  const egp = (v) => fmt(v, 'egp', { compact: false })
  return (
    <div className="quote-card">
      <div className="quote-top">
        <strong>Price quote · عرض سعر {quote.quote_id}</strong>
        <span className="muted small">valid until · صالح لحد {quote.valid_until}</span>
      </div>
      <div className="quote-row"><span>{quote.total_units} units · قطعة</span><span>{egp(quote.subtotal)}</span></div>
      {quote.discount > 0 && (
        <div className="quote-row good-text">
          <span>Volume discount · خصم الكمية {(quote.discount_pct * 100).toFixed(0)}%</span>
          <span>− {egp(quote.discount)}</span>
        </div>
      )}
      <div className="quote-row quote-total"><span>Total · الإجمالي</span><span>{egp(quote.total)}</span></div>
      {quote.next_tier && (
        <div className="muted small">
          +{quote.next_tier.units_missing} units → {(quote.next_tier.discount_pct * 100).toFixed(0)}% discount ·
          زوّد {quote.next_tier.units_missing} قطعة وخد خصم {(quote.next_tier.discount_pct * 100).toFixed(0)}%
        </div>
      )}
      <a className="action-btn primary quote-btn" href={`/print/quote/${quote.quote_id}`} target="_blank" rel="noreferrer">
        <FileDown size={15} /> Download PDF · تحميل PDF
      </a>
    </div>
  )
}
