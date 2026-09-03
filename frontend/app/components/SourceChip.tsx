"use client";

// "Every number on screen carries dataset + timestamp" (exit criterion 4).
// The chip is the compact form; ProvenancePopover is the one-tap expansion
// the plan asks for, so provenance is always one interaction away and never
// more than one.
import { useState } from "react";
import { Database } from "lucide-react";
import { confidenceClass, confidenceLabel, type ConfidenceTier } from "./Badge";

export function SourceChip({
  dataset,
  acquisitionTimestamp,
  confidenceTier,
  detail,
  freshnessMinutes,
  sourceSelection,
}: {
  dataset: string;
  acquisitionTimestamp: string;
  confidenceTier?: ConfidenceTier;
  detail?: string;
  // Phase 2 D2: the click-through upgrade (differentiator 3) also carries
  // freshness and — when Agent 3 chose between candidates — why this source.
  freshnessMinutes?: number;
  sourceSelection?: { narrative: string; considered?: string[] };
}) {
  const [open, setOpen] = useState(false);
  const when = formatTimestamp(acquisitionTimestamp);

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-sm border border-hairline bg-shelf-1/60 px-1.5 py-0.5 text-[11px] text-ink-dim transition-colors hover:border-hairline-strong hover:text-ink-muted"
      >
        <Database className="size-3 shrink-0" aria-hidden="true" />
        <span className="text-ink-muted">{dataset}</span>
        <time dateTime={acquisitionTimestamp} data-readout className="text-[11px]">
          {when}
        </time>
        {confidenceTier && (
          <span className={confidenceClass(confidenceTier)}>{confidenceLabel(confidenceTier)}</span>
        )}
      </button>

      {open && (
        <ProvenancePopover
          dataset={dataset}
          acquisitionTimestamp={acquisitionTimestamp}
          confidenceTier={confidenceTier}
          detail={detail}
          freshnessMinutes={freshnessMinutes}
          sourceSelection={sourceSelection}
          onClose={() => setOpen(false)}
        />
      )}
    </span>
  );
}

function freshnessLabel(minutes: number): string {
  if (minutes <= 0) return "static reference — does not go stale";
  if (minutes < 90) return `${minutes} min old`;
  if (minutes < 2880) return `~${Math.round(minutes / 60)} h old`;
  return `~${Math.round(minutes / 1440)} d old`;
}

export function ProvenancePopover({
  dataset,
  acquisitionTimestamp,
  confidenceTier,
  detail,
  freshnessMinutes,
  sourceSelection,
  onClose,
}: {
  dataset: string;
  acquisitionTimestamp: string;
  confidenceTier?: ConfidenceTier;
  detail?: string;
  freshnessMinutes?: number;
  sourceSelection?: { narrative: string; considered?: string[] };
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-label={`Provenance for ${dataset}`}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
      className="glass absolute bottom-full left-0 z-30 mb-1.5 w-72 rounded-md p-3 text-xs shadow-lg shadow-black/50"
    >
      <p className="font-semibold text-ink">{dataset}</p>
      <dl className="mt-2 space-y-1.5">
        <div className="flex justify-between gap-3">
          <dt className="text-ink-dim">Acquired</dt>
          <dd data-readout className="text-ink-muted">
            {formatTimestamp(acquisitionTimestamp)}
          </dd>
        </div>
        {typeof freshnessMinutes === "number" && (
          <div className="flex justify-between gap-3">
            <dt className="text-ink-dim">Freshness</dt>
            <dd data-readout className="text-ink-muted">{freshnessLabel(freshnessMinutes)}</dd>
          </div>
        )}
        {confidenceTier && (
          <div className="flex justify-between gap-3">
            <dt className="text-ink-dim">Confidence</dt>
            <dd className={confidenceClass(confidenceTier)}>{confidenceLabel(confidenceTier)}</dd>
          </div>
        )}
      </dl>
      {sourceSelection && (
        <p className="mt-2 border-t border-hairline pt-2 text-ink-dim">
          <span className="font-medium text-ink-muted">Why this source: </span>
          {sourceSelection.narrative}
        </p>
      )}
      {detail && <p className="mt-2 border-t border-hairline pt-2 text-ink-dim">{detail}</p>}
    </div>
  );
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // Fixed locale and zone, never the visitor's: the whole product reads in
  // UTC, and a locale-dependent string would also break hydration.
  return `${d.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  })} UTC`;
}
