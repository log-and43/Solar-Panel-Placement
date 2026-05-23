// "Model notes" section below the diagnostic strip. Lives where the Codex
// version had it. Contains: the generation mix bar, region facts, and a
// compact note grid showing data provenance (eGRID, EIA, Census).
//
// The honest-limits caveats live in their own panel beside this — kept
// visually distinct so they aren't easy to skip past.

import { fmtMWh, fmtPct } from '../lib/format.js'

const MIX_ORDER = ['coal', 'natural_gas', 'nuclear', 'hydro', 'wind', 'solar', 'other']
const MIX_COLORS = {
  coal: '#1f2937',
  natural_gas: '#9ca3af',
  nuclear: '#eab308',
  hydro: '#0ea5e9',
  wind: '#22c55e',
  solar: '#f97316',
  other: '#475569',
}

function MixBar({ mix }) {
  return (
    <div className="space-y-1">
      <div className="flex h-3 rounded overflow-hidden">
        {MIX_ORDER.map((k) =>
          mix[k] > 0 ? (
            <div
              key={k}
              style={{ width: `${mix[k] * 100}%`, backgroundColor: MIX_COLORS[k] }}
              title={`${k}: ${fmtPct(mix[k])}`}
            />
          ) : null
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted">
        {MIX_ORDER.filter((k) => mix[k] > 0).map((k) => (
          <span key={k} className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-sm" style={{ backgroundColor: MIX_COLORS[k] }} />
            {k.replace('_', ' ')} {fmtPct(mix[k])}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function ModelNotes({ result }) {
  if (!result) {
    return (
      <section className="border border-line rounded-lg bg-panel p-4 grid md:grid-cols-[1fr_auto] gap-5 items-center">
        <div>
          <h2 className="text-base font-semibold text-text mb-1">Model pipeline</h2>
          <p className="text-xs text-muted leading-relaxed">
            Pick a region and run the model. The pipeline derives state-level
            consumption from EIA SEDS, generation mix from EPA eGRID, and scales
            to county/city via Census ACS population shares. Polygons, generation
            per polygon, and the renewable-mix recommendation arrive in later
            phases.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2.5">
          <div className="border border-line rounded-md bg-panel2 p-2.5">
            <span className="text-[11px] text-muted">Imagery</span>
            <strong className="block mt-1 text-xs text-text">Esri World Imagery</strong>
          </div>
          <div className="border border-line rounded-md bg-panel2 p-2.5">
            <span className="text-[11px] text-muted">Demand data</span>
            <strong className="block mt-1 text-xs text-text">EIA + eGRID + Census</strong>
          </div>
          <div className="border border-line rounded-md bg-panel2 p-2.5">
            <span className="text-[11px] text-muted">Fallback</span>
            <strong className="block mt-1 text-xs text-text">Population scaling</strong>
          </div>
        </div>
      </section>
    )
  }

  const { region, consumption } = result
  return (
    <section className="border border-line rounded-lg bg-panel p-4 grid md:grid-cols-[1fr_auto] gap-5 items-start">
      <div className="space-y-3">
        <div>
          <h2 className="text-base font-semibold text-text">
            {region.name}, {region.state}
          </h2>
          <p className="text-xs text-muted">
            {region.type === 'county' ? 'County' : 'City'} ·{' '}
            {region.is_coastal ? 'Coastal' : 'Inland'} ·{' '}
            Total {fmtMWh(consumption.total_mwh_per_year)} · Fossil{' '}
            {fmtMWh(consumption.fossil_mwh_per_year)}
          </p>
        </div>
        <div>
          <h3 className="text-xs uppercase tracking-wide text-muted mb-2">Generation mix</h3>
          <MixBar mix={consumption.mix} />
          <p className="text-[11px] text-muted mt-2">Source: {consumption.source}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2.5">
        <div className="border border-line rounded-md bg-panel2 p-2.5">
          <span className="text-[11px] text-muted">Imagery</span>
          <strong className="block mt-1 text-xs text-text">Esri World Imagery</strong>
        </div>
        <div className="border border-line rounded-md bg-panel2 p-2.5">
          <span className="text-[11px] text-muted">Demand</span>
          <strong className="block mt-1 text-xs text-text">EIA + eGRID + Census</strong>
        </div>
        <div className="border border-line rounded-md bg-panel2 p-2.5">
          <span className="text-[11px] text-muted">Polygons</span>
          <strong className="block mt-1 text-xs text-text">
            {result.polygons.features.length} (placeholder)
          </strong>
        </div>
      </div>
    </section>
  )
}
