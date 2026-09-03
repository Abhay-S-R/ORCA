"use client";

// Source-selection narration (Phase 2 plan §4 D2, differentiator 4).
//
// Agent 3 decides which dataset answers a question and produces a
// human-readable sentence saying why — "MOSDAC NRT SST chosen over Copernicus
// reanalysis: 6 h old vs ~5 d, same Tier-1 authority — freshness decided it."
// The plan is explicit that this is a first-class output rendered ON the
// answer card, not buried in the trace. This is that surface.
import { GitBranch } from "lucide-react";

export type SourceSelection = {
  data_type: string;
  chosen: string;
  chosen_dataset: string;
  narrative: string;
  considered?: string[];
  fallback_chain?: string[];
};

export function SourceNarration({ selection }: { selection: SourceSelection | null | undefined }) {
  if (!selection) return null;
  return (
    <div className="rounded-sm border border-hairline bg-shelf-1/50 p-2.5 text-xs">
      <p className="flex items-start gap-1.5 text-ink-muted">
        <GitBranch className="mt-0.5 size-3.5 shrink-0 text-ink-dim" aria-hidden="true" />
        <span>{selection.narrative}</span>
      </p>
      {selection.considered && selection.considered.length > 1 && (
        <p className="mt-1.5 pl-5 text-[11px] text-ink-dim">
          Considered: {selection.considered.join(" → ")}
        </p>
      )}
    </div>
  );
}
