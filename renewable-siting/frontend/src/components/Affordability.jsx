// Phase 5: Affordability panel.
//
// Three controls — budget ($/yr), allocation (%), horizon (years) — drive a
// low/high range for installed capacity and CO2 displaced. Calls the
// lightweight /affordability endpoint on change (NOT the heavy /analyze
// pipeline), debounced so dragging a slider doesn't spam the backend.

import { useEffect, useRef, useState } from 'react'
import { getAffordability } from '../lib/api.js'
import { fmtUSD, fmtTons } from '../lib/format.js'
import SourceNote from './SourceNote.jsx'

function useDebounce(fn, delay = 250) {
  const timer = useRef(null)
  return (...args) => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => fn(...args), delay)
  }
}

function RangeStat({ label, low, high, unit, fmt, source, formula }) {
  const f = fmt || ((v) => v?.toLocaleString?.() ?? '—')
  return (
    <div className="bg-panel2 rounded-md p-3 border border-line">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-lg font-semibold text-text mt-1">
        {f(low)} <span className="text-muted text-sm">–</span> {f(high)}
        {unit && <span className="text-xs text-muted ml-1">{unit}</span>}
      </div>
      <SourceNote source={source} formula={formula} />
    </div>
  )
}

export default function Affordability({ result }) {
  const [allocationPct, setAllocationPct] = useState(0.10)
  const [horizonYears, setHorizonYears] = useState(20)
  const [budgetText, setBudgetText] = useState('')  // raw input string; '' = use backend's
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const region = result?.region

  // Parse the budget text to a number only when sending. Empty / invalid → null
  // (meaning "let the backend look up the region's budget").
  const budgetOverride = budgetText.trim() === '' ? null : Number(budgetText)

  const fetchAfford = useDebounce(async (params) => {
    setLoading(true)
    setError(null)
    try {
      const d = await getAffordability(params)
      setData(d)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, 250)

  useEffect(() => {
    if (!region) { setData(null); return }
    // Don't fire on a half-typed number (e.g. "10" while the user means 10000000).
    // Only send budget if it's empty (use backend) or a finished positive number.
    const budgetValid = budgetText.trim() === '' || (Number.isFinite(budgetOverride) && budgetOverride >= 0)
    if (!budgetValid) return
    fetchAfford({
      state: region.state,
      region_type: region.type,
      region_name: region.name,
      allocation_pct: allocationPct,
      horizon_years: horizonYears,
      budget_dollars: budgetOverride,
    })
  }, [region, allocationPct, horizonYears, budgetText])  // eslint-disable-line

  if (!result) {
    return (
      <section className="border border-line rounded-lg bg-panel p-4">
        <h2 className="text-base font-semibold text-text mb-1">Affordability</h2>
        <p className="text-xs text-muted">
          Run a region to estimate what its capital budget could build out.
        </p>
      </section>
    )
  }

  const unavailable = data && data.available === false
  const usingManualBudget = budgetText.trim() !== ''

  return (
    <section className="border border-line rounded-lg bg-panel p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-text">Affordability — realism estimate</h2>
        {loading && <span className="spinner" />}
      </div>

      {error && (
        <div className="text-xs text-rose bg-rose/10 border border-rose/30 rounded p-2">
          {error}
        </div>
      )}

      {/* Persistent budget control — always visible, never unmounts. */}
      <label className="block">
        <div className="flex justify-between text-xs text-muted mb-1">
          <span>Annual capital budget</span>
          <span className="text-text font-medium">
            {usingManualBudget
              ? 'manual'
              : (data?.budget_dollars != null ? fmtUSD(data.budget_dollars) : 'auto')}
          </span>
        </div>
        <input
          type="number" min="0" step="1000000"
          value={budgetText}
          onChange={(e) => setBudgetText(e.target.value)}
          className="w-full border border-line rounded-md bg-[#111716] text-text min-h-9 px-2"
          placeholder={
            data?.budget_dollars != null
              ? `${data.budget_dollars.toLocaleString()} (from data — type to override)`
              : 'Enter annual capital budget, e.g. 100000000'
          }
        />
        <span className="text-[11px] text-muted mt-1 block">
          {unavailable
            ? `No budget data on file for ${region.name}. Enter one to model it.`
            : 'Leave blank to use the region\u2019s budget from Census data.'}
        </span>
      </label>

      {/* Sliders — always visible. */}
      <div className="space-y-3">
        <label className="block">
          <div className="flex justify-between text-xs text-muted mb-1">
            <span>Budget allocated to renewables</span>
            <span className="text-text font-medium">{(allocationPct * 100).toFixed(0)}%</span>
          </div>
          <input
            type="range" min="0" max="0.5" step="0.01"
            value={allocationPct}
            onChange={(e) => setAllocationPct(Number(e.target.value))}
            className="w-full accent-rooftop"
          />
        </label>

        <label className="block">
          <div className="flex justify-between text-xs text-muted mb-1">
            <span>Time horizon</span>
            <span className="text-text font-medium">{horizonYears} years</span>
          </div>
          <input
            type="range" min="1" max="40" step="1"
            value={horizonYears}
            onChange={(e) => setHorizonYears(Number(e.target.value))}
            className="w-full accent-rooftop"
          />
        </label>
      </div>

      {/* Results — shown when we have an available computation. */}
      {data && data.available && (
        <>
          <p className="text-sm text-text leading-relaxed bg-panel2 rounded-md p-3 border border-line">
            Allocating <b>{(data.allocation_pct * 100).toFixed(0)}%</b> of{' '}
            <b>{fmtUSD(data.budget_dollars)}</b>/yr for{' '}
            <b>{data.horizon_years} years</b> could fund{' '}
            <b>{data.installed_mw_low?.toLocaleString()}–{data.installed_mw_high?.toLocaleString()} MW</b>{' '}
            of solar, displacing roughly{' '}
            <b>{fmtTons(data.co2_tons_per_year_low)}–{fmtTons(data.co2_tons_per_year_high)}</b>/yr.
          </p>

          <div className="grid grid-cols-2 gap-2">
            <RangeStat label="Installed capacity" low={data.installed_mw_low}
                       high={data.installed_mw_high} unit="MW"
                       source="NREL ATB 2024 cost range + region capital budget"
                       formula="MW = (budget × allocation × years) ÷ cost-per-watt" />
            <RangeStat label="Annual generation" low={data.annual_gwh_low}
                       high={data.annual_gwh_high} unit="GWh/yr"
                       fmt={(v) => v?.toFixed?.(1)}
                       source="Derived from capacity and region capacity factor"
                       formula="GWh = MW × 8760 h × capacity factor × degradation ÷ 1000" />
            <RangeStat label="CO₂ displaced / yr" low={data.co2_tons_per_year_low}
                       high={data.co2_tons_per_year_high} fmt={fmtTons}
                       source="EPA eGRID grid CO₂ intensity"
                       formula="tons = GWh × 1000 × grid intensity" />
            <RangeStat label={`CO₂ over ${data.horizon_years}yr`}
                       low={data.co2_tons_cumulative_low}
                       high={data.co2_tons_cumulative_high} fmt={fmtTons}
                       source="EPA eGRID grid CO₂ intensity"
                       formula="= annual CO₂ × horizon years" />
          </div>

          <p className="text-[11px] text-muted">
            Range from NREL ATB cost spread (${data.cost_per_watt_low}–${data.cost_per_watt_high}/W).
            Budget source: {data.source}.
          </p>
        </>
      )}
    </section>
  )
}
