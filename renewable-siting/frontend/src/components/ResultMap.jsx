import { useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'

const STYLES = {
  rooftop:             { color: '#67d391', weight: 1, fillColor: '#67d391', fillOpacity: 0.55 },
  parking:             { color: '#f5c45b', weight: 1, fillColor: '#f5c45b', fillOpacity: 0.55 },
  offshore_wind_zone:  { color: '#6ea2ff', weight: 1.5, fillColor: '#6ea2ff', fillOpacity: 0.32, dashArray: '6 4' },
  cv_detected_parking: { color: '#53c7df', weight: 1, fillColor: '#53c7df', fillOpacity: 0.55 },
}

function styleFor(feature) {
  const cat = feature.properties?.category
  return STYLES[cat] || { color: '#94a3b8', weight: 1, fillOpacity: 0.4 }
}

function onEachFeature(feature, layer) {
  const p = feature.properties || {}
  layer.bindTooltip(
    `<div style="font-size:11px;">
       <div><b style="text-transform:capitalize">${(p.category || '').replace(/_/g, ' ')}</b></div>
       <div>Area: ${p.area_m2?.toFixed?.(0) ?? '?'} m²</div>
       <div>Est. ${p.est_annual_mwh?.toFixed?.(2) ?? '?'} MWh/yr</div>
       <div>Suitability: ${((p.suitability_score ?? 0) * 100).toFixed(0)}%</div>
     </div>`,
    { sticky: true }
  )
}

function FitToBbox({ bbox }) {
  const map = useMap()
  useEffect(() => {
    if (!bbox) return
    const [w, s, e, n] = bbox
    map.fitBounds([[s, w], [n, e]], { padding: [20, 20] })
  }, [bbox, map])
  return null
}

export default function ResultMap({ result, visibleLayers }) {
  const center = result?.region?.centroid ?? [39.5, -98.35]

  // Filter polygons by the user's layer toggles.
  const filteredPolygons = useMemo(() => {
    if (!result?.polygons) return null
    return {
      ...result.polygons,
      features: result.polygons.features.filter(f =>
        visibleLayers.has(f.properties.category)
      ),
    }
  }, [result, visibleLayers])

  // GeoJSON layer in React-Leaflet caches its data; re-key on region+visibility.
  const layerKey = result
    ? `${result.region.state}-${result.region.type}-${result.region.name}-${[...visibleLayers].sort().join(',')}`
    : 'empty'

  return (
    <div className="h-full w-full relative">
      <MapContainer center={center} zoom={11} className="h-full w-full" scrollWheelZoom>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution='Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
          maxZoom={19}
        />
        {result && filteredPolygons && (
          <>
            <FitToBbox bbox={result.region.bbox} />
            <GeoJSON
              key={layerKey}
              data={filteredPolygons}
              style={styleFor}
              onEachFeature={onEachFeature}
            />
          </>
        )}
      </MapContainer>

      {/* Dark legend, bottom-left */}
      <div className="absolute bottom-3 left-3 bg-panel/95 border border-line rounded-md px-3 py-2 text-[11px] space-y-1 z-[500]">
        <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-sm bg-rooftop" /> Rooftop</div>
        <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-sm bg-parking" /> Parking</div>
        <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-sm bg-wind" /> Offshore wind</div>
      </div>
    </div>
  )
}
