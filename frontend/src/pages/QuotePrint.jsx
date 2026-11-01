// =============================================================================
// QuotePrint.jsx - B2B price quote as a printable bilingual document (EN + AR)
//   /print/quote/Q-20261031-AB12  -> "Save as PDF" button = browser print-to-PDF
// The browser renders the Arabic text, so it is always joined and right-to-left.
// =============================================================================
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Printer } from 'lucide-react'
import { api } from '../lib/api.js'
import { fmt } from '../lib/format.js'

const egp = (v) => fmt(v, 'egp', { compact: false })

function Pair({ en, ar }) {
  return (
    <div className="pair">
      <span>{en}</span>
      <span dir="rtl" lang="ar">{ar}</span>
    </div>
  )
}

export default function QuotePrint() {
  const { quoteId } = useParams()
  const [quote, setQuote] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.quote(quoteId).then(setQuote).catch((e) => setError(e.message))
  }, [quoteId])

  if (error) return <div className="doc"><div className="error-box">{error}</div></div>
  if (!quote) return <div className="doc muted">Loading… · جاري التحميل</div>

  return (
    <div className="doc">
      <div className="doc-toolbar no-print">
        <button className="action-btn primary" onClick={() => window.print()}>
          <Printer size={16} /> Save as PDF · حفظ PDF
        </button>
        <span className="muted small">In the print window choose "Save as PDF" · اختار Save as PDF</span>
      </div>

      <header className="doc-header">
        <img src="/cottonil-logo-blue.png" alt="Cottonil" className="doc-logo"
          onError={(e) => { e.currentTarget.style.display = 'none' }} />
        <div className="doc-title">
          <Pair en="Wholesale price quote" ar="عرض سعر جملة" />
        </div>
      </header>

      <section className="doc-meta">
        <Pair en={`Quote no.: ${quote.quote_id}`} ar={`رقم العرض: ${quote.quote_id}`} />
        <Pair en={`Date: ${quote.date}`} ar={`التاريخ: ${quote.date}`} />
        <Pair en={`Valid until: ${quote.valid_until}`} ar={`صالح حتى: ${quote.valid_until}`} />
        {quote.company_name && <Pair en={`For: ${quote.company_name}`} ar={`مقدم إلى: ${quote.company_name}`} />}
        {quote.customer && (
          <Pair en={`Customer: ${quote.customer.customer_key} (${quote.customer.customer_segment})`}
            ar={`العميل: ${quote.customer.customer_key}`} />
        )}
      </section>

      <table className="doc-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Product · المنتج</th>
            <th>Size · المقاس</th>
            <th className="num">Qty · الكمية</th>
            <th className="num">Unit price · سعر القطعة</th>
            <th className="num">Total · الإجمالي</th>
          </tr>
        </thead>
        <tbody>
          {quote.lines.map((l, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td dir="auto">{l.name}<div className="muted small">{l.product_id} · {l.category}</div></td>
              <td>{l.size === 'assorted' ? 'Assorted · مقاسات مختلفة' : l.size}</td>
              <td className="num">{l.quantity}</td>
              <td className="num">{egp(l.unit_price)}</td>
              <td className="num">{egp(l.line_total)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className="doc-totals">
        <div className="doc-total-row"><Pair en="Subtotal" ar="الإجمالي قبل الخصم" /><span>{egp(quote.subtotal)}</span></div>
        <div className="doc-total-row">
          <Pair en={`Volume discount (${(quote.discount_pct * 100).toFixed(0)}% for ${quote.total_units} units)`}
            ar={`خصم الكمية (${(quote.discount_pct * 100).toFixed(0)}% على ${quote.total_units} قطعة)`} />
          <span>− {egp(quote.discount)}</span>
        </div>
        <div className="doc-total-row grand"><Pair en="Total to pay" ar="الإجمالي المطلوب" /><span>{egp(quote.total)}</span></div>
      </section>

      <section className="doc-notes">
        <h3><Pair en="Volume discount tiers" ar="شرائح خصم الكمية" /></h3>
        <ul>
          {quote.tiers.map((t) => (
            <li key={t.min_units}>
              <Pair en={`${t.min_units}+ units: ${(t.discount_pct * 100).toFixed(0)}% off`}
                ar={`${t.min_units} قطعة أو أكتر: خصم ${(t.discount_pct * 100).toFixed(0)}%`} />
            </li>
          ))}
        </ul>
        <Pair en="Payment: bank transfer (wholesale). Prices are list prices in EGP."
          ar="الدفع: تحويل بنكي (للجملة). الأسعار هي أسعار الكتالوج بالجنيه المصري." />
        <p className="muted small">
          {quote.note}
          <br />
          <span dir="rtl" lang="ar">شرائح خصم تجريبية للمشروع. الأسعار النهائية بيأكدها فريق الجملة في كوتونيل.</span>
        </p>
      </section>
    </div>
  )
}
