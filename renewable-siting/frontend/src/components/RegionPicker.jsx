import { useEffect, useRef, useState } from 'react'
import { getHealth, listStates, searchRegions } from '../lib/api.js'

// Debounce helper — fires `fn` after `delay` ms of inactivity.
function useDebounce(fn, delay = 200) {
  const timer = useRef(null)
  return (...args) => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => fn(...args), delay)
  }
}

export default function RegionPicker({ onRun, running }) {
  const [denom, setDenom] = useState('county')
  const [stateAbbr, setStateAbbr] = useState('')
  const [states, setStates] = useState([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selected, setSelected] = useState(null)
  const [open, setOpen] = useState(false)
  const [phase2Ready, setPhase2Ready] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([listStates(), getHealth()])
      .then(([st, hp]) => {
        setStates(st)
        if (st.length > 0) setStateAbbr(st[0].abbr)
        setPhase2Ready(hp.data_built)
      })
      .catch((e) => setError(e.message))
  }, [])

  const runSearch = useDebounce(async (params) => {
    try {
      const data = await searchRegions(params)
      setResults(data)
      const exact = data.find(r => r.name.toLowerCase() === params.q.trim().toLowerCase())
      if (exact) setSelected(exact)
    } catch (e) {
      setError(e.message)
    }
  }, 200)

  useEffect(() => {
    if (selected && query !== selected.name) {
      setSelected(null)
    }
    if (stateAbbr) {
      runSearch({ regionType: denom, state: stateAbbr, q: query })
    }
  }, [denom, stateAbbr, query])  // eslint-disable-line react-hooks/exhaustive-deps

  const canRun = selected && !running

  function handleSelect(row) {
    setSelected(row)
    setQuery(row.name)
    setOpen(false)
  }

  // Segmented control inspired by the Codex frontend — feels more product-y
  // than a dropdown for a 2-state choice.
  const segments = [
    { value: 'county', label: 'County' },
    { value: 'city', label: 'City' },
  ]

  return (
    <section className="border border-line rounded-lg bg-panel p-4 space-y-3">
      <h2 className="text-sm font-semibold text-text">Area</h2>

      {!phase2Ready && (
        <div className="text-[11px] text-rose bg-rose/10 border border-rose/30 p-2 rounded">
          Phase 2 data not built. Showing fallback (WA only). Run
          <code className="mx-1 px-1 bg-panel2 rounded">python scripts/build_data.py</code>.
        </div>
      )}

      {error && (
        <div className="text-[11px] text-rose bg-rose/10 border border-rose/30 p-2 rounded">
          {error}
        </div>
      )}

      <div
        className="grid grid-cols-2 border border-line rounded-md overflow-hidden"
        role="group"
        aria-label="Geography type"
      >
        {segments.map((seg) => {
          const active = denom === seg.value
          return (
            <button
              key={seg.value}
              onClick={() => setDenom(seg.value)}
              className={
                'min-h-9 text-sm transition ' +
                (active
                  ? 'bg-rooftop text-[#08120d] font-bold'
                  : 'bg-transparent text-muted hover:text-text')
              }
            >
              {seg.label}
            </button>
          )
        })}
      </div>

      <label className="block">
        <span className="text-xs text-muted block mb-1">State</span>
        <select
          value={stateAbbr}
          onChange={(e) => setStateAbbr(e.target.value)}
          className="w-full border border-line rounded-md bg-[#111716] text-text min-h-9 px-2"
        >
          {states.map((s) => (
            <option key={s.abbr} value={s.abbr}>
              {s.abbr} — {s.name}
            </option>
          ))}
        </select>
      </label>

      <label className="block relative">
        <span className="text-xs text-muted block mb-1">
          {denom === 'county' ? 'County' : 'City'} (type to search)
        </span>
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setSelected(null)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={denom === 'county' ? 'e.g. Whatcom County' : 'e.g. Bellingham'}
          className="w-full border border-line rounded-md bg-[#111716] text-text min-h-9 px-2"
        />
        {open && results.length > 0 && (
          <ul className="absolute top-full left-0 right-0 z-20 mt-1 max-h-72 overflow-y-auto rounded-md border border-line bg-panel2 shadow-lg">
            {results.map((row, i) => (
              <li
                key={`${row.state}-${row.name}-${i}`}
                onMouseDown={() => handleSelect(row)}
                className="px-3 py-1.5 hover:bg-line/60 cursor-pointer text-sm flex justify-between"
              >
                <span className="text-text">{row.name}</span>
                <span className="text-muted text-xs">
                  {row.state}{row.population ? ` · ${row.population.toLocaleString()}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </label>

      <button
        onClick={() =>
          selected && onRun({
            state: selected.state,
            region_type: selected.region_type,
            region_name: selected.name,
          })
        }
        disabled={!canRun}
        className="w-full inline-flex gap-2 items-center justify-center min-h-11 rounded-md font-extrabold text-[#08120d] bg-parking disabled:bg-line disabled:text-muted transition hover:brightness-110"
      >
        {running ? (
          <>
            <span className="spinner" />
            <span>Analyzing…</span>
          </>
        ) : (
          <span>▶ Run model</span>
        )}
      </button>

      <p className="text-[11px] text-muted">
        {phase2Ready
          ? 'All US states + counties; cities ≥ 10,000 pop.'
          : 'Fallback mode: WA only.'}
      </p>
    </section>
  )
}
