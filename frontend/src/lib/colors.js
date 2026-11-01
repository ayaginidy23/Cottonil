// =============================================================================
// colors.js - Chart colours (validated colour-blind-safe categorical palette)
// -----------------------------------------------------------------------------
// Rules: hues are used in this FIXED order; a colour follows the entity (the
// same channel is always the same colour), never its rank; more than 8
// categories fold into "Other".
// =============================================================================

// brand royal blue first, then hues that stay distinct for colour-blind readers
export const SERIES = ['#2f6fd6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
export const NEGATIVE = '#c23b3b'   // used only for negative values (losses)
export const OTHER = '#a7afbf'

// Same set of labels -> same colours, regardless of their order in the data
export function colorMap(labels) {
  const sorted = [...new Set(labels.map(String))].sort((a, b) => a.localeCompare(b))
  const map = {}
  sorted.forEach((label, i) => {
    map[label] = label === 'Other' ? OTHER : SERIES[i % SERIES.length]
  })
  return map
}