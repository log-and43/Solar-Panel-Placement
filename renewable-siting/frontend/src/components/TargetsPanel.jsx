// Targets and toggles panel.
//
// Two of these are real and one is honest about being a placeholder:
//
//   - energyTargetGwh: a user-supplied override for "how much fossil to
//     offset." When set, the diagnostic recomputes the % covered against
//     this number instead of consumption.fossil_mwh_per_year. Real work.
//
//   - avoidAgriculture: UI present, but disabled with a "Phase 6" hint.
//     We have no agriculture data yet (NREL siting layers are Phase 6),
//     so a working checkbox would be a lie. Codex version had this active
//     as a multiplier in a fake model; ours surfaces it but doesn't fake.

export default function TargetsPanel({
  energyTargetGwh,
  setEnergyTargetGwh,
  avoidAgriculture,
  setAvoidAgriculture,
  includeOcean,
  setIncludeOcean,
  defaultFossilGwh,
}) {
  return (
    <section className="border border-line rounded-lg bg-panel p-4 space-y-3">
      <h2 className="text-sm font-semibold text-text">Target</h2>

      <label className="block">
        <span className="text-xs text-muted block mb-1">Fossil energy to offset</span>
        <div className="grid grid-cols-[1fr_auto] gap-2 items-center">
          <input
            type="number"
            min="0.1"
            step="0.1"
            value={energyTargetGwh ?? ''}
            placeholder={defaultFossilGwh != null ? defaultFossilGwh.toFixed(1) : '—'}
            onChange={(e) => setEnergyTargetGwh(e.target.value === '' ? null : Number(e.target.value))}
            className="border border-line rounded-md bg-[#111716] text-text min-h-9 px-2"
          />
          <span className="text-xs text-muted">GWh / year</span>
        </div>
        <span className="text-[11px] text-muted mt-1 block">
          Leave blank to use the region's full fossil generation.
        </span>
      </label>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={includeOcean}
          onChange={(e) => setIncludeOcean(e.target.checked)}
          className="w-4 h-4 accent-rooftop"
        />
        <span>Include offshore zones (coastal regions only)</span>
      </label>

      <label className="flex items-center gap-2 text-sm opacity-50 cursor-not-allowed" title="Will be wired up in Phase 6">
        <input
          type="checkbox"
          checked={avoidAgriculture}
          onChange={(e) => setAvoidAgriculture(e.target.checked)}
          disabled
          className="w-4 h-4 accent-rooftop"
        />
        <span>Avoid productive agriculture <span className="text-[11px] text-muted">(Phase 6)</span></span>
      </label>
    </section>
  )
}
