export default function Caveats({ caveats }) {
  if (!caveats || caveats.length === 0) return null
  return (
    <section className="border border-parking/40 rounded-lg bg-parking/10 p-4 text-sm">
      <h3 className="font-semibold text-parking mb-2">Limitations & caveats</h3>
      <ul className="list-disc pl-5 space-y-1.5 text-[#f7e7b8]">
        {caveats.map((c, i) => <li key={i} className="leading-snug text-xs">{c}</li>)}
      </ul>
    </section>
  )
}
