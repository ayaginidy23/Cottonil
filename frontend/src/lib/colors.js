// =============================================================================
// colors.js - Chart colours (validated colour-blind-safe categorical palette)
// -----------------------------------------------------------------------------
// Rules: hues are used in this FIXED order; a colour follows the entity (the
// same channel is always the same colour), never its rank; more than 8
// categories fold into "Other".
// =============================================================================

export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
export const NEGATIVE = '#d03b3b'   // used only for negative values (losses)
export const OTHER = '#a3a29c'

// Same set of labels -> same colours, regardless of their order in the data
export function colorMap(labels) {
  const sorted = [...new Set(labels.map(String))].sort((a, b) => a.localeCompare(b))
  const map = {}
  sorted.forEach((label, i) => {
    map[label] = label === 'Other' ? OTHER : SERIES[i % SERIES.length]
  })
  return map
}
