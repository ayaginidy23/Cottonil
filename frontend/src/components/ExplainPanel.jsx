// =============================================================================
// ExplainPanel.jsx - Shows the AI summary of a page ("Explain this page")
//   EN / AR tabs on screen, read-aloud button; prints BOTH languages in the PDF.
// =============================================================================
import { useState } from 'react'
import { Sparkles, Volume2, X } from 'lucide-react'
import { speak, stopSpeaking, canSpeak } from '../lib/speech.js'
import { useLang } from '../lib/i18n.jsx'

function Summary({ part, lang, t }) {
  if (!part) return null
  return (
    <div className="explain-body" dir={lang === 'ar' ? 'rtl' : 'ltr'} lang={lang}>
      <p className="explain-headline">{part.headline}</p>
      <ul>{part.points.map((p, i) => <li key={i}>{p}</li>)}</ul>
      {part.watch?.length > 0 && (
        <>
          <div className="explain-watch-title">{lang === 'ar' ? 'خلي بالك من' : t('toWatch')}</div>
          <ul className="explain-watch">{part.watch.map((p, i) => <li key={i}>{p}</li>)}</ul>
        </>
      )}
    </div>
  )
}

const asText = (part) => part ? [part.headline, ...part.points, ...(part.watch || [])].join('. ') : ''

export default function ExplainPanel({ summary, loading, error, onClose }) {
  const { lang: uiLang, t } = useLang()
  const [lang, setLang] = useState(uiLang)
  if (!summary && !loading && !error) return null
  return (
    <section className="card explain-panel">
      <div className="explain-head">
        <Sparkles size={18} />
        <strong>{t('aiSummary')}</strong>
        <div className="segmented small-seg no-print">
          <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
          <button className={lang === 'ar' ? 'active' : ''} onClick={() => setLang('ar')}>عربي</button>
        </div>
        <span className="spacer" />
        {summary && canSpeak && (
          <button className="icon-btn no-print" title={t('readAloud')} onClick={() => speak(asText(summary[lang]))}>
            <Volume2 size={16} />
          </button>
        )}
        <button className="icon-btn no-print" title={t('close')} onClick={() => { stopSpeaking(); onClose() }}>
          <X size={16} />
        </button>
      </div>
      {loading && <div className="muted">{t('explaining')}</div>}
      {error && <div className="error-text small">{error}</div>}
      {summary && (
        <>
          <div className="screen-only"><Summary part={summary[lang]} lang={lang} t={t} /></div>
          {/* the PDF always has both languages */}
          <div className="print-only explain-print">
            <Summary part={summary.en} lang="en" t={t} />
            <Summary part={summary.ar} lang="ar" t={t} />
          </div>
        </>
      )}
    </section>
  )
}
