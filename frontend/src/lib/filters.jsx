// =============================================================================
// filters.jsx - Global filters shared by every app (React Context)
// -----------------------------------------------------------------------------
// Context = a value that any component can read without passing it down through
// every level. Here: the selected date range, branches and channels, plus the
// options (branch list, channel list, date limits) loaded once from the API.
//
// Two copies of the filters:
//   draft   - what the filter bar shows; changes instantly while the user clicks
//   filters - what the pages load data with; follows the draft 0.5 s after the
//             LAST change, so picking a date or ticking 5 branches loads the page
//             once, not once per click
// =============================================================================
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api.js'

const FiltersContext = createContext(null)
const DEBOUNCE_MS = 500

export function FiltersProvider({ children }) {
  const [options, setOptions] = useState(null)
  const [error, setError] = useState(null)
  const [draft, setDraft] = useState({ dateFrom: null, dateTo: null, branches: [], channels: [] })
  const [filters, setFilters] = useState(draft)

  // the pages follow the draft only after the user stopped changing it for DEBOUNCE_MS
  useEffect(() => {
    if (draft === filters) return undefined
    const timer = setTimeout(() => setFilters(draft), DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [draft]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load the filter options once, then start on the default period (last 12 complete months)
  useEffect(() => {
    api
      .filterOptions()
      .then((opts) => {
        setOptions(opts)
        const start = { dateFrom: opts.default_period.date_from, dateTo: opts.default_period.date_to,
          branches: [], channels: [] }
        setDraft(start)
        setFilters(start)                           // first load: no waiting
      })
      .catch((e) => setError(e.message))
  }, [])

  const presets = useMemo(() => {
    if (!options) return []
    const { dates, default_period: dp } = options
    const lastYear = Number(dates.complete_to.slice(0, 4))
    return [
      { id: 'l12m', label: 'Last 12 months', from: dp.date_from, to: dp.date_to },
      { id: 'ytd', label: 'Year to date', from: `${lastYear}-01-01`, to: dates.complete_to },
      { id: 'ly', label: `${lastYear - 1}`, from: `${lastYear - 1}-01-01`, to: `${lastYear - 1}-12-31` },
      { id: 'all', label: 'All time', from: dates.data_from, to: dates.data_to },
    ]
  }, [options])

  const value = {
    options,
    error,
    filters,
    draft,
    presets,
    ready: Boolean(options && filters.dateFrom),
    setFilters: setDraft,
    update: (patch) => setDraft((f) => ({ ...f, ...patch })),
    reset: () =>
      options &&
      setDraft({
        dateFrom: options.default_period.date_from,
        dateTo: options.default_period.date_to,
        branches: [],
        channels: [],
      }),
  }
  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>
}

export function useFilters() {
  return useContext(FiltersContext)
}