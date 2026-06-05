// Inline provenance blurb shown under a displayed value.
//
// Two lines, both intentionally discreet (small, muted) so they inform
// without dominating:
//   Source: <where the number came from>
//   <formula in readable math notation, monospace>
//
// Urban planners (the audience that asked for this) need provenance to be
// obvious and honest. For values that are still placeholders, pass a source
// that SAYS SO — e.g. "Placeholder — national averages, not site-specific".
// Never label a provisional number as if it came from an authoritative
// dataset; that's the one thing this component exists to prevent.

export default function SourceNote({ source, formula }) {
  if (!source && !formula) return null
  return (
    <div className="mt-1.5 space-y-0.5 border-t border-line pt-1.5">
      {source && (
        <div className="text-[11px] text-muted leading-snug">
          <span className="font-semibold text-text/70">Source:</span> {source}
        </div>
      )}
      {formula && (
        <div className="text-[11px] text-muted font-mono leading-snug">
          {formula}
        </div>
      )}
    </div>
  )
}
