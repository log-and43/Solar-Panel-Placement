import { useEffect, useMemo, useRef, useState } from 'react'
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
  const [selected, setSelected] = useState(null) // {state, region_type, name, population}
  const [open, setOpen] = useState(false)
  const [phase2Ready, setPhase2Ready] = useState(true)
  const [error, setError] = useState(null)

  // Bootstrap: load state list + health on mount.
  useEffect(() => {
    Promise.all([listStates(), getHealth()])
      .then(([st, hp]) => {
        setStates(st)
        if (st.length > 0) setStateAbbr(st[0].abbr)
        setPhase2Ready(hp.data_built)
      })
      .catch((e) => setError(e.message))
  }, [])

  // Search when query, state, or denomination changes.
  const runSearch = useDebounce(async (params) => {
    try {
      const data = await searchRegions(params)
      setResults(data)
      // Auto-select if the typed query exactly matches a result name.
      // Saves a click for "I already know what I want" usage.
      const exact = data.find(r => r.name.toLowerCase() === params.q.trim().toLowerCase())
      if (exact) setSelected(exact)
    } catch (e) {
      setError(e.message)
    }
  }, 200)

  useEffect(() => {
    // If the query no longer matches the currently-selected row, clear it.
    // (Just changing the query to match the selected row's name should NOT
    // wipe the selection — that's how clicking a result works.)
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

  return (
    <div className="bg-white rounded-lg shadow p-4 space-y-3">
      <h2 className="text-lg font-semibold text-slate-800">Pick a region</h2>

      {!phase2Ready && (
        <div className="text-amber-800 text-xs bg-amber-50 border border-amber-200 p-2 rounded">
          Phase 2 data not built. Showing Phase-1 fallback (WA only). Run
          <code className="mx-1 px-1 bg-amber-100 rounded">python scripts/build_data.py</code>
          in the backend folder to enable full coverage.
        </div>
      )}

      {error && (
        <div className="text-red-700 text-sm bg-red-50 border border-red-200 p-2 rounded">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col text-sm">
          <span className="text-slate-600 mb-1">Denomination</span>
          <select
            value={denom}
            onChange={(e) => setDenom(e.target.value)}
            className="border rounded px-2 py-1.5"
          >
            <option value="county">County</option>
            <option value="city">City</option>
          </select>
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-slate-600 mb-1">State</span>
          <select
            value={stateAbbr}
            onChange={(e) => setStateAbbr(e.target.value)}
            className="border rounded px-2 py-1.5"
          >
            {states.map((s) => (
              <option key={s.abbr} value={s.abbr}>
                {s.abbr} — {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex flex-col text-sm relative">
        <span className="text-slate-600 mb-1">
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
          className="border rounded px-2 py-1.5"
          placeholder={denom === 'county' ? 'e.g. Whatcom County' : 'e.g. Bellingham'}
        />
        {open && results.length > 0 && (
          <ul className="absolute top-full left-0 right-0 z-20 bg-white border border-slate-200 rounded mt-1 max-h-72 overflow-y-auto shadow-lg">
            {results.map((row, i) => (
              <li
                key={`${row.state}-${row.name}-${i}`}
                onMouseDown={() => handleSelect(row)}
                className="px-3 py-1.5 hover:bg-emerald-50 cursor-pointer text-sm flex justify-between"
              >
                <span>{row.name}</span>
                <span className="text-slate-400 text-xs">
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
        className="w-full bg-emerald-600 disabled:bg-slate-300 hover:bg-emerald-700 text-white font-semibold py-2 rounded transition"
      >
        {running ? 'Analyzing…' : 'Run'}
      </button>

      <p className="text-xs text-slate-500">
        {phase2Ready
          ? 'All US states + counties; cities ≥ 10,000 pop.'
          : 'Phase-1 fallback: WA only.'}
      </p>
    </div>
  )
}
