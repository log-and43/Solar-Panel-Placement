// Model notes: pipeline narrative + provenance tiles. Generation Mix bar
// and Caveats list live in DataQuality.

import { useEffect, useState } from 'react'
import { getPolygonsStatus, getPvwattsStatus } from '../lib/api.js'

export default function ModelNotes({ result }) {
  const [pvStatus, setPvStatus] = useState(null)
  const [polyStatus, setPolyStatus] = useState(null)

  useEffect(() => {
    getPvwattsStatus().then(setPvStatus).catch(() => setPvStatus(null))
    getPolygonsStatus().then(setPolyStatus).catch(() => setPolyStatus(null))
  }, [result])  // re-fetch after each run so cache counts update

  const pvLabel = pvStatus
    ? (pvStatus.api_key_configured
        ? `NREL PVWatts v8 (${pvStatus.cache?.entries ?? 0} cached)`
        : 'Approximation (no key)')
    : '—'
  const pvTone = pvStatus?.api_key_configured ? 'text-text' : 'text-parking'

  const polyLabel = polyStatus
    ? (polyStatus.overture_available
        ? `Overture + OSM (${polyStatus.cache?.entries ?? 0} cached)`
        : 'Phase 1 placeholders (duckdb missing)')
    : '—'
  const polyTone = polyStatus?.overture_available ? 'text-text' : 'text-parking'

  // For result-mode, count polygons by category for an at-a-glance breakdown.
  let rooftopCount = 0, parkingCount = 0
  if (result?.polygons?.features) {
    for (const f of result.polygons.features) {
      if (f.properties.category === 'rooftop') rooftopCount++
      else if (f.properties.category === 'parking') parkingCount++
    }
  }

  return (
    <section className="border border-line rounded-lg bg-panel p-4 grid md:grid-cols-[1fr_auto] gap-5 items-center">
      <div>
        <h2 className="text-base font-semibold text-text mb-1">Model pipeline</h2>
        <p className="text-xs text-muted leading-relaxed">
          State consumption from EIA SEDS scales to county/city via Census ACS
          populations. Generation mix from EPA eGRID. Polygons come from Overture
          Maps (buildings) and OpenStreetMap (parking), filtered to commercial-scale
          surfaces. Each rooftop/parking polygon is sized for a real NREL PVWatts
          estimate when a key is configured.
          {result && ` This run: ${rooftopCount} rooftops, ${parkingCount} parking lots.`}
        </p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
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
          <strong className={`block mt-1 text-xs ${polyTone}`}>{polyLabel}</strong>
        </div>
        <div className="border border-line rounded-md bg-panel2 p-2.5">
          <span className="text-[11px] text-muted">Solar resource</span>
          <strong className={`block mt-1 text-xs ${pvTone}`}>{pvLabel}</strong>
        </div>
      </div>
    </section>
  )
}
