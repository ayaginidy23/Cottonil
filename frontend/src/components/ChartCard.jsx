// =============================================================================
// ChartCard.jsx - Draws ANY chart described in an app YAML
//   type: line | area | bar | hbar | donut | table | map (Egypt governorates)
//   x: column for the category / time axis
//   series: [{key, label}] columns to plot
//   format: how values are shown (egp, pct, number...)
//   note:   optional explanation shown under the title
// Every chart also has a "table view" toggle (accessibility + exact numbers).
// Titles, series names and category labels follow the language switch.
// =============================================================================
import { lazy, Suspense, useState } from 'react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { BarChart3, Table2 } from 'lucide-react'

import DataTable from './DataTable.jsx'
import { NEGATIVE, OTHER, SERIES, colorMap } from '../lib/colors.js'
import { fmt, fmtAxisLabel } from '../lib/format.js'
import { Bi, useLang } from '../lib/i18n.jsx'

// the map library is big, so it is only downloaded when a page has a map
const MapChart = lazy(() => import('./MapChart.jsx'))

const AXIS = { stroke: 'var(--axis)', fontSize: 12, tickLine: false }
const GRID = <CartesianGrid vertical={false} stroke="var(--grid)" />
// Bars must always start at zero, and axis ticks should be round numbers
// (0, 1M, 2M, 3M, 4M - not 41.4M or 317.7M). niceScale picks a round step
// (1, 2, 2.5 or 5 x 10^n) so the axis has about `count` ticks.
function niceScale(rows, keys, count = 5) {
  let min = 0
  let max = 0
  rows.forEach((r) => keys.forEach((k) => {
    const v = Number(r[k])
    if (Number.isFinite(v)) { min = Math.min(min, v); max = Math.max(max, v) }
  }))
  if (min === max) return { domain: [0, 1], ticks: undefined }
  const raw = (max - min) / (count - 1)
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => st >= raw)
  const lo = Math.floor(min / step) * step
  const hi = Math.ceil(max / step) * step
  const ticks = []
  for (let t = lo; t <= hi + step / 2; t += step) ticks.push(Number(t.toPrecision(12)))
  return { domain: [lo, hi], ticks }
}

const niceAxis = ({ domain, ticks }) => ({ domain, ticks, interval: 0 })

function tooltipProps(format, xfmt = fmtAxisLabel) {
  return {
    formatter: (v, name) => [fmt(v, format, { compact: false }), name],
    labelFormatter: xfmt,
    contentStyle: {
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      fontSize: 13,
    },
  }
}

// Donuts with many slices: keep the 7 biggest, fold the rest into "Other"
function foldOther(rows, x, key, keep = 7) {
  if (rows.length <= keep + 1) return rows
  const sorted = [...rows].sort((a, b) => Number(b[key]) - Number(a[key]))
  const top = sorted.slice(0, keep)
  const rest = sorted.slice(keep).reduce((s, r) => s + Number(r[key] || 0), 0)
  return [...top, { [x]: 'Other', [key]: rest }]
}

function Plot({ chart, xfmt }) {
  const { type, data, x, series = [], format } = chart
  const multi = series.length > 1
  const yTick = (v) => fmt(v, format, { short: true })

  if (type === 'line' || type === 'area') {
    const Chart = type === 'line' ? LineChart : AreaChart
    return (
      <ResponsiveContainer width="100%" height={300}>
        <Chart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
          {GRID}
          <XAxis dataKey={x} tickFormatter={xfmt} {...AXIS} minTickGap={24} />
          <YAxis tickFormatter={yTick} {...AXIS} width={86} />
          <Tooltip {...tooltipProps(format, xfmt)} />
          {multi && <Legend iconType="plainline" wrapperStyle={{ fontSize: 13 }} />}
          {series.map((s, i) =>
            type === 'line' ? (
              <Line key={s.key} dataKey={s.key} name={s.label} stroke={SERIES[i]} strokeWidth={2}
                dot={false} activeDot={{ r: 4 }} />
            ) : (
              <Area key={s.key} dataKey={s.key} name={s.label} stroke={SERIES[i]} strokeWidth={2}
                fill={SERIES[i]} fillOpacity={0.15} />
            ),
          )}
        </Chart>
      </ResponsiveContainer>
    )
  }

  if (type === 'bar') {
    const single = !multi
    // tilt the labels when they would collide (many bars or long names)
    const longest = Math.max(...data.map((r) => String(xfmt(r[x]) ?? '').length))
    const tilt = data.length > 8 || longest * data.length > 55
    return (
      <ResponsiveContainer width="100%" height={tilt ? 330 : 300}>
        <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }} barGap={2}>
          {GRID}
          <XAxis dataKey={x} tickFormatter={xfmt} {...AXIS} interval={0}
            angle={tilt ? -30 : 0} textAnchor={tilt ? 'end' : 'middle'}
            height={tilt ? 80 : 30} />
          <YAxis tickFormatter={yTick} {...AXIS} width={86} {...niceAxis(niceScale(data, series.map((se) => se.key)))} />
          <Tooltip {...tooltipProps(format, xfmt)} cursor={{ fill: 'var(--hover)' }} />
          {multi && <Legend wrapperStyle={{ fontSize: 13 }} />}
          <ReferenceLine y={0} stroke="var(--axis)" />
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.label} fill={SERIES[i]} radius={[4, 4, 0, 0]} maxBarSize={48}>
              {single && data.map((row, j) => (
                <Cell key={j} fill={Number(row[s.key]) < 0 ? NEGATIVE : SERIES[0]} />
              ))}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (type === 'hbar') {
    const s = series[0]
    const height = Math.max(220, data.length * 30 + 40)
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke="var(--grid)" />
          <XAxis type="number" tickFormatter={yTick} {...AXIS} {...niceAxis(niceScale(data, [s.key]))} />
          <YAxis type="category" dataKey={x} tickFormatter={xfmt} {...AXIS} width={150} interval={0} />
          <Tooltip {...tooltipProps(format, xfmt)} cursor={{ fill: 'var(--hover)' }} />
          <ReferenceLine x={0} stroke="var(--axis)" />
          <Bar dataKey={s.key} name={s.label} radius={[0, 4, 4, 0]} maxBarSize={20}>
            {data.map((row, j) => (
              <Cell key={j} fill={Number(row[s.key]) < 0 ? NEGATIVE : SERIES[0]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (type === 'donut') {
    const key = series[0]?.key || 'value'
    const rows = foldOther(data, x, key).map((r) => ({ ...r, [x]: xfmt(r[x]) }))
    const colors = colorMap(rows.map((r) => r[x]))
    const total = rows.reduce((s, r) => s + Number(r[key] || 0), 0)
    return (
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie data={rows} dataKey={key} nameKey={x} innerRadius="55%" outerRadius="80%"
            paddingAngle={1} stroke="var(--surface)" strokeWidth={2}>
            {rows.map((r) => (
              <Cell key={r[x]} fill={colors[String(r[x])] || OTHER} />
            ))}
          </Pie>
          <Tooltip {...tooltipProps(format, xfmt)}
            formatter={(v, n) => [`${fmt(v, format, { compact: false })} (${((v / total) * 100).toFixed(1)}%)`, n]} />
          <Legend layout="horizontal" verticalAlign="bottom" wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    )
  }

  if (type === 'map') {
    return (
      <Suspense fallback={<div className="empty">…</div>}>
        <MapChart chart={chart} />
      </Suspense>
    )
  }

  return null
}

export default function ChartCard({ chart }) {
  const [asTable, setAsTable] = useState(false)
  const { t, tl } = useLang()
  const { title, type, data = [], x, series = [], format, error, table_columns: tableColumns } = chart

  // columns for the table view of a normal chart
  const columns = (tableColumns || [
    { key: x, label: x },
    ...series.map((s) => ({ key: s.key, label: s.label, format: s.format || format || 'number' })),
  ]).map((c) => ({ ...c, label: tl(c.label) }))
  const showTable = type === 'table' || asTable
  const shown = { ...chart, series: series.map((s) => ({ ...s, label: tl(s.label) })) }
  const xfmt = (v) => tl(fmtAxisLabel(v))

  return (
    <div className={`card chart w-${chart.width || 'half'}`}>
      <div className="chart-head">
        <h3><Bi text={title} /></h3>
        {type !== 'table' && !error && data.length > 0 && (
          <button className="icon-btn no-print" onClick={() => setAsTable((v) => !v)}
            title={asTable ? t('showChart') : t('showTable')} aria-label="Toggle table view">
            {asTable ? <BarChart3 size={16} /> : <Table2 size={16} />}
          </button>
        )}
      </div>
      {chart.note && <p className="chart-note muted small">{tl(chart.note)}</p>}
      {error ? (
        <div className="error-box">
          <strong>{t('queryError')}</strong>
          <code>{error}</code>
        </div>
      ) : data.length === 0 ? (
        <div className="empty">{t('noData')}</div>
      ) : showTable ? (
        <DataTable rows={data} columns={columns} filename={chart.title || chart.id} />
      ) : (
        <div dir="ltr"><Plot chart={shown} xfmt={xfmt} /></div>
      )}
    </div>
  )
}
