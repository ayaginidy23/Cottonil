// =============================================================================
// ProductsPage.jsx - Product Explorer: every catalog product with its photo
// -----------------------------------------------------------------------------
// A visual catalog for management: photo, price, and the sales numbers of the
// selected period (global filters). Search, filter by category, sort; click a
// product to open its own page.
// =============================================================================
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ImageOff, Search } from 'lucide-react'
import { api } from '../lib/api.js'
import { useFilters } from '../lib/filters.jsx'
import { fmt } from '../lib/format.js'
import { useLang } from '../lib/i18n.jsx'

const SORTS = {
  net_sales: ['Net sales', 'صافي المبيعات'],
  units: ['Units', 'القطع'],
  margin_pct: ['Margin %', 'نسبة الهامش'],
  return_rate: ['Return rate', 'نسبة المرتجع'],
  min_price: ['Price', 'السعر'],
}

export default function ProductsPage() {
  const { filters, ready } = useFilters()
  const { lang, tl, t } = useLang()
  const ar = lang === 'ar'
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('')
  const [sort, setSort] = useState('net_sales')

  useEffect(() => {
    if (!ready) return
    api.products(filters).then(setRows).catch((e) => setError(e.message))
  }, [filters, ready])

  const categories = useMemo(() => [...new Set((rows || []).map((r) => r.category))].sort(), [rows])
  const shown = useMemo(() => (rows || [])
    .filter((r) => (!cat || r.category === cat)
      && (!q || r.name.includes(q.trim()) || r.product_id.toLowerCase().includes(q.trim().toLowerCase())))
    .sort((a, b) => (Number(b[sort]) || 0) - (Number(a[sort]) || 0)), [rows, q, cat, sort])

  return (
    <div className="app-page">
      <div className="page-head">
        <div>
          <div className="eyebrow">{ar ? 'المنتجات' : 'Products'}</div>
          <h1>{t('productsGallery')}</h1>
          <p className="muted">
            {ar ? 'كل منتجات الكتالوج بالصور والأسعار وأرقام البيع في الفترة المختارة. اضغط على أي منتج تشوف صفحته.'
              : 'Every catalog product with its photo, price and the sales of the selected period. Click a product to open its page.'}
          </p>
          <p className="demo-note">
            {ar ? 'الصور والأسعار من موقع كوتونيل الرسمي العام. ده مشروع تجريبي ومش متجر رسمي.'
              : 'Photos and prices come from the public cottonilegypt.com site. This is a demo project, not an official store.'}
          </p>
        </div>
      </div>

      <div className="gallery-tools">
        <div className="control search-box">
          <Search size={16} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={ar ? 'اسم المنتج أو الكود' : 'Product name or id'} dir="auto" />
        </div>
        <select className="input select" value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">{t('allCategories')}</option>
          {categories.map((c) => <option key={c} value={c}>{tl(c)}</option>)}
        </select>
        <select className="input select" value={sort} onChange={(e) => setSort(e.target.value)}>
          {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{ar ? `ترتيب: ${v[1]}` : `Sort: ${v[0]}`}</option>)}
        </select>
        <span className="muted small">{shown.length} / {rows?.length || 0}</span>
      </div>

      {error && <div className="error-box"><strong>Error</strong><code>{error}</code></div>}
      {!rows && !error && <div className="gallery">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="card skeleton tall" />)}</div>}

      <div className="gallery">
        {shown.map((p) => (
          <Link key={p.product_id} to={`/products/${p.product_id}`} className="card gallery-card">
            <div className="gallery-img">
              {p.image_url ? <img src={p.image_url} alt={p.name} loading="lazy" referrerPolicy="no-referrer" />
                : <ImageOff size={28} />}
            </div>
            <div className="gallery-body">
              <div className="product-name" dir="auto">{p.name}</div>
              <div className="muted small">{p.product_id} · {tl(p.category)}</div>
              <div className="product-price">
                {p.min_price === p.max_price ? fmt(p.min_price, 'egp', { compact: false })
                  : `${fmt(p.min_price, 'egp', { compact: false })} – ${fmt(p.max_price, 'egp', { compact: false })}`}
              </div>
              <div className="gallery-stats">
                <span>{fmt(p.net_sales, 'egp')}</span>
                <span>{fmt(p.units, 'number')} {ar ? 'قطعة' : 'units'}</span>
                <span>{ar ? 'هامش' : 'margin'} {fmt(p.margin_pct, 'pct')}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
