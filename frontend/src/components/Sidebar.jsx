// =============================================================================
// Sidebar.jsx - App menu built from GET /api/apps, grouped by "group"
//   + the AI assistants and AI tools at the top (fixed pages)
// =============================================================================
import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { icons } from 'lucide-react'
import { api } from '../lib/api.js'
import { useLang } from '../lib/i18n.jsx'

// "layout-dashboard" (name in the YAML) -> icons.LayoutDashboard
function Icon({ name, size = 18 }) {
  const pascal = (name || '').split('-').map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join('')
  const Cmp = icons[pascal] || icons.ChartColumn || icons.BarChart3
  return Cmp ? <Cmp size={size} /> : null
}

const FIXED = [
  { group: 'aiAssistants', links: [
    { to: '/chat/shop', icon: 'message-circle', label: 'shopAssistant' },
    { to: '/chat/analyst', icon: 'sparkles', label: 'analyst' },
  ] },
  { group: 'aiTools', links: [
    { to: '/ai/insights', icon: 'radar', label: 'insights' },
    { to: '/ai/reports', icon: 'file-text', label: 'reports' },
    { to: '/ai/offers', icon: 'badge-percent', label: 'offers' },
    { to: '/products', icon: 'shirt', label: 'productsGallery' },
    { to: '/simulator', icon: 'sliders-horizontal', label: 'simulator' },
    { to: '/ai/security', icon: 'shield-check', label: 'security' },
  ] },
]

export default function Sidebar({ onNavigate }) {
  const [apps, setApps] = useState([])
  const [error, setError] = useState(null)
  const { t, tl } = useLang()

  useEffect(() => {
    api.apps().then(setApps).catch((e) => setError(e.message))
  }, [])

  // keep the order coming from the API, group consecutive apps by "group"
  const groups = []
  apps.forEach((a) => {
    let g = groups.find((x) => x.name === a.group)
    if (!g) groups.push((g = { name: a.group, apps: [] }))
    g.apps.push(a)
  })
  const linkClass = ({ isActive }) => `nav-link ${isActive ? 'active' : ''}`

  return (
    <aside className="sidebar no-print">
      <div className="brand">
        <div>
          {/* logo file: frontend/public/cottonil-logo-white.png (served at /cottonil-logo-white.png) */}
          <img className="brand-logo" src="/cottonil-logo-white.png" alt="Cottonil" />
        </div>
      </div>
      <nav className="nav">
        {error && <div className="nav-error">{t('apiDown')}: {error}</div>}
        {FIXED.map((g) => (
          <div key={g.group} className="nav-group">
            <div className="nav-group-title">{t(g.group)}</div>
            {g.links.map((l) => (
              <NavLink key={l.to} to={l.to} onClick={onNavigate} className={linkClass}>
                <Icon name={l.icon} />
                <span>{t(l.label)}</span>
              </NavLink>
            ))}
          </div>
        ))}
        {groups.map((g) => (
          <div key={g.name} className="nav-group">
            <div className="nav-group-title">{tl(g.name)}</div>
            {g.apps.map((a) => (
              <NavLink key={a.id} to={`/apps/${a.id}`} onClick={onNavigate} className={linkClass}
                title={tl(a.description)}>
                <Icon name={a.icon} />
                <span>{tl(a.title)}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  )
}
