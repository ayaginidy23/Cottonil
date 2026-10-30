// =============================================================================
// FilterBar.jsx - The one row of global filters above every app
//   period presets + custom dates | branch multi-select | channel chips | reset
// =============================================================================
import { useEffect, useRef, useState } from 'react'
import { Calendar, ChevronDown, RotateCcw, Store } from 'lucide-react'
import { useFilters } from '../lib/filters.jsx'

function BranchSelect({ branches, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef(null)

  // close the dropdown when clicking outside of it
  useEffect(() => {
    const close = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const q = search.trim().toLowerCase()
  const shown = branches.filter(
    (b) =>
      !q ||
      b.branch_id.toLowerCase().includes(q) ||
      (b.branch_display_name || '').includes(search.trim()) ||
      (b.governorate_ar || '').includes(search.trim()),
  )
  const toggle = (id) =>
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])

  return (
    <div className="dropdown" ref={ref}>
      <button className="control" onClick={() => setOpen((o) => !o)}>
        <Store size={16} />
        <span>{selected.length ? `${selected.length} branches` : 'All branches'}</span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <div className="dropdown-panel">
          <input
            className="input"
            placeholder="Search id, name or governorate"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
          <div className="dropdown-actions">
            <button className="link-btn" onClick={() => onChange([])}>Clear</button>
            <span className="muted">{selected.length} selected</span>
          </div>
          <div className="dropdown-list">
            {shown.map((b) => (
              <label key={b.branch_id} className="check-row">
                <input type="checkbox" checked={selected.includes(b.branch_id)} onChange={() => toggle(b.branch_id)} />
                <span className="mono">{b.branch_id}</span>
                <span className="ar" dir="auto">{b.branch_display_name}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function FilterBar() {
  const { options, filters, presets, update, reset, error } = useFilters()
  if (error) return <div className="filterbar error-text">Filters unavailable: {error}</div>
  if (!options) return <div className="filterbar muted">Loading filters…</div>

  const activePreset = presets.find((p) => p.from === filters.dateFrom && p.to === filters.dateTo)
  const toggleChannel = (c) =>
    update({
      channels: filters.channels.includes(c)
        ? filters.channels.filter((x) => x !== c)
        : [...filters.channels, c],
    })

  return (
    <div className="filterbar">
      <div className="segmented">
        {presets.map((p) => (
          <button
            key={p.id}
            className={activePreset?.id === p.id ? 'active' : ''}
            onClick={() => update({ dateFrom: p.from, dateTo: p.to })}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="control date-range">
        <Calendar size={16} />
        <input
          type="date"
          value={filters.dateFrom || ''}
          min={options.dates.data_from}
          max={filters.dateTo || options.dates.data_to}
          onChange={(e) => update({ dateFrom: e.target.value })}
        />
        <span className="muted">→</span>
        <input
          type="date"
          value={filters.dateTo || ''}
          min={filters.dateFrom || options.dates.data_from}
          max={options.dates.data_to}
          onChange={(e) => update({ dateTo: e.target.value })}
        />
      </div>

      <BranchSelect branches={options.branches} selected={filters.branches} onChange={(b) => update({ branches: b })} />

      <div className="chips">
        {options.channels.map((c) => (
          <button
            key={c}
            className={`chip ${filters.channels.includes(c) ? 'active' : ''}`}
            onClick={() => toggleChannel(c)}
          >
            {c}
          </button>
        ))}
      </div>

      <button className="icon-btn" onClick={reset} title="Reset filters" aria-label="Reset filters">
        <RotateCcw size={16} />
      </button>
    </div>
  )
}
