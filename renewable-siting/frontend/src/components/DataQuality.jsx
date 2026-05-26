// "Data Quality" section combining the Generation Mix bar with the Caveats
// list. Codex's Phase 3 paired these together in a dedicated section
// between the diagnostic strip and the model notes; that's a cleaner
// information hierarchy than burying the mix inside ModelNotes.

import { fmtPct } from '../lib/format.js'

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
    <div>
      <div className="flex h-4 rounded-full overflow-hidden border border-line bg-[#0f1514]">
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
      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2.5 text-xs text-muted">
        {MIX_ORDER.filter((k) => mix[k] > 0).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block w-2.5 h-2.5 rounded-sm"
              style={{ backgroundColor: MIX_COLORS[k] }}
            />
            {k.replace('_', ' ')} {fmtPct(mix[k])}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function DataQuality({ result }) {
  if (!result) {
    return (
      <section className="border border-line rounded-lg bg-panel p-4 grid md:grid-cols-[1fr_0.8fr] gap-5">
        <div>
          <h2 className="text-base font-semibold text-text mb-2">Generation Mix</h2>
          <p className="text-xs text-muted">Run the model to see the generation mix for the selected state.</p>
        </div>
        <div>
          <h2 className="text-base font-semibold text-text mb-2">Data Caveats</h2>
          <p className="text-xs text-muted">Honest limitations of this run will appear after analysis.</p>
        </div>
      </section>
    )
  }

  const { consumption, caveats } = result

  return (
    <section className="border border-line rounded-lg bg-panel p-4 grid md:grid-cols-[1fr_0.8fr] gap-5">
      <div>
        <h2 className="text-base font-semibold text-text mb-3">Generation Mix</h2>
        <MixBar mix={consumption.mix} />
        <p className="text-[11px] text-muted mt-2">Source: {consumption.source}</p>
      </div>
      <div>
        <h2 className="text-base font-semibold text-text mb-2">Data Caveats</h2>
        <ul className="list-disc pl-5 space-y-1.5 text-muted text-xs">
          {(caveats || []).map((c, i) => (
            <li key={i} className="leading-snug">{c}</li>
          ))}
        </ul>
      </div>
    </section>
  )
}
