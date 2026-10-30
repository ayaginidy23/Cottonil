// =============================================================================
// filters.jsx - Global filters shared by every app (React Context)
// -----------------------------------------------------------------------------
// Context = a value that any component can read without passing it down through
// every level. Here: the selected date range, branches and channels, plus the
// options (branch list, channel list, date limits) loaded once from the API.
// =============================================================================
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api.js'

const FiltersContext = createContext(null)

export function FiltersProvider({ children }) {
  const [options, setOptions] = useState(null)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ dateFrom: null, dateTo: null, branches: [], channels: [] })

  // Load the filter options once, then start on the default period (last 12 complete months)
  useEffect(() => {
    api
      .filterOptions()
      .then((opts) => {
        setOptions(opts)
        setFilters((f) => ({
          ...f,
          dateFrom: opts.default_period.date_from,
          dateTo: opts.default_period.date_to,
        }))
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
    presets,
    ready: Boolean(options && filters.dateFrom),
    setFilters,
    update: (patch) => setFilters((f) => ({ ...f, ...patch })),
    reset: () =>
      options &&
      setFilters({
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
