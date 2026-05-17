import { fmtMWh, fmtUSD, fmtTons, fmtYears, fmtPct } from '../lib/format.js'

function MixBar({ mix }) {
  // Order matters for stacked bar readability.
  const order = ['coal', 'natural_gas', 'nuclear', 'hydro', 'wind', 'solar', 'other']
  const colors = {
    coal: '#1f2937',
    natural_gas: '#9ca3af',
    nuclear: '#eab308',
    hydro: '#0ea5e9',
    wind: '#22c55e',
    solar: '#f97316',
    other: '#cbd5e1',
  }
  return (
    <div className="space-y-1">
      <div className="flex h-3 rounded overflow-hidden">
        {order.map((k) => (
          mix[k] > 0 ? (
            <div
              key={k}
              style={{ width: `${mix[k] * 100}%`, backgroundColor: colors[k] }}
              title={`${k}: ${fmtPct(mix[k])}`}
            />
          ) : null
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600">
        {order.filter(k => mix[k] > 0).map((k) => (
          <span key={k} className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-sm" style={{ backgroundColor: colors[k] }} />
            {k.replace('_', ' ')} {fmtPct(mix[k])}
          </span>
        ))}
      </div>
    </div>
  )
}

function Stat({ label, value, sub }) {
  return (
    <div className="bg-slate-50 rounded p-3">
      <div className="text-xs text-slate-500 uppercase tracking-wide">{label}</div>
      <div className="text-xl font-semibold text-slate-800">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  )
}

export default function Diagnostic({ result }) {
  if (!result) {
    return (
      <div className="bg-white rounded-lg shadow p-4 text-sm text-slate-500">
        Run a region to see results here.
      </div>
    )
  }
  const { region, consumption, recommendation, economics } = result
  const primaryLabel = {
    solar: 'Solar (rooftop + parking)',
    wind: 'Onshore wind',
    offshore_wind: 'Offshore wind',
    mixed: 'Mixed: solar + wind',
    insufficient: 'Insufficient — gap remains',
  }[recommendation.primary] || recommendation.primary

  return (
    <div className="bg-white rounded-lg shadow p-4 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-800">
          {region.name}, {region.state}
        </h2>
        <p className="text-xs text-slate-500">
          {region.type === 'county' ? 'County' : 'City'} · {region.is_coastal ? 'coastal' : 'inland'}
        </p>
      </div>

      <section>
        <h3 className="text-sm font-semibold text-slate-700 mb-2">Generation mix (state-derived)</h3>
        <MixBar mix={consumption.mix} />
        <p className="text-xs text-slate-500 mt-2">Source: {consumption.source}</p>
      </section>

      <section className="grid grid-cols-2 gap-2">
        <Stat label="Annual consumption" value={fmtMWh(consumption.total_mwh_per_year)} />
        <Stat label="Fossil share" value={fmtMWh(consumption.fossil_mwh_per_year)} sub="to displace" />
      </section>

      <section className="border-t pt-3">
        <h3 className="text-sm font-semibold text-slate-700 mb-2">Recommendation</h3>
        <div className="text-base font-medium text-emerald-700">{primaryLabel}</div>
        <p className="text-sm text-slate-600 mt-1">{recommendation.notes}</p>
        <div className="grid grid-cols-2 gap-2 mt-3">
          <Stat label="Covered" value={fmtMWh(recommendation.covered_mwh_per_year)} />
          <Stat label="Remaining gap" value={fmtMWh(recommendation.gap_mwh_per_year)} />
        </div>
        {recommendation.alternatives?.length > 0 && (
          <div className="mt-3 space-y-1">
            <div className="text-xs uppercase text-slate-500 tracking-wide">Alternatives considered</div>
            {recommendation.alternatives.map((a, i) => (
              <div key={i} className="text-sm bg-slate-50 rounded p-2">
                <div className="font-medium">{a.tech.replace('_', ' ')}</div>
                <div className="text-xs text-slate-600">{a.rationale}</div>
                <div className="text-xs text-slate-500">Potential: {fmtMWh(a.potential_mwh)}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="border-t pt-3">
        <h3 className="text-sm font-semibold text-slate-700 mb-2">Economics</h3>
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Install cost" value={fmtUSD(economics.install_cost_usd)} />
          <Stat label="Annual savings" value={fmtUSD(economics.annual_savings_usd)} />
          <Stat label="Payback" value={fmtYears(economics.payback_years)} />
          <Stat label="CO₂ avoided" value={fmtTons(economics.co2_avoided_tons_per_year)} sub="per year" />
        </div>
      </section>
    </div>
  )
}
