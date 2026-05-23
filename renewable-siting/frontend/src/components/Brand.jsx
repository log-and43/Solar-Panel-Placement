// Small "SP" mark used in the sidebar header. Inspired by the Codex version
// — gradient block, monogram, and a tagline to give the project a name.
export default function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div
        className="w-10 h-10 rounded-lg grid place-items-center font-extrabold text-[#09110d]"
        style={{ background: 'linear-gradient(135deg, #67d391, #f5c45b)' }}
      >
        SP
      </div>
      <div>
        <h1 className="text-base font-semibold text-text leading-tight">Solar Placement</h1>
        <p className="text-xs text-muted">Renewable siting planner</p>
      </div>
    </div>
  )
}
