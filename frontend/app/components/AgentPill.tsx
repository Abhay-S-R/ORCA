"use client";

// The live agent activity strip (differentiator 1 — "what makes the UI
// visibly agentic", §4.5). Up to ten agents execute per query; this is how a
// user sees that happening instead of watching a spinner.
//
// No per-agent glyph and no static connector arrow: status reads through
// colour, text and motion, and the link between two pills is itself the
// tell — a current flowing toward whichever agent is in flight, the same
// "water finding its way downstream" language the chart's own
// FlowFieldCanvas uses for real ocean currents, just scaled down to a 12px
// channel. A solid line once the flow has arrived, a quiet dashed one where
// it hasn't reached yet.
import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, Check, Loader2, X } from "lucide-react";
import { confidenceLabel, type ConfidenceTier } from "./Badge";

const CONFIDENCE_FILL: Record<ConfidenceTier, string> = {
  HIGH: "bg-[color-mix(in_oklab,var(--color-confidence-high)_85%,black)]",
  MEDIUM: "bg-[color-mix(in_oklab,var(--color-confidence-medium)_85%,black)]",
  LOW_DATA: "bg-[color-mix(in_oklab,var(--color-confidence-low)_85%,black)]",
};

// Mirrors orca/contracts.py's AgentResult.status, plus the frontend-only
// "pending"/"running" the strip infers. "cancelled" (P2.12) is distinct from
// "skipped" (P2.7) on purpose: skipped is "the plan never asked for this",
// decided before anything ran; cancelled is "this was pending and a hard
// constraint made it pointless", decided mid-flight.
export type AgentStatus =
  | "pending" | "running" | "ok" | "degraded" | "failed" | "skipped" | "cancelled";

export const AGENT_REGISTRY: Record<string, { label: string; shortLabel: string }> = {
  distress: { label: "Distress Check", shortLabel: "Distress" },
  distresscheck: { label: "Distress Check", shortLabel: "Distress" },
  distress_check: { label: "Distress Check", shortLabel: "Distress" },
  languageingress: { label: "Language Ingress", shortLabel: "Ingress" },
  language_ingress: { label: "Language Ingress", shortLabel: "Ingress" },
  planning: { label: "Planning", shortLabel: "Planning" },
  // Agent 3, a real node since P2.6 rather than a field smuggled out on
  // Ocean Analytics' output.
  marinedatadiscovery: { label: "Marine Data Discovery", shortLabel: "Discovery" },
  marine_data_discovery: { label: "Marine Data Discovery", shortLabel: "Discovery" },
  discovery: { label: "Marine Data Discovery", shortLabel: "Discovery" },
  weatherintelligence: { label: "Weather Intel", shortLabel: "Weather" },
  weather_intelligence: { label: "Weather Intel", shortLabel: "Weather" },
  weather: { label: "Weather Intel", shortLabel: "Weather" },
  geospatial: { label: "Geospatial", shortLabel: "Geospatial" },
  oceananalytics: { label: "Ocean Analytics", shortLabel: "Ocean" },
  ocean_analytics: { label: "Ocean Analytics", shortLabel: "Ocean" },
  ocean: { label: "Ocean Analytics", shortLabel: "Ocean" },
  riskassessment: { label: "Risk Assessment", shortLabel: "Risk" },
  risk_assessment: { label: "Risk Assessment", shortLabel: "Risk" },
  risk: { label: "Risk Assessment", shortLabel: "Risk" },
  visualization: { label: "Visualization", shortLabel: "Visuals" },
  reporting: { label: "Reporting", shortLabel: "Reporting" },
  critic: { label: "Critic", shortLabel: "Critic" },
  languageegress: { label: "Language Egress", shortLabel: "Egress" },
  language_egress: { label: "Language Egress", shortLabel: "Egress" },
};

// The normal query path, in execution order. The backend only ever reports
// a span once an agent *finishes* — it never announces one starting — so
// the strip has no real name for whichever agent is currently running
// unless it infers one: the first agent in this order that hasn't reported
// in yet.
//
// Two changes in Phase 2. `marinedatadiscovery` is Agent 3, promoted to a
// real node that runs before the fan-out (P2.6). And the Critic is now here
// at all: it was left out because it only ran at DEEP, which made guessing it
// wrong more often than right — P2.5 runs it on every query, so the opposite
// is now true. Any wrong guess still self-corrects the moment the next real
// span arrives.
export const AGENT_ORDER = [
  "distress",
  "languageingress",
  "planning",
  "marinedatadiscovery",
  "geospatial",
  "oceananalytics",
  "weatherintelligence",
  "riskassessment",
  "visualization",
  "reporting",
  "critic",
  "languageegress",
];

export function nextRunningAgent(spans: { agent_name: string }[]): string | null {
  // Spans and AGENT_ORDER can each spell an agent differently (the registry
  // carries several raw-name aliases per agent) — comparing by resolved
  // short label, not raw string, is what makes this match regardless of
  // which alias the backend happens to send.
  const done = new Set(spans.map((s) => getAgentMeta(s.agent_name)?.shortLabel ?? s.agent_name));
  return AGENT_ORDER.find((key) => !done.has(getAgentMeta(key)?.shortLabel ?? key)) ?? null;
}

export function getAgentMeta(raw: string) {
  const normalizedKey = raw.toLowerCase().replace(/[^a-z0-9]/g, "");
  return AGENT_REGISTRY[raw] ?? AGENT_REGISTRY[normalizedKey];
}

export function formatAgentLabel(raw: string): string {
  const meta = getAgentMeta(raw);
  if (meta?.label) return meta.label;
  return raw
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const STATUS_TEXT: Record<AgentStatus, string> = {
  ok: "done",
  running: "running",
  degraded: "degraded",
  failed: "failed",
  pending: "queued",
  skipped: "skipped",
  cancelled: "cancelled",
};

const STATUS_STYLE: Record<AgentStatus, string> = {
  ok: "border-hairline/80 bg-shelf-3 text-ink hover:border-hairline-strong shadow-2xs hover:shadow-xs",
  running: "border-ocean-cyan/70 bg-ocean-cyan/10 text-ocean-cyan ring-1 ring-ocean-cyan/30 shadow-xs",
  degraded: "border-caution/50 bg-caution/10 text-caution shadow-2xs hover:shadow-xs",
  failed: "border-no-go/50 bg-no-go/10 text-no-go shadow-2xs hover:shadow-xs",
  pending: "border-hairline/50 bg-shelf-1/60 text-ink-dim/80 opacity-75",
  skipped: "border-hairline/40 bg-shelf-1/40 text-ink-dim/60 opacity-60",
  // P2.12 — dashed, so an early exit reads as "deliberately stopped" rather
  // than the faded "never asked for" a skip gets.
  cancelled: "border-dashed border-caution/50 bg-shelf-1/40 text-caution/70 opacity-75",
};

// P2.1 (`R-JUDGE-1`) — an engine label, shortened for a 12px badge.
//
// The distinction the badge has to carry is "was this arithmetic or a model",
// because that is the judge's actual question and the one ORCA's whole safety
// argument rests on. "DET" for deterministic, "MT" for the local IndicTrans2
// translation weights, "AI" for a span that genuinely reached a provider. The
// full string is in the title and the sr-only text, so the abbreviation is
// never the only carrier.
function engineBadge(engine: string | undefined): { short: string; cls: string } | null {
  if (!engine) return null;
  if (engine.startsWith("Deterministic")) {
    return { short: "DET", cls: "border-go/40 bg-go/10 text-go" };
  }
  if (engine.startsWith("IndicTrans2")) {
    return { short: "MT", cls: "border-ocean-cyan/40 bg-ocean-cyan/10 text-ocean-cyan" };
  }
  return { short: "AI", cls: "border-caution/40 bg-caution/10 text-caution" };
}

export function AgentPill({
  name,
  status,
  latencyMs,
  confidence,
  engine,
  skipReason,
  runs = 1,
  className = "",
}: {
  name: string;
  status: AgentStatus;
  latencyMs?: number;
  confidence?: ConfidenceTier;
  // What computed this span (orca/engines.py). Absent on a pill the frontend
  // inferred rather than received — e.g. the "currently running" guess.
  engine?: string;
  // P2.7/P2.12 — why it did not run, when it did not.
  skipReason?: string | null;
  // How many times this agent ran. A Critic-driven re-invocation runs a specialist, Reporting and
  // the Critic again; the strip shows one pill per agent with a x2 marker, not the same agent twice.
  runs?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const meta = getAgentMeta(name);
  const fullLabel = formatAgentLabel(name);
  const shortLabel = meta?.shortLabel ?? fullLabel;
  const pulse = status === "running" && !reduce;
  // Only a finished agent has a confidence; failed already reads as failed.
  const showConfidence = confidence && (status === "ok" || status === "degraded");
  // A span that did not run computed nothing, so it has no engine to report —
  // labelling a skipped node "Deterministic" would claim work that never
  // happened. The skip reason takes that slot instead.
  const didNotRun = status === "skipped" || status === "cancelled";
  const badge = didNotRun ? null : engineBadge(engine);
  const engineNote = didNotRun
    ? skipReason
      ? ` — ${status}: ${skipReason}`
      : ` — ${status}`
    : engine
    ? ` — engine: ${engine}`
    : "";

  return (
    <span
      className={`relative inline-flex w-full min-w-0 h-7 shrink-0 items-center justify-center gap-1 sm:gap-1.5 rounded-md border px-1.5 sm:px-2 text-[11px] sm:text-xs font-medium tracking-tight whitespace-nowrap select-none transition-colors duration-150 ${STATUS_STYLE[status]} ${pulse ? "animate-pulse" : ""} ${className}`}
      title={`${fullLabel} — ${STATUS_TEXT[status]}${showConfidence ? `, ${confidenceLabel(confidence)} confidence` : ""}${latencyMs ? ` (${latencyMs}ms)` : ""}${runs > 1 ? ` — ran ${runs}×` : ""}${engineNote}`}
    >
      {/* A confidence token already says "finished" — dropping the tick keeps
          the agent name from truncating in the 5-across strip. */}
      {status === "ok" && !showConfidence && (
        <Check className="size-3 sm:size-3.5 shrink-0 text-go" aria-hidden="true" strokeWidth={2.5} />
      )}
      {status === "running" && (
        <Loader2 className="size-3 sm:size-3.5 shrink-0 animate-spin text-ocean-cyan" aria-hidden="true" />
      )}
      {status === "degraded" && (
        <AlertTriangle className="size-3 sm:size-3.5 shrink-0 text-caution" aria-hidden="true" />
      )}
      {status === "failed" && (
        <X className="size-3 sm:size-3.5 shrink-0 text-no-go" aria-hidden="true" />
      )}
      <span className="truncate">{shortLabel}</span>
      <span className="sr-only">
        ({STATUS_TEXT[status]}
        {showConfidence ? `, ${confidenceLabel(confidence)} confidence` : ""}
        {runs > 1 ? `, ran ${runs} times` : ""}
        {engineNote})
      </span>
      {/* P2.1 — the engine, pinned bottom-left so it costs the agent name no
          width (the same constraint the confidence letter solves top-right).
          Text, not colour alone: "DET" / "MT" / "AI" read without hue, and
          the full engine string is in the title and the sr-only text above. */}
      {badge && (
        <span
          aria-hidden="true"
          className={`absolute -bottom-1.5 -left-1.5 hidden rounded-[3px] border px-1 font-mono text-[8px] font-bold leading-[1.4] ring-2 ring-shelf-1 sm:inline ${badge.cls}`}
        >
          {badge.short}
        </span>
      )}
      {showConfidence && (
        // One boxed letter pinned to the pill's top-right corner, so it takes
        // no width from the name (which otherwise truncated at ~1366 px).
        // Filled in the tier colour, 15% darker so white text clears 4.5:1 on
        // the lightest tier; still a letter, not colour alone (principle 9) —
        // the full word is in the title and the sr-only text above.
        <span
          aria-hidden="true"
          className={`absolute -right-1.5 -top-1.5 grid size-3.5 place-items-center rounded-[3px] font-mono text-[9px] font-bold leading-none text-white ring-2 ring-shelf-1 ${CONFIDENCE_FILL[confidence]}`}
        >
          {confidence === "LOW_DATA" ? "L" : confidence === "MEDIUM" ? "M" : "H"}
        </span>
      )}
      {runs > 1 && (
        <span
          aria-hidden="true"
          title={`Ran ${runs} times, re-invoked after a Critic critique. Time is the sum.`}
          className="absolute -bottom-1.5 -right-1.5 rounded-[3px] border border-hairline bg-shelf-3 px-1 font-mono text-[8px] font-bold leading-[1.4] text-ink-muted ring-2 ring-shelf-1"
        >
          ×{runs}
        </span>
      )}
      {latencyMs != null && status === "ok" && (
        <span
          data-readout
          className="hidden 2xl:inline ml-0.5 rounded bg-shelf-2/90 px-1 py-0.2 font-mono text-[9px] text-ink-dim"
        >
          {latencyMs}ms
        </span>
      )}
    </span>
  );
}

type LinkState = "idle" | "flowing" | "delivered";

function linkState(left: AgentStatus | undefined, right: AgentStatus | undefined): LinkState {
  const leftDone = !!left && left !== "pending" && left !== "running";
  if (!leftDone || !right) return "idle";
  const rightDone = right !== "pending" && right !== "running";
  return rightDone ? "delivered" : "flowing";
}

// The connector: a 12–16px channel standing in for the water between two
// buoys. Idle water is a faint dashed line; once the upstream agent is done
// and the downstream one is in flight, a short bead of light runs the
// channel on a loop — current carrying the query onward, not a spinner
// telling you to wait. It solidifies into a steady cyan line once both
// sides have actually landed.
function AgentLink({ state }: { state: LinkState }) {
  const reduce = useReducedMotion();

  if (state === "flowing" && !reduce) {
    return (
      <div
        aria-hidden="true"
        className="relative h-1 w-3 shrink-0 self-center overflow-hidden rounded-full bg-hairline/25 sm:w-4"
      >
        <motion.span
          className="absolute inset-y-0 left-0 w-2/3 rounded-full bg-gradient-to-r from-transparent via-ocean-cyan to-transparent"
          animate={{ x: ["-100%", "250%"] }}
          transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
        />
      </div>
    );
  }

  return (
    <div
      aria-hidden="true"
      className={`h-px w-3 shrink-0 self-center rounded-full sm:w-4 ${
        state === "delivered" ? "bg-ocean-cyan/70" : state === "flowing" ? "bg-ocean-cyan/40" : "bg-hairline/30"
      }`}
    />
  );
}

export function AgentStrip({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const items = React.Children.toArray(children).filter(Boolean) as React.ReactElement<{ status: AgentStatus }>[];

  // Rows of five, as many as there are spans — never a fixed two. The strip
  // used to slice(0, 10), which was the whole pipeline until Phase 2. Agent 3
  // (P2.6), the Critic on every query (P2.5) and its re-invocation add up to
  // five more spans, and a hard slice silently dropped exactly those: the
  // Critic, the headline of the phase, was the pill nobody could see. A
  // minimum of two rows keeps the empty-state placeholders the strip has
  // always drawn while the first spans stream in.
  const rows: React.ReactElement<{ status: AgentStatus }>[][] = [];
  for (let i = 0; i < Math.max(items.length, 10); i += 5) rows.push(items.slice(i, i + 5));

  const renderRow = (rowItems: React.ReactElement<{ status: AgentStatus }>[]) => (
    <div className="flex items-center w-full justify-between gap-1 sm:gap-1.5">
      {Array.from({ length: 5 }).map((_, index) => {
        const item = rowItems[index];
        return (
          <React.Fragment key={index}>
            <div className="flex-1 min-w-0 flex justify-center">
              {item ?? (
                <div className="h-7 w-full rounded-md border border-dashed border-hairline/30 bg-shelf-1/20" />
              )}
            </div>
            {index < 4 && <AgentLink state={linkState(item?.props.status, rowItems[index + 1]?.props.status)} />}
          </React.Fragment>
        );
      })}
    </div>
  );

  return (
    <div
      aria-live="polite"
      aria-label="Agent reasoning trace"
      className={`w-full rounded-xl border border-hairline/60 bg-shelf-1/40 p-2 sm:p-2.5 shadow-2xs ${className}`}
    >
      <div className="flex flex-col gap-1.5 sm:gap-2">
        {rows.map((row, i) => (
          <React.Fragment key={i}>{renderRow(row)}</React.Fragment>
        ))}
      </div>
    </div>
  );
}
