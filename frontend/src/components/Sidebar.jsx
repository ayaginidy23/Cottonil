// =============================================================================
// Sidebar.jsx - App menu built from GET /api/apps, grouped by "group"
// =============================================================================
import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { icons } from 'lucide-react'
import { api } from '../lib/api.js'

// "layout-dashboard" (name in the YAML) -> icons.LayoutDashboard
function Icon({ name, size = 18 }) {
  const pascal = (name || '').split('-').map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join('')
  const Cmp = icons[pascal] || icons.ChartColumn || icons.BarChart3
  return Cmp ? <Cmp size={size} /> : null
}

export default function Sidebar({ onNavigate }) {
  const [apps, setApps] = useState([])
  const [error, setError] = useState(null)

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

  return (
    <aside className="sidebar">
      <div className="brand">
        <div>
          {/* logo file: frontend/public/cottonil-logo-white.png (served at /cottonil-logo-white.png) */}
          <img className="brand-logo" src="/cottonil-logo-white.png" alt="Cottonil" />
          <div className="brand-sub">Data &amp; AI Platform</div>
        </div>
      </div>
      <nav className="nav">
        {error && <div className="nav-error">API not reachable: {error}</div>}
        <div className="nav-group">
          <div className="nav-group-title">AI Assistants</div>
          <NavLink to="/chat/shop" onClick={onNavigate}
            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Icon name="message-circle" />
            <span>Shopping Assistant</span>
          </NavLink>
          <NavLink to="/chat/analyst" onClick={onNavigate}
            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Icon name="sparkles" />
            <span>Business Analyst</span>
          </NavLink>
        </div>
        {groups.map((g) => (
          <div key={g.name} className="nav-group">
            <div className="nav-group-title">{g.name}</div>
            {g.apps.map((a) => (
              <NavLink
                key={a.id}
                to={`/apps/${a.id}`}
                onClick={onNavigate}
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                title={a.description}
              >
                <Icon name={a.icon} />
                <span>{a.title}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  )
}