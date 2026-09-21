"use client";

// Confidence as three discrete segments, not a percentage bar.
//
// This is a Ground Rule 3 decision: the backend emits a TIER, and a smooth
// 0-100 bar would invent a precision the tier does not have. Three notches
// say "one of three" honestly. The tier word is always rendered too, so the
// meter is reinforcement rather than the only carrier.
//
// P2.3 (`R-JUDGE-4`) — the meter now expands to show *how* the tier was
// arrived at. Every `Confidence` object has carried a `rationale` string
// since Phase 1 ("Worst of 4 upstream inputs: geospatial MEDIUM (IMBL proxy
// boundary, not treaty line)") and it was thrown away at this boundary, so
// the single most-asked judge question — "why MEDIUM?" — had no answer on
// screen. The derivation is deterministic arithmetic (risk_assessment's
// compute_confidence takes the worst tier, never an average), which is the
// part worth showing: it is a rule, not a model's opinion.
import { useState } from "react";
import { ChevronDown, Info } from "lucide-react";
import { confidenceClass, confidenceLabel, type ConfidenceTier } from "./Badge";

const FILLED: Record<ConfidenceTier, number> = { LOW_DATA: 1, MEDIUM: 2, HIGH: 3 };

// The rationale strings are composed backend-side and can be long. Splitting
// on the conventional separators keeps the first clause readable without the
// frontend parsing a format the backend never promised — anything unsplittable
// renders as a single line, which is the honest fallback.
function rationaleLines(rationale: string): string[] {
  return (rationale ?? "")
    .split(/\s*—\s*|\s*;\s*|\s*\[score/)
    .map((part) => part.trim())
    .filter(Boolean);
}

// One input to the tier: an agent whose result Reporting took the worst of.
// Read straight off the backend's own `confidence_inputs` (graph.reporting_run),
// so nothing here is re-derived in the browser.
export type ConfidenceInput = {
  agent_name: string;
  tier: ConfidenceTier;
  rationale: string;
};

export function ConfidenceMeter({
  tier,
  inputs,
}: {
  tier: ConfidenceTier;
  // Why this tier: the inputs the backend took the worst of. Absent on answers
  // cached before P2.3, and on refusals/distress responses that never reach
  // Reporting — the meter then renders exactly as it did before rather than
  // showing an empty drawer.
  inputs?: ConfidenceInput[] | null;
}) {
  const [open, setOpen] = useState(false);
  const filled = FILLED[tier];
  const cls = confidenceClass(tier);

  const rows = inputs ?? [];
  const hasDetail = rows.length > 0;
  // The inputs that SET the tier. The DLC's own example names exactly this
  // one: "MEDIUM — worst of 4 inputs: geospatial MEDIUM (IMBL proxy boundary,
  // not treaty line)". When every input is HIGH there is no single culprit and
  // the line says so instead of inventing one.
  const setters = rows.filter((r) => r.tier === tier);
  const summary = hasDetail
    ? tier === "HIGH"
      ? `${confidenceLabel(tier)} — all ${rows.length} inputs are High`
      : `${confidenceLabel(tier)} — worst of ${rows.length} inputs: ${setters
          .map((r) => `${r.agent_name.replace(/_/g, " ")} ${confidenceLabel(r.tier)}`)
          .join(", ")}`
    : null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="flex gap-1" role="img" aria-label={`Confidence: ${confidenceLabel(tier)} (${filled} of 3)`}>
          {[1, 2, 3].map((n) => (
            <span
              key={n}
              className={`h-1 w-5 rounded-full ${n <= filled ? `bg-current ${cls}` : "bg-hairline"}`}
            />
          ))}
        </div>
        <span className={`text-[11px] font-medium ${cls}`}>{confidenceLabel(tier)} confidence</span>

        {hasDetail && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="inline-flex items-center gap-1 rounded text-[11px] text-ink-dim transition-colors hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <Info className="size-3" aria-hidden="true" />
            <span>{open ? "Hide" : "Why?"}</span>
            <ChevronDown
              className={`size-3 transition-transform ${open ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </button>
        )}
      </div>

      {open && hasDetail && (
        <div className="flex flex-col gap-2 rounded-lg border border-hairline/60 bg-shelf-1/40 p-2.5 text-[11px] text-ink-muted">
          <p className="font-medium text-ink">{summary}</p>
          <p className="text-ink-dim">
            The tier is the <span className="font-medium text-ink">worst</span> of its inputs — never an
            average, so one weak source cannot be offset by three strong ones. It is a rule, not a
            model&apos;s opinion.
          </p>

          <ul className="flex flex-col gap-1.5 border-t border-hairline/50 pt-2">
            {rows.map((row) => (
              <li key={row.agent_name} className="flex flex-col gap-0.5">
                <span className="flex items-center gap-1.5">
                  <span className={`font-mono text-[10px] font-semibold uppercase ${confidenceClass(row.tier)}`}>
                    {row.tier === "LOW_DATA" ? "LOW" : row.tier}
                  </span>
                  <span className="font-medium text-ink-muted">{row.agent_name.replace(/_/g, " ")}</span>
                  {row.tier === tier && tier !== "HIGH" && (
                    <span className="rounded bg-shelf-3 px-1 font-mono text-[9px] uppercase text-ink-dim">
                      sets the tier
                    </span>
                  )}
                </span>
                {rationaleLines(row.rationale).length > 0 && (
                  <span className="pl-1 text-ink-dim">{rationaleLines(row.rationale)[0]}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
