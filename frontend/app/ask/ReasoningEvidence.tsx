"use client";

// Phase 2's "the conversation that visibly reasons" surfaces, kept in one
// file because they are one idea in two parts: show the decisions the
// pipeline already makes instead of only their results.
//
//   (RoutingLine and ReconciliationPanel were removed from the card on
//   2026-10-08 at the user's request: the routing summary and the
//   cross-source check are still computed and on the wire, just not shown.)
//   (InheritedChips, the removable "Carried over" chips of P2.9, were removed on 2026-10-10 at the user's request.)
//   SkippedNotice      P2.12 (orca_final §4.1) — work that was deliberately
//                            not done, and why.
//
// None of these fetch anything or compute a number. Every value is one the
// backend already decided; rendering it is the whole point.
import { formatAgentLabel } from "../components/AgentPill";

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
