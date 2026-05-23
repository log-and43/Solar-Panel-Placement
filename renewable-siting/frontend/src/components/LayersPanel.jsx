// Map layer toggles. Per-category checkboxes that filter what's rendered.
// Pure frontend; doesn't talk to the backend.

const LAYERS = [
  { key: 'rooftop',            label: 'Rooftops',           swatch: 'bg-rooftop' },
  { key: 'parking',            label: 'Parking lots',       swatch: 'bg-parking' },
  { key: 'offshore_wind_zone', label: 'Offshore wind',      swatch: 'bg-wind' },
  { key: 'cv_detected_parking',label: 'CV-detected parking',swatch: 'bg-ocean', phase: 5 },
]

export default function LayersPanel({ visibleLayers, setVisibleLayers }) {
  function toggle(key) {
    const next = new Set(visibleLayers)
    next.has(key) ? next.delete(key) : next.add(key)
    setVisibleLayers(next)
  }
  return (
    <section className="border border-line rounded-lg bg-panel p-4 space-y-2">
      <h2 className="text-sm font-semibold text-text">Layers</h2>
      {LAYERS.map((l) => (
        <label key={l.key} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={visibleLayers.has(l.key)}
            onChange={() => toggle(l.key)}
            className="w-4 h-4 accent-rooftop"
          />
          <span className={`w-2.5 h-2.5 rounded-sm ${l.swatch}`} />
          <span className="flex-1">{l.label}</span>
          {l.phase && <span className="text-[10px] text-muted">P{l.phase}</span>}
        </label>
      ))}
    </section>
  )
}
