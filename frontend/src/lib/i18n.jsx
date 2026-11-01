// =============================================================================
// i18n.jsx - English / Arabic switch for the whole UI
// -----------------------------------------------------------------------------
//   t('key')        -> a UI text (buttons, menus, messages) in the chosen language
//   tl('Net sales') -> a label coming from the app YAML files or the data
//                      (titles, KPI names, columns, channels, segments...);
//                      Arabic comes from labels_ar.json, unknown labels stay English
// Arabic also switches the page direction to right-to-left (dir="rtl").
// Numbers stay in Latin digits (EGP 12.4M) in both languages, as in Egyptian business use.
// The choice is remembered in this browser (localStorage, if allowed).
// =============================================================================
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import LABELS_AR from './labels_ar.json'
import { setFormatLang } from './format.js'

// Values that appear inside the data (not in the YAML files)
const VALUES_AR = {
  Champions: 'الأبطال', Loyal: 'الأوفياء', 'New / Promising': 'جداد / واعدين',
  'Needs attention': 'محتاجين اهتمام', 'At risk': 'معرضين نخسرهم', Hibernating: 'نايمين',
  Retail: 'قطاعي', 'B2B reseller': 'تاجر جملة (B2B)',
  'No branch - candidate': 'مفيش فرع - مرشحة', 'Under-served': 'الخدمة أقل من الطلب', Covered: 'متغطية',
  Replenish: 'محتاج تزويد', Overstocked: 'زيادة مخزون', OK: 'تمام',
  Monday: 'الإثنين', Tuesday: 'الثلاثاء', Wednesday: 'الأربعاء', Thursday: 'الخميس',
  Friday: 'الجمعة', Saturday: 'السبت', Sunday: 'الأحد',
  Ramadan: 'رمضان', Eid: 'العيد', 'Back to school': 'المدارس', 'Black Friday': 'البلاك فرايداي',
  'Regular day': 'يوم عادي', Adult: 'كبار', Kids: 'أطفال', Free: 'مقاس واحد', Other: 'أخرى',
  Men: 'رجالي', Women: 'حريمي', Unisex: 'للجنسين',
  'Last 12 months': 'آخر 12 شهر', 'Year to date': 'من أول السنة', 'All time': 'كل الفترة',
  Delivered: 'اتسلمت', 'In transit': 'في الطريق', Cancelled: 'اتلغت', Completed: 'اكتملت',
}

const UI = {
  en: {
    platform: 'Data & AI Platform', aiAssistants: 'AI Assistants', aiTools: 'AI Tools',
    shopAssistant: 'Shopping Assistant', analyst: 'Business Analyst', insights: 'Insight Scout',
    reports: 'Report Agent', security: 'Security Log', offers: 'Offers', productsGallery: 'Product Explorer',
    simulator: 'What-if Simulator', apiDown: 'API not reachable', language: 'العربية',
    chatFilters: "AI assistant - global filters don't apply here",
    explain: 'Explain this page', explaining: 'Reading the page…', downloadPdf: 'Download PDF',
    aiSummary: 'AI summary', toWatch: 'To watch', close: 'Close', readAloud: 'Read aloud',
    english: 'English', arabic: 'العربية', generatedOn: 'Generated on', filters: 'Filters',
    period: 'Period', allData: 'All data', allBranches: 'All branches', allChannels: 'All channels',
    loadError: 'Could not load this app', queryError: 'Query error', noData: 'No data for the selected filters',
    showChart: 'Show chart', showTable: 'Show table', vsPrev: 'vs previous period',
    retry: 'Try again', loading: 'Loading…', search: 'Search', allCategories: 'All categories',
    printNote: 'Tip: in the print window choose "Save as PDF".',
  },
  ar: {
    platform: 'منصة البيانات والذكاء الاصطناعي', aiAssistants: 'المساعدين الأذكياء', aiTools: 'أدوات الذكاء الاصطناعي',
    shopAssistant: 'مساعد التسوق', analyst: 'المحلل الذكي', insights: 'مستكشف الملاحظات',
    reports: 'وكيل التقارير', security: 'سجل الأمان', offers: 'العروض', productsGallery: 'مستكشف المنتجات',
    simulator: 'محاكي ماذا لو', apiDown: 'السيرفر مش متاح', language: 'English',
    chatFilters: 'المساعد الذكي - الفلاتر العامة مش بتأثر هنا',
    explain: 'اشرحلي الصفحة', explaining: 'بقرا الصفحة…', downloadPdf: 'تحميل PDF',
    aiSummary: 'ملخص الذكاء الاصطناعي', toWatch: 'خلي بالك من', close: 'قفل', readAloud: 'اقرأ بصوت عالي',
    english: 'English', arabic: 'العربية', generatedOn: 'اتعمل يوم', filters: 'الفلاتر',
    period: 'الفترة', allData: 'كل الفترة', allBranches: 'كل الفروع', allChannels: 'كل القنوات',
    loadError: 'مقدرناش نحمّل الصفحة', queryError: 'خطأ في الاستعلام', noData: 'مفيش بيانات للفلاتر دي',
    showChart: 'اعرض الرسم', showTable: 'اعرض الجدول', vsPrev: 'مقارنة بالفترة اللي قبلها',
    retry: 'جرب تاني', loading: 'بيحمّل…', search: 'بحث', allCategories: 'كل الفئات',
    printNote: 'في شاشة الطباعة اختار "Save as PDF".',
  },
}

const LangContext = createContext({ lang: 'en', setLang: () => {}, t: (k) => k, tl: (s) => s })

function initialLang() {
  try {
    return localStorage.getItem('cottonil_lang') === 'ar' ? 'ar' : 'en'
  } catch {
    return 'en'
  }
}

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(initialLang)

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
  }, [lang])

  const value = useMemo(() => {
    setFormatLang(lang)                       // month names on chart axes
    const setLang = (l) => {
      setLangState(l)
      try { localStorage.setItem('cottonil_lang', l) } catch { /* storage blocked: keep in memory */ }
    }
    const t = (key) => UI[lang][key] ?? UI.en[key] ?? key
    const tl = (text) => {
      if (lang !== 'ar' || typeof text !== 'string') return text
      return LABELS_AR[text] ?? VALUES_AR[text] ?? text
    }
    return { lang, setLang, t, tl }
  }, [lang])

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>
}

export const useLang = () => useContext(LangContext)

// Arabic labels for both languages at once (used by the bilingual PDF pages)
export const arabicLabel = (text) => LABELS_AR[text] ?? VALUES_AR[text] ?? text

// A YAML label in the screen language; in the PDF it is printed in BOTH languages
export function Bi({ text }) {
  const { tl } = useLang()
  if (!text) return null
  const ar = arabicLabel(text)
  return (
    <>
      <span className="screen-only">{tl(text)}</span>
      <span className="print-only">
        {text}
        {ar !== text && <span className="bi-ar" dir="rtl" lang="ar">{ar}</span>}
      </span>
    </>
  )
}
