// =============================================================================
// Layout.jsx - Page frame: sidebar (app menu) + filter bar + language switch + page
// =============================================================================
import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Languages, Menu } from 'lucide-react'

import Sidebar from './Sidebar.jsx'
import FilterBar from './FilterBar.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'
import { useLang } from '../lib/i18n.jsx'

// pages where the global filters (dates, branches, channels) mean nothing
const NO_FILTERS = ['/chat', '/ai']

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  const { lang, setLang, t } = useLang()
  const noFilters = NO_FILTERS.some((p) => pathname.startsWith(p))
  return (
    <div className={`layout ${menuOpen ? 'menu-open' : ''}`}>
      <Sidebar onNavigate={() => setMenuOpen(false)} />
      <div className="main">
        <header className="topbar no-print">
          <button className="icon-btn menu-btn" onClick={() => setMenuOpen((o) => !o)} aria-label="Menu">
            <Menu size={20} />
          </button>
          {noFilters ? <div className="filterbar muted">{t('chatFilters')}</div> : <FilterBar />}
          <button className="lang-toggle" onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}
            title="English / العربية" aria-label="Switch language">
            <Languages size={16} />
            <span>{t('language')}</span>
          </button>
        </header>
        <main className="content">
          <ErrorBoundary resetKey={pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      {menuOpen && <div className="backdrop" onClick={() => setMenuOpen(false)} />}
    </div>
  )
}
