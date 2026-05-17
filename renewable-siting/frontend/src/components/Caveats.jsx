export default function Caveats({ caveats }) {
  if (!caveats || caveats.length === 0) return null
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
      <h3 className="font-semibold text-amber-900 mb-1">Limitations & caveats</h3>
      <ul className="list-disc pl-5 space-y-1 text-amber-900/90">
        {caveats.map((c, i) => <li key={i}>{c}</li>)}
      </ul>
    </div>
  )
}
