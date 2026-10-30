// =============================================================================
// Layout.jsx - Page frame: sidebar (app menu) + filter bar + the current page
// =============================================================================
import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'

import Sidebar from './Sidebar.jsx'
import FilterBar from './FilterBar.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  const onChat = pathname.startsWith('/chat')   // filters don't apply to chat pages
  return (
    <div className={`layout ${menuOpen ? 'menu-open' : ''}`}>
      <Sidebar onNavigate={() => setMenuOpen(false)} />
      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setMenuOpen((o) => !o)} aria-label="Menu">
            <Menu size={20} />
          </button>
          {onChat ? <div className="filterbar muted">AI assistant - global filters don't apply here</div> : <FilterBar />}
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