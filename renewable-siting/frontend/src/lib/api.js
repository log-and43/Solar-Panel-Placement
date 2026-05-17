// Tiny backend client. One reason for keeping it minimal: when the contract
// in docs/CONTRACT.md is honored, the frontend doesn't need to know which
// phase the backend is in.

const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export async function listRegions() {
  const r = await fetch(`${BASE}/regions`)
  if (!r.ok) throw new Error(`GET /regions ${r.status}`)
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
