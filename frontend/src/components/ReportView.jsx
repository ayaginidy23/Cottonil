// =============================================================================
// ReportView.jsx - Draws a Report Agent report
//   lang = 'en' | 'ar'  -> one language (screen)
//   lang = 'both'       -> English and Arabic together (the PDF)
// Chart numbers come from the saved query results, never from the model's text.
// =============================================================================
import ChartCard from './ChartCard.jsx'
import DataTable from './DataTable.jsx'
import { autoChart, guessFormat } from '../lib/autochart.js'

function Text({ en, ar, lang, as: Tag = 'p', className }) {
  if (lang === 'both') {
    return (
      <>
        {en && <Tag className={className}>{en}</Tag>}
        {ar && <Tag className={className} dir="rtl" lang="ar">{ar}</Tag>}
      </>
    )
  }
  const v = lang === 'ar' ? ar || en : en || ar
  return v ? <Tag className={className} dir={lang === 'ar' ? 'rtl' : 'ltr'}>{v}</Tag> : null
}

function List({ en = [], ar = [], lang }) {
  const show = (items, dir) => items.length > 0 && (
    <ul dir={dir}>{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
  )
  if (lang === 'both') return <>{show(en, 'ltr')}{show(ar, 'rtl')}</>
  return show(lang === 'ar' && ar.length ? ar : en, lang === 'ar' ? 'rtl' : 'ltr')
}

export default function ReportView({ report, lang = 'en' }) {
  return (
    <div className="report">
      <Text en={report.title_en} ar={report.title_ar} lang={lang} as="h1" className="report-title" />
      <div className="report-summary card">
        <Text en={report.summary_en} ar={report.summary_ar} lang={lang} />
      </div>
      {report.sections.map((s, i) => {
        const chart = s.rows?.length ? autoChart(s.columns, s.rows, s.chart) : null
        return (
          <section key={i} className="report-section">
            <Text en={`${i + 1}. ${s.heading_en}`} ar={`${i + 1}. ${s.heading_ar}`} lang={lang} as="h2" />
            <Text en={s.text_en} ar={s.text_ar} lang={lang} />
            {s.images?.length > 0 && (
              <div className="report-images">
                {s.images.map((p) => (
                  <figure key={p.product_id}>
                    <img src={p.image_url} alt={p.name} referrerPolicy="no-referrer" />
                    <figcaption dir="auto">{p.name}</figcaption>
                  </figure>
                ))}
              </div>
            )}
            {chart && s.chart !== 'table' ? (
              <div className="report-chart"><ChartCard chart={{ ...chart, title: lang === 'ar' ? s.heading_ar : s.heading_en }} /></div>
            ) : s.rows?.length ? (
              <DataTable rows={s.rows} filename={s.heading_en} columns={s.columns.map((c, j) => ({
                key: c, label: c,
                format: j > 0 && s.rows.every((r) => r[c] === null || typeof r[c] === 'number') ? guessFormat(c, s.rows) : undefined,
              }))} />
            ) : null}
          </section>
        )
      })}
      {(report.recommendations_en?.length > 0 || report.recommendations_ar?.length > 0) && (
        <section className="report-section report-recs">
          <Text en="Recommendations" ar="التوصيات" lang={lang} as="h2" />
          <List en={report.recommendations_en} ar={report.recommendations_ar} lang={lang} />
        </section>
      )}
      <Text en={report.notes_en} ar={report.notes_ar} lang={lang} className="muted small" />
    </div>
  )
}
