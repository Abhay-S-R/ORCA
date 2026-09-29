"use client";

// Phase 2's "the conversation that visibly reasons" surfaces, kept in one
// file because they are one idea in four parts: show the decisions the
// pipeline already makes instead of only their results.
//
//   RoutingLine        P2.7  (`R-JUDGE-3`) — which intents matched, which tier
//                            decided, how many agents that dispatched, and
//                            what it cost in time and provider calls.
//   ReconciliationPanel P2.4 (`R-PS-5`)    — where two sources covering the
//                            same variable were compared, and what happened.
//   InheritedChips     P2.9  (`R-PS-3`)    — what this answer took from earlier
//                            in the conversation, each one removable.
//   SkippedNotice      P2.12 (orca_final §4.1) — work that was deliberately
//                            not done, and why.
//
// None of these fetch anything or compute a number. Every value is one the
// backend already decided; rendering it is the whole point.
import { AlertTriangle, CheckCheck, GitBranch, Timer, X } from "lucide-react";
import type { InheritedValue, Reconciliation, RoutingSummary, FinalResponse } from "./useAskThread";
import { formatAgentLabel } from "../components/AgentPill";

// The routing tier, in words a judge reads rather than an identifier.
const TIER_LABEL: Record<string, string> = {
  tier1_rules: "keyword rules",
  tier2_embeddings: "sentence embeddings",
  "tier2_embeddings+tier3_confirmed": "sentence embeddings, confirmed",
  "tier2_embeddings+tier3_disagreed": "embeddings + model, both kept",
  tier3_llm: "model classifier",
  carried_from_previous_turn: "continued from the previous question",
  no_match: "no rule matched",
};

function humanIntent(row: string): string {
  return row
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function RoutingLine({
  routing,
  latency,
  llmCalls,
  failedAttempts,
}: {
  routing: RoutingSummary;
  latency?: FinalResponse["latency"];
  llmCalls?: number;
  failedAttempts?: number;
}) {
  const tier = routing.routing_tier ? TIER_LABEL[routing.routing_tier] ?? routing.routing_tier : null;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-0.5 text-[11px] text-ink-dim">
      <span className="inline-flex items-center gap-1.5">
        <GitBranch className="size-3 shrink-0 text-accent" aria-hidden="true" />
        <span>
          <span className="font-medium text-ink-muted">
            {routing.matched_intent_rows.map(humanIntent).join(" + ")}
          </span>
          {tier && <span className="text-ink-dim"> · {tier}</span>}
          {" → "}
          {routing.agents_dispatched} {routing.agents_dispatched === 1 ? "agent" : "agents"} dispatched
        </span>
      </span>

      {/* P2.10 — `agent_time_ms` is a SUM of spans, not wall clock: the three
          specialists run in parallel, so it overstates elapsed time rather
          than flattering it. Labelled as agent time for exactly that reason. */}
      {latency && latency.agent_time_ms > 0 && (
        <span className="inline-flex items-center gap-1.5" title="Sum of every agent's own run time. The specialists run in parallel, so elapsed time is less than this.">
          <Timer className="size-3 shrink-0" aria-hidden="true" />
          <span className="font-mono">{(latency.agent_time_ms / 1000).toFixed(1)}s agent time</span>
          {latency.slowest && (
            <span className="text-ink-dim/80">
              · slowest {formatAgentLabel(latency.slowest.agent_name)} {Math.round(latency.slowest.latency_ms)}ms
            </span>
          )}
        </span>
      )}

      {llmCalls != null && (
        <span className="font-mono" title="Provider calls that returned an answer for this query — measured, not estimated. Failed attempts on a model that was down are counted separately.">
          {llmCalls} LLM {llmCalls === 1 ? "call" : "calls"}
          {!!failedAttempts && (
            <span className="text-ink-dim/80">
              {" "}· {failedAttempts} failed {failedAttempts === 1 ? "attempt" : "attempts"}
            </span>
          )}
        </span>
      )}
    </div>
  );
}

export function ReconciliationPanel({ rows }: { rows: Reconciliation[] }) {
  if (rows.length === 0) return null;
  const diverged = rows.filter((r) => r.status === "diverged");

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-hairline/60 bg-shelf-1/40 p-3">
      <span className="flex items-center gap-1.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
        {diverged.length > 0 ? (
          <AlertTriangle className="size-3 text-caution" aria-hidden="true" />
        ) : (
          <CheckCheck className="size-3 text-go" aria-hidden="true" />
        )}
        Cross-source check
      </span>

      <div className="flex flex-col gap-1.5">
        {rows.map((row) => (
          <div key={row.variable} className="flex flex-col gap-0.5">
            <div className="flex flex-wrap items-baseline gap-x-2 text-[11px]">
              <span className="font-medium text-ink-muted">{row.label}</span>
              <span className="font-mono text-ink-dim">
                {String(row.primary.value)}
                {row.unit} vs {String(row.secondary.value)}
                {row.unit}
              </span>
              <span
                className={`rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide ${
                  row.status === "diverged"
                    ? "bg-caution/15 text-caution"
                    : row.status === "not_comparable"
                    ? "bg-shelf-3 text-ink-dim"
                    : "bg-go/10 text-go"
                }`}
              >
                {row.status === "not_comparable" ? "not comparable" : row.status}
              </span>
            </div>
            {/* The agreements get no sentence — two feeds quietly matching is
                not news, and it would bury the one line that is. */}
            {row.status !== "agree" && (
              <p className="text-[11px] leading-snug text-ink-muted">{row.statement}</p>
            )}
            <p className="font-mono text-[10px] text-ink-dim">
              {row.primary.source} · {row.secondary.source}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

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
