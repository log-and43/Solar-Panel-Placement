import { fmtUSD, fmtTons, fmtYears } from '../lib/format.js'
import SourceNote from './SourceNote.jsx'

// 4-card diagnostic strip, adapted from the Codex frontend layout.
// Sits below the map. Reads from the AnalyzeResponse plus the user's
// energy-target override.

function Card({ label, value, sub, source, formula }) {
  return (
    <article className="border border-line rounded-lg bg-panel p-4">
      <span className="text-[11px] uppercase tracking-wide text-muted">{label}</span>
      <strong className="block text-2xl my-1.5 text-text">{value}</strong>
      <p className="text-xs text-muted leading-snug">{sub}</p>
      <SourceNote source={source} formula={formula} />
    </article>
  )
}

export default function Diagnostic({ result, energyTargetGwh }) {
  if (!result) {
    return (
      <section className="grid grid-cols-4 gap-3">
        {['Solar generation', 'Alternative renewable', 'Installation cost', 'CO₂ relief'].map((label) => (
          <Card key={label} label={label} value="—" sub="Run the model to populate." />
        ))}
      </section>
    )
  }

  // The "target" is either the user's override or the region's full fossil load.
  const fossilGwh = result.consumption.fossil_mwh_per_year / 1000.0
  const target = energyTargetGwh ?? fossilGwh

  // Solar coverage from rooftop + parking polygons (offshore is wind, counted separately).
  const solarMwh = (result.polygons?.features ?? [])
    .filter(f => f.properties.category === 'rooftop' || f.properties.category === 'parking')
    .reduce((s, f) => s + (f.properties.est_annual_mwh ?? 0), 0)
  const solarGwh = solarMwh / 1000.0
  const solarPct = target > 0 ? Math.min(100, (solarGwh / target) * 100) : 0
  const remainingGwh = Math.max(0, target - solarGwh)

  // Alternative — from recommendation.alternatives + offshore_wind_zone polygons.
  const altMwh = (result.polygons?.features ?? [])
    .filter(f => f.properties.category === 'offshore_wind_zone')
    .reduce((s, f) => s + (f.properties.est_annual_mwh ?? 0), 0)
  const altGwh = altMwh / 1000.0
  const altPrimary = result.recommendation?.primary
  const altLabel = altPrimary === 'offshore_wind' || result.region.is_coastal
    ? 'Offshore wind'
    : (result.recommendation?.alternatives?.[0]?.tech ?? 'Not specified')

  // Phase 7: real economics provenance, when the backend supplies it.
  const es = result.economics_sources || null

  return (
    <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
      <Card
        label="Solar generation"
        value={`${solarGwh.toFixed(2)} GWh/yr`}
        sub={`${solarPct.toFixed(0)}% of the ${target.toFixed(2)} GWh fossil offset target.`}
        source="NREL PVWatts v8 (NSRDB), summed over rooftop + parking polygons"
        formula="annual GWh = Σ (polygon kW × per-kW yield) ÷ 1000"
      />
      <Card
        label="Alternative renewable"
        value={altGwh > 0 ? `${altGwh.toFixed(2)} GWh/yr` : 'Not needed'}
        sub={
          remainingGwh > 0
            ? `Solar leaves ${remainingGwh.toFixed(2)} GWh/yr. Primary alternative: ${altLabel}.`
            : 'Solar covers the modeled target.'
        }
        source="Placeholder — offshore wind not yet sited from real lease areas (Phase 6)"
      />
      <Card
        label="Installation cost"
        value={fmtUSD(result.economics.install_cost_usd)}
        sub={`${fmtYears(result.economics.payback_years)} simple payback at the state commercial rate.`}
        source={es ? es.install_cost : "Placeholder — national-average $/W, not site-specific (Phase 7)"}
        formula="cost = installed watts × $/W"
      />
      <Card
        label="CO₂ relief"
        value={fmtTons(result.economics.co2_avoided_tons_per_year)}
        sub={`Avoided emissions per year, using ${result.region.state}'s grid intensity.`}
        source={es ? es.co2_avoided : "Placeholder — national-average emissions factor (Phase 7)"}
        formula="CO₂ = generation (MWh) × grid intensity"
      />
    </section>
  )
}
