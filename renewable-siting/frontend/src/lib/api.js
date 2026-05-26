// Tiny backend client. One reason for keeping it minimal: when the contract
// in docs/CONTRACT.md is honored, the frontend doesn't need to know which
// phase the backend is in.

const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export async function listStates() {
  const r = await fetch(`${BASE}/states`)
  if (!r.ok) throw new Error(`GET /states ${r.status}`)
  return r.json()
}

export async function searchRegions({ regionType, state, q, limit = 25 }) {
  const params = new URLSearchParams({ region_type: regionType, limit: String(limit) })
  if (state) params.set('state', state)
  if (q) params.set('q', q)
  const r = await fetch(`${BASE}/search?${params.toString()}`)
  if (!r.ok) throw new Error(`GET /search ${r.status}`)
  return r.json()
}

export async function getHealth() {
  const r = await fetch(`${BASE}/health`)
  if (!r.ok) throw new Error(`GET /health ${r.status}`)
  return r.json()
}

export async function getPvwattsStatus() {
  const r = await fetch(`${BASE}/pvwatts/status`)
  if (!r.ok) throw new Error(`GET /pvwatts/status ${r.status}`)
  return r.json()
}

export async function getPolygonsStatus() {
  const r = await fetch(`${BASE}/polygons/status`)
  if (!r.ok) throw new Error(`GET /polygons/status ${r.status}`)
  return r.json()
}

export async function analyze({ state, region_type, region_name }) {
  const r = await fetch(`${BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state, region_type, region_name }),
  })
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`POST /analyze ${r.status}: ${text}`)
  }
  return r.json()
}
