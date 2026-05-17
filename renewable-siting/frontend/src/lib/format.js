export function fmtMWh(v) {
  if (v == null) return '—'
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} TWh`
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)} GWh`
  return `${v.toFixed(0)} MWh`
}

export function fmtUSD(v) {
  if (v == null) return '—'
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`
  return `$${v.toFixed(0)}`
}

export function fmtTons(v) {
  if (v == null) return '—'
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M t CO₂`
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k t CO₂`
  return `${v.toFixed(0)} t CO₂`
}

export function fmtYears(v) {
  if (v == null) return 'no payback'
  return `${v.toFixed(1)} yrs`
}

export function fmtPct(v) {
  return `${(v * 100).toFixed(0)}%`
}
