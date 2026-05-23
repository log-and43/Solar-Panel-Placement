import { useState } from 'react'
import Brand from './components/Brand.jsx'
import RegionPicker from './components/RegionPicker.jsx'
import TargetsPanel from './components/TargetsPanel.jsx'
import LayersPanel from './components/LayersPanel.jsx'
import ResultMap from './components/ResultMap.jsx'
import Diagnostic from './components/Diagnostic.jsx'
import ModelNotes from './components/ModelNotes.jsx'
import Caveats from './components/Caveats.jsx'
import { analyze } from './lib/api.js'

const DEFAULT_LAYERS = new Set([
  'rooftop',
  'parking',
  'offshore_wind_zone',
  'cv_detected_parking',
])

export default function App() {
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  // New controls borrowed (and re-grounded) from the Codex frontend.
  const [energyTargetGwh, setEnergyTargetGwh] = useState(null)  // null = use region's full fossil
  const [includeOcean, setIncludeOcean] = useState(true)
  const [avoidAgriculture, setAvoidAgriculture] = useState(false)  // wired in Phase 6
  const [visibleLayers, setVisibleLayers] = useState(DEFAULT_LAYERS)

  // The "include ocean" toggle is a quick filter on top of the layer toggles.
  const effectiveVisible = includeOcean
    ? visibleLayers
    : new Set([...visibleLayers].filter(l => l !== 'offshore_wind_zone'))

  async function handleRun(req) {
    setRunning(true)
    setError(null)
    try {
      const data = await analyze(req)
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  const defaultFossilGwh = result
    ? result.consumption.fossil_mwh_per_year / 1000.0
    : null

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] bg-bg">
      {/* Sidebar */}
      <aside className="border-b lg:border-b-0 lg:border-r border-line bg-[#151b1a] p-5 flex flex-col gap-4 overflow-y-auto">
        <Brand />

        <RegionPicker onRun={handleRun} running={running} />

        <TargetsPanel
          energyTargetGwh={energyTargetGwh}
          setEnergyTargetGwh={setEnergyTargetGwh}
          includeOcean={includeOcean}
          setIncludeOcean={setIncludeOcean}
          avoidAgriculture={avoidAgriculture}
          setAvoidAgriculture={setAvoidAgriculture}
          defaultFossilGwh={defaultFossilGwh}
        />

        <LayersPanel
          visibleLayers={visibleLayers}
          setVisibleLayers={setVisibleLayers}
        />
      </aside>

      {/* Workspace */}
      <main className="grid grid-rows-[auto_minmax(420px,1fr)_auto_auto] gap-4 p-5">
        {/* Topbar */}
        <header className="flex justify-between items-center gap-5">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Continental U.S. renewable coverage model</p>
            <h2 className="text-2xl lg:text-3xl font-bold text-text mt-1">
              {result ? `${result.region.name}, ${result.region.state}` : 'Choose an area to begin'}
            </h2>
          </div>
          <div className="border border-line rounded-full px-3 py-2 inline-flex gap-2 items-center text-xs text-muted bg-panel">
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: running ? '#f5c45b' : error ? '#ee7b78' : '#67d391' }}
            />
            {running ? 'Analyzing…' : error ? 'Error' : result ? 'Ready' : 'Idle'}
          </div>
        </header>

        {/* Map */}
        <section className="min-h-[420px] rounded-lg border border-line overflow-hidden relative">
          <ResultMap result={result} visibleLayers={effectiveVisible} />
          {error && (
            <div className="absolute top-3 right-3 max-w-xs bg-rose/10 border border-rose/40 text-rose text-xs rounded-md px-3 py-2 z-[600]">
              {error}
            </div>
          )}
        </section>

        {/* Diagnostic strip */}
        <Diagnostic result={result} energyTargetGwh={energyTargetGwh} />

        {/* Model notes + caveats side by side */}
        <div className="grid lg:grid-cols-[2fr_1fr] gap-4">
          <ModelNotes result={result} />
          <Caveats caveats={result?.caveats} />
        </div>
      </main>
    </div>
  )
}
