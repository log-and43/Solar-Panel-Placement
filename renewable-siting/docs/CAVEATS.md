# Caveats and Honest Limitations

This is a living document. Every phase adds caveats; none are removed.
The frontend reads from a subset of this list and shows them to users.

## Always-true caveats (shown in UI)

1. **Consumption at sub-state level is extrapolated.** We scale state totals
   by population share. Real city/county consumption depends heavily on
   industrial load, climate, and housing stock — none of which we model.

2. **Generation estimates are technical, not economic or permitted.** A
   building footprint with 1000 m² of roof does not mean 1000 m² of usable
   panel area. Shading, structural load, electrical capacity, HVAC
   equipment, fire-code setbacks, and zoning all reduce real-world capacity,
   often by 30–60%.

3. **Cost and payback figures use national averages.** Local labor rates,
   utility interconnection fees, permitting costs, and incentives can shift
   payback by years in either direction.

4. **The renewable mix recommendation ignores transmission and policy.** A
   region might have excellent wind resource and no way to connect it to
   the grid. Real siting decisions involve interconnection queues,
   transmission upgrades, and state RPS rules we do not model.

## Phase-specific caveats

### Phase 1 (current)
- All numbers are hardcoded for demo. **Do not interpret any output as real.**

### Phase 2 (planned)
- eGRID is annual and lagging. The most recent file may be 1–2 years old.
- EIA SEDS state-level consumption mixes residential, commercial, and
  industrial. We don't separate them.

### Phase 4 (planned)
- Microsoft Building Footprints has coverage gaps for very recent construction.
- OSM parking coverage is uneven; rural counties often have very little.

### Phase 5 (planned, optional)
- SAM is a foundation model, not trained on aerial imagery specifically.
  False positives and false negatives are real.

### Phase 6 (planned)
- Offshore wind "potential" assumes water depth and distance-to-shore
  thresholds for fixed-bottom turbines. Floating offshore is largely
  pre-commercial. We do not flag this distinction in the UI yet.
- We do not model environmental review, viewshed objections, fishing
  industry conflicts, or military/coast-guard exclusion zones.

## What we explicitly do NOT claim

- That this tool's outputs are sufficient for any real siting decision.
- That the "ML" component (SAM-based segmentation, if implemented) is
  trained or validated for this purpose.
- That ocean-surface solar PV is currently a deployed technology at scale.
  (Floating PV on inland water is. Offshore floating PV in seawater is mostly
  experimental, which is why we recommend offshore wind for coastal regions.)
