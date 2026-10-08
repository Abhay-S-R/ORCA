"use client";

// Phase 2's "the conversation that visibly reasons" surfaces, kept in one
// file because they are one idea in two parts: show the decisions the
// pipeline already makes instead of only their results.
//
//   (RoutingLine and ReconciliationPanel were removed from the card on
//   2026-10-08 at the user's request: the routing summary and the
//   cross-source check are still computed and on the wire, just not shown.)
//   InheritedChips     P2.9  (`R-PS-3`)    — what this answer took from earlier
//                            in the conversation, each one removable.
//   SkippedNotice      P2.12 (orca_final §4.1) — work that was deliberately
//                            not done, and why.
//
// None of these fetch anything or compute a number. Every value is one the
// backend already decided; rendering it is the whole point.
import { X } from "lucide-react";
import type { InheritedValue } from "./useAskThread";
import { formatAgentLabel } from "../components/AgentPill";

export function InheritedChips({
  inherited,
  onRemove,
}: {
  inherited: InheritedValue[];
  onRemove: (value: InheritedValue) => void;
}) {
  if (inherited.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
        Carried over
      </span>
      {inherited.map((value) => (
        <span
          key={value.field}
          title={value.detail}
          className="inline-flex items-center gap-1 rounded-lg border border-hairline/60 bg-shelf-2/50 py-0.5 pl-2 pr-1 text-[11px] text-ink-muted"
        >
          <span className="text-ink-dim">{value.label}:</span>
          <span className="font-medium text-ink">{value.value}</span>
          <button
            type="button"
            onClick={() => onRemove(value)}
            aria-label={`Don't carry over ${value.label.toLowerCase()} ${value.value}`}
            className="rounded p-0.5 text-ink-dim transition-colors hover:bg-shelf-3 hover:text-no-go focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent"
          >
            <X className="size-3" aria-hidden="true" />
          </button>
        </span>
      ))}
    </div>
  );
}

export function SkippedNotice({
  skipped,
}: {
  skipped: { agent_name: string; status: string; reason: string }[];
}) {
  if (skipped.length === 0) return null;

  return (
    <div className="flex flex-col gap-1 rounded-lg border border-dashed border-hairline/60 bg-shelf-1/30 p-2.5">
      <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
        Not run
      </span>
      {skipped.map((s) => (
        <p key={s.agent_name} className="text-[11px] leading-snug text-ink-muted">
          <span className="font-medium text-ink-muted">{formatAgentLabel(s.agent_name)}</span>
          <span className="text-ink-dim"> — {s.reason}</span>
        </p>
      ))}
    </div>
  );
}
