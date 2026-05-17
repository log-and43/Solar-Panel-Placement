import { useEffect } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'

// Color by polygon category. Phase 5 may add 'cv_detected_parking' as a
// visually distinct shade so provenance is visible on the map.
const STYLES = {
  rooftop: { color: '#f59e0b', weight: 1, fillColor: '#f59e0b', fillOpacity: 0.55 },
  parking: { color: '#3b82f6', weight: 1, fillColor: '#3b82f6', fillOpacity: 0.55 },
  offshore_wind_zone: { color: '#10b981', weight: 1, fillColor: '#10b981', fillOpacity: 0.35 },
  cv_detected_parking: { color: '#a855f7', weight: 1, fillColor: '#a855f7', fillOpacity: 0.55 },
}

function styleFor(feature) {
  const cat = feature.properties?.category
  return STYLES[cat] || { color: '#94a3b8', weight: 1, fillOpacity: 0.4 }
}

function onEachFeature(feature, layer) {
  const p = feature.properties || {}
  layer.bindTooltip(
    `<div class="text-xs">
       <div><b>${p.category}</b></div>
       <div>Area: ${p.area_m2?.toFixed?.(0) ?? '?'} m²</div>
       <div>Est. ${p.est_annual_mwh?.toFixed?.(1) ?? '?'} MWh/yr</div>
       <div>Suitability: ${((p.suitability_score ?? 0) * 100).toFixed(0)}%</div>
       <div class="text-slate-400 mt-1">${p.source ?? ''}</div>
     </div>`,
    { sticky: true }
  )
}

// Fits map to region bbox whenever it changes.
function FitToBbox({ bbox }) {
  const map = useMap()
  useEffect(() => {
    if (!bbox) return
    const [w, s, e, n] = bbox
    map.fitBounds([[s, w], [n, e]], { padding: [20, 20] })
  }, [bbox, map])
  return null
}

export default function ResultMap({ result }) {
  const center = result?.region?.centroid ?? [48.7519, -122.4787] // Bellingham
  const polygons = result?.polygons
  // GeoJSON layer in React-Leaflet caches its data; re-key on region to force refresh.
  const layerKey = result ? `${result.region.state}-${result.region.type}-${result.region.name}` : 'empty'

  return (
    <div className="h-full w-full">
      <MapContainer center={center} zoom={11} className="h-full w-full" scrollWheelZoom>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution='Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
          maxZoom={19}
        />
        {result && (
          <>
            <FitToBbox bbox={result.region.bbox} />
            <GeoJSON
              key={layerKey}
              data={polygons}
              style={styleFor}
              onEachFeature={onEachFeature}
            />
          </>
        )}
      </MapContainer>

      {/* Legend */}
      <div className="absolute bottom-3 right-3 bg-white/95 rounded-lg shadow px-3 py-2 text-xs space-y-1 z-[1000]">
        <div className="flex items-center gap-2"><span className="w-3 h-3 bg-rooftop rounded-sm" /> Rooftop</div>
        <div className="flex items-center gap-2"><span className="w-3 h-3 bg-parking rounded-sm" /> Parking</div>
        <div className="flex items-center gap-2"><span className="w-3 h-3 bg-offshore rounded-sm" /> Offshore wind</div>
      </div>
    </div>
  )
}
