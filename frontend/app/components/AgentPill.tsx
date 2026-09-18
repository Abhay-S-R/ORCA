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

export type AgentStatus = "pending" | "running" | "ok" | "degraded" | "failed" | "skipped";

export const AGENT_REGISTRY: Record<string, { label: string; shortLabel: string }> = {
  distress: { label: "Distress Check", shortLabel: "Distress" },
  distresscheck: { label: "Distress Check", shortLabel: "Distress" },
  distress_check: { label: "Distress Check", shortLabel: "Distress" },
  languageingress: { label: "Language Ingress", shortLabel: "Ingress" },
  language_ingress: { label: "Language Ingress", shortLabel: "Ingress" },
  planning: { label: "Planning", shortLabel: "Planning" },
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
// in yet. Critic is conditional (DEEP depth only) and left out on purpose;
// it's rare enough that guessing it would be wrong more often than right,
// and any wrong guess self-corrects the moment the next real span arrives.
const AGENT_ORDER = [
  "distress",
  "languageingress",
  "planning",
  "geospatial",
  "oceananalytics",
  "weatherintelligence",
  "riskassessment",
  "visualization",
  "reporting",
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
};

const STATUS_STYLE: Record<AgentStatus, string> = {
  ok: "border-hairline/80 bg-shelf-3 text-ink hover:border-hairline-strong shadow-2xs hover:shadow-xs",
  running: "border-ocean-cyan/70 bg-ocean-cyan/10 text-ocean-cyan ring-1 ring-ocean-cyan/30 shadow-xs",
  degraded: "border-caution/50 bg-caution/10 text-caution shadow-2xs hover:shadow-xs",
  failed: "border-no-go/50 bg-no-go/10 text-no-go shadow-2xs hover:shadow-xs",
  pending: "border-hairline/50 bg-shelf-1/60 text-ink-dim/80 opacity-75",
  skipped: "border-hairline/40 bg-shelf-1/40 text-ink-dim/60 opacity-60",
};

export function AgentPill({
  name,
  status,
  latencyMs,
  className = "",
}: {
  name: string;
  status: AgentStatus;
  latencyMs?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const meta = getAgentMeta(name);
  const fullLabel = formatAgentLabel(name);
  const shortLabel = meta?.shortLabel ?? fullLabel;
  const pulse = status === "running" && !reduce;

  return (
    <span
      className={`inline-flex w-full min-w-0 h-7 shrink-0 items-center justify-center gap-1.5 rounded-md border px-2 text-[11px] sm:text-xs font-medium tracking-tight whitespace-nowrap select-none transition-colors duration-150 ${STATUS_STYLE[status]} ${pulse ? "animate-pulse" : ""} ${className}`}
      title={`${fullLabel} — ${STATUS_TEXT[status]}${latencyMs ? ` (${latencyMs}ms)` : ""}`}
    >
      <span className="truncate">{shortLabel}</span>
      <span className="sr-only">({STATUS_TEXT[status]})</span>

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

  const row1 = items.slice(0, 5);
  const row2 = items.slice(5, 10);

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
        {renderRow(row1)}
        {renderRow(row2)}
      </div>
    </div>
  );
}
