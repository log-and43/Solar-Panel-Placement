import { useState } from 'react'
import RegionPicker from './components/RegionPicker.jsx'
import ResultMap from './components/ResultMap.jsx'
import Diagnostic from './components/Diagnostic.jsx'
import Caveats from './components/Caveats.jsx'
import { analyze } from './lib/api.js'

export default function App() {
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

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

  return (
    <div className="h-full grid grid-cols-12 gap-4 p-4 bg-slate-100">
      {/* Left rail */}
      <aside className="col-span-4 xl:col-span-3 flex flex-col gap-4 overflow-y-auto">
        <header>
          <h1 className="text-xl font-bold text-slate-900">Renewable Siting Tool</h1>
          <p className="text-xs text-slate-500">Phase 1 — walking skeleton</p>
        </header>

        <RegionPicker onRun={handleRun} running={running} />

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-800 rounded p-3 text-sm">
            {error}
          </div>
        )}

        <Diagnostic result={result} />
        <Caveats caveats={result?.caveats} />
      </aside>

      {/* Map fills the rest */}
      <main className="col-span-8 xl:col-span-9 rounded-lg overflow-hidden shadow relative">
        <ResultMap result={result} />
      </main>
    </div>
  )
}
