import { useEffect, useMemo, useState } from 'react'
import { listRegions } from '../lib/api.js'

export default function RegionPicker({ onRun, running }) {
  const [regions, setRegions] = useState([])
  const [denom, setDenom] = useState('county') // county or city
  const [state, setState] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    listRegions()
      .then((data) => {
        setRegions(data)
        if (data.length > 0) {
          setState(data[0].state)
        }
      })
      .catch((e) => setError(e.message))
  }, [])

  const statesAvailable = useMemo(
    () => Array.from(new Set(regions.map((r) => r.state))).sort(),
    [regions]
  )

  const namesForChoice = useMemo(
    () => regions.filter((r) => r.state === state && r.region_type === denom).map((r) => r.name),
    [regions, state, denom]
  )

  // Auto-select first available name when filters change
  useEffect(() => {
    if (namesForChoice.length > 0 && !namesForChoice.includes(name)) {
      setName(namesForChoice[0])
    } else if (namesForChoice.length === 0) {
      setName('')
    }
  }, [namesForChoice, name])

  const canRun = state && denom && name && !running

  return (
    <div className="bg-white rounded-lg shadow p-4 space-y-3">
      <h2 className="text-lg font-semibold text-slate-800">Pick a region</h2>

      {error && (
        <div className="text-red-700 text-sm bg-red-50 border border-red-200 p-2 rounded">
          Could not reach backend: {error}. Is it running on :8000?
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
            value={state}
            onChange={(e) => setState(e.target.value)}
            className="border rounded px-2 py-1.5"
          >
            {statesAvailable.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex flex-col text-sm">
        <span className="text-slate-600 mb-1">
          {denom === 'county' ? 'County' : 'City'}
        </span>
        <select
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border rounded px-2 py-1.5"
          disabled={namesForChoice.length === 0}
        >
          {namesForChoice.length === 0 && (
            <option value="">— none seeded for this state yet —</option>
          )}
          {namesForChoice.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>

      <button
        onClick={() => onRun({ state, region_type: denom, region_name: name })}
        disabled={!canRun}
        className="w-full bg-emerald-600 disabled:bg-slate-300 hover:bg-emerald-700 text-white font-semibold py-2 rounded transition"
      >
        {running ? 'Analyzing…' : 'Run'}
      </button>

      <p className="text-xs text-slate-500">
        Phase 1: only WA / Whatcom County / Bellingham are seeded.
      </p>
    </div>
  )
}
