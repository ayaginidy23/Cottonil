// =============================================================================
// KpiCard.jsx - One headline number + % change vs the previous period
// -----------------------------------------------------------------------------
// "good" (from the YAML) decides the colour: for sales up is good (green),
// for returns or costs up is bad (red). Arrow + sign carry the meaning too,
// so it never depends on colour alone.
// KPIs that are already a % show the change in percentage points (pp).
// The hint (how the KPI is calculated) is its own line, never hiding the delta.
// =============================================================================
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { fmt } from '../lib/format.js'

export default function KpiCard({ kpi }) {
  const { label, value, format, hint, change_pct: change, change_unit: unit, good, error } = kpi

  let tone = 'neutral'
  let Arrow = Minus
  if (change !== null && change !== undefined && Math.abs(change) >= 0.0005) {
    const up = change > 0
    Arrow = up ? ArrowUpRight : ArrowDownRight
    tone = up === (good !== 'down') ? 'good' : 'bad'
  }

  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      {error ? (
        <div className="error-text small">Query error</div>
      ) : (
        <div className="kpi-value" title={fmt(value, format, { compact: false })}>
          {fmt(value, format)}
        </div>
      )}
      <div className="kpi-foot">
        {change !== null && change !== undefined && (
          <>
            <span className={`delta ${tone}`}>
              <Arrow size={14} />
              {change > 0 ? '+' : ''}
              {(change * 100).toFixed(1)}{unit === 'pp' ? ' pp' : '%'}
            </span>
            <span className="muted small">vs previous period</span>
          </>
        )}
        {hint && <span className="kpi-hint muted small" title={hint}>{hint}</span>}
      </div>
    </div>
  )
}