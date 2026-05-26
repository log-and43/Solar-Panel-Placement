# Post-Codex Phase 3

Second iteration in the parallel-implementation workflow. This phase
adopts two things from the teammate's Codex-built Phase 3:

1. **Multi-env-var support** for the NREL API key. `PVWATTS_API_KEY`,
   `NREL_API_KEY`, and `ROCKIES_API_KEY` are all accepted, with
   `PVWATTS_API_KEY` winning when multiple are set.
2. **"Data Quality" UI section** combining the Generation Mix bar and
   the Caveats list in a dedicated panel between the diagnostic strip
   and the model notes. The mix bar previously lived inside ModelNotes
   (cluttering it); caveats were in a separate amber panel.

The backend PVWatts logic (one real call per polygon, with per-category
defaults) is unchanged — this phase is about polish and configuration,
not core estimation.

## What was adopted

| From Codex | Where it lives now |
|------------|---------------------|
| `NREL_API_KEY` and `ROCKIES_API_KEY` as accepted env var names | `backend/app/pvwatts.py`, `backend/.env.example` |
| "Data Quality" section grouping mix + caveats | `frontend/src/components/DataQuality.jsx` |
| Rounded-pill mix bar styling (full radius, with state-name source line below) | `DataQuality.jsx` |

## What was deliberately NOT adopted

- **Their per-location-not-per-polygon PVWatts call.** Adopting this
  would be a regression. The whole point of Phase 3 is that each polygon
  gets a real generation estimate sized to its actual area, with rooftop
  vs parking using different physical params (tilt, losses, packing
  factor, array type). Their version calls PVWatts once for the region
  centroid and uses that single yield factor to scale all template
  polygons — losing the per-polygon physical realism.
- **Browser-side `localStorage` cache.** Our backend cache already
  dedupes by lat/lon/system-size, and adding a frontend cache would
  complicate cache invalidation when polygons or PVWatts defaults change.
- **The fake `× 0.45` / `× 0.32` / `× 0.36` template polygon multipliers**
  that masquerade as "rooftop / parking / ocean shares." These are
  the analytical equivalent of magic numbers and don't survive review.

## What was kept from ours

- Per-polygon PVWatts calls (~70 per region, all cached)
- Per-category tilt / array_type / losses / packing-factor defaults
- Cache key that includes system size, so a small house and big warehouse
  at the same lat/lon don't share an answer
- Soft fallback to the Phase 1 approximation when no key is configured
  or when a PVWatts call fails mid-run
- 10 original Phase 3 tests (now 15 with the multi-env-var additions)
- The frozen API contract

## API key precedence

When `load_api_key()` is called:

1. **OS environment variables first**, in this order:
   - `PVWATTS_API_KEY` (canonical for this project)
   - `NREL_API_KEY` (matches NREL's broader API ecosystem)
   - `ROCKIES_API_KEY` (legacy NREL naming, still in some examples)
2. **Then the `.env` file**, same precedence order.

The canonical name wins if multiple are set. This means a teammate can
have `NREL_API_KEY` set globally for other tools without it conflicting
with a project-specific `PVWATTS_API_KEY`.

## Tests

15 Phase 3 tests now, up from 10. New tests:

- `test_api_key_loaded_from_any_known_env_var[PVWATTS_API_KEY]`
- `test_api_key_loaded_from_any_known_env_var[NREL_API_KEY]`
- `test_api_key_loaded_from_any_known_env_var[ROCKIES_API_KEY]`
- `test_canonical_name_wins_over_aliases`
- `test_api_key_loaded_from_dotenv_with_alias`

Total: 23 passing, 9 skipped pending Phase 2 data or live PVWatts.

## Honest acknowledgment

The Codex Phase 3 implementation has a polished UI but materially
weaker analytical claims than ours. Their PVWatts use is "one real
number multiplied by hardcoded coverage percentages on fixed-position
template polygons." Ours is "real PVWatts for each polygon, with
physical sizing." Both technically integrate PVWatts; only one supports
the claim "every polygon's generation estimate is grounded in real solar
resource data."

This is worth being clear about in the writeup: the project's analytical
backbone is our backend; the project's visual polish came partly from
Codex's frontend taste. Both contributions are real.

Next round of feeding-off-each-other comes with Phase 4 (real polygon
sources from Microsoft Building Footprints + OpenStreetMap).
