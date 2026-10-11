"use client";

// AgentTraceExpanded — Human-like narrative trace for Sagar Sarathi
//
// Each agent step is narrated as a natural language sentence describing
// WHAT the system is doing, not which component is running.
// Font size and style matches the response typography (text-sm leading-relaxed).
// Active steps feature a left-to-right text shimmer loading animation.

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import type { TraceGraph, TraceNode } from "../reasoning/fixture";
import { calculateExecutionOrder, type OrderedStep } from "./calculateExecutionOrder";
import { AGENT_LABEL } from "../reasoning/trace-adapter";

export interface AgentTraceExpandedProps {
  traceGraph: TraceGraph;
  streaming: boolean;
  totalTimeMs?: number;
  onCollapse: () => void;
  closeButtonRef?: React.RefObject<HTMLButtonElement | null>;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Agent narrative descriptions
// ---------------------------------------------------------------------------

interface AgentNarrative {
  /** What to show while the agent is actively running */
  running: string;
  /** What to show when the agent finished successfully */
  done: string;
  /** What to show if the agent failed */
  failed?: string;
  /** Short noun phrase for parallel group descriptions */
  activity?: string;
}

export const AGENT_NARRATIVE: Record<string, AgentNarrative> = {
  "Distress Check": {
    running: "Scanning for distress signals…",
    done: "No distress signals detected",
    failed: "Distress signal check encountered an error",
  },
  "Language Ingress": {
    running: "Translating the query…",
    done: "Query translated successfully",
    failed: "Could not translate the query",
  },
  "Planning": {
    running: "Analyzing the query and planning my approach…",
    done: "Routing to specialist agents",
    failed: "Failed to plan the approach",
  },
  "Marine Data Discovery": {
    running: "Searching for relevant marine data sources…",
    done: "Relevant data sources identified",
    failed: "Could not discover marine data sources",
    activity: "marine data sources",
  },
  "Weather Intelligence": {
    running: "Fetching weather and sea conditions…",
    done: "Weather and sea conditions analyzed",
    failed: "Weather data retrieval failed",
    activity: "weather and sea conditions",
  },
  "Geospatial": {
    running: "Analyzing geospatial data…",
    done: "Geospatial analysis complete",
    failed: "Geospatial analysis failed",
    activity: "geospatial information",
  },
  "Ocean Analytics": {
    running: "Computing ocean analytics…",
    done: "Ocean conditions processed",
    failed: "Ocean analytics computation failed",
    activity: "ocean conditions",
  },
  "Risk Assessment": {
    running: "Evaluating potential risks…",
    done: "Risk evaluation complete",
    failed: "Risk assessment encountered an error",
    activity: "risk factors",
  },
  "Visualization": {
    running: "Preparing map visualizations…",
    done: "Visualizations prepared",
    failed: "Visualization generation failed",
    activity: "map visualizations",
  },
  "Reporting": {
    running: "Compiling my findings…",
    done: "Findings compiled into a report",
    failed: "Report compilation failed",
  },
  "Critic": {
    running: "Reviewing and validating the findings…",
    done: "Findings validated — quality check passed",
    failed: "Validation encountered an issue",
  },
  "Language Egress": {
    running: "Translating the response…",
    done: "Response translated",
    failed: "Response translation failed",
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function getDisplayName(node: TraceNode): string {
  return AGENT_LABEL[node.agent_name] ?? AGENT_LABEL[node.id] ?? node.agent_name;
}

export function getNarrative(node: TraceNode): AgentNarrative | undefined {
  const name = getDisplayName(node);
  return AGENT_NARRATIVE[name];
}

export function didRun(node: TraceNode): boolean {
  return node.status !== "skipped" && node.status !== "cancelled";
}

export function isRunning(node: TraceNode, streaming: boolean, isLast: boolean): boolean {
  if (!streaming) return false;
  return node.status === "running" || (isLast && node.status === "pending");
}

export function getDoneText(node: TraceNode, narrative: AgentNarrative | undefined): string {
  if (node.used_llm && node.reasoning_summary && node.reasoning_summary.trim()) {
    return node.reasoning_summary;
  }
  return narrative?.done ?? `${getDisplayName(node)} complete`;
}

export function joinNatural(items: string[]): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

// ---------------------------------------------------------------------------
// Step → narrative line conversion
// ---------------------------------------------------------------------------

export function stepToNarrative(
  step: OrderedStep,
  streaming: boolean,
  isLastStep: boolean,
  allSteps: OrderedStep[],
  index: number,
): { text: string; running: boolean } | null {
  switch (step.type) {
    case "step": {
      if (!didRun(step.node)) return null;

      const narrative = getNarrative(step.node);
      const active = isRunning(step.node, streaming, isLastStep);

      if (active) {
        return {
          text: narrative?.running ?? `Processing ${getDisplayName(step.node)}…`,
          running: true,
        };
      }

      switch (step.node.status) {
        case "ok":
        case "degraded":
          return { text: getDoneText(step.node, narrative), running: false };
        case "failed":
          return {
            text: narrative?.failed ?? `${getDisplayName(step.node)} failed`,
            running: false,
          };
        default:
          return { text: getDoneText(step.node, narrative), running: false };
      }
    }

    case "group_start": {
      const activities: string[] = [];
      let anyRunning = false;
      for (let i = index + 1; i < allSteps.length; i++) {
        const s = allSteps[i];
        if (s.type === "group_end") break;
        if (s.type === "step" && didRun(s.node)) {
          const n = getNarrative(s.node);
          activities.push(n?.activity ?? getDisplayName(s.node).toLowerCase());
          if (isRunning(s.node, streaming, i === allSteps.length - 1)) {
            anyRunning = true;
          }
        }
      }
      if (activities.length === 0) return null;
      return {
        text: anyRunning
          ? `Gathering ${joinNatural(activities)}…`
          : `Gathering ${joinNatural(activities)}`,
        running: anyRunning,
      };
    }

    case "group_end":
      return null;

    case "critic_reinvoke":
      return { text: step.label, running: false };

    default:
      return null;
  }
}

export interface NarrativeLine {
  key: string;
  text: string;
  running: boolean;
}

export function getNarrativeLines(
  traceGraph: TraceGraph | null,
  streaming: boolean,
): NarrativeLine[] {
  if (!traceGraph) return [];
  const orderedSteps = calculateExecutionOrder(traceGraph);
  const lines: NarrativeLine[] = [];

  orderedSteps.forEach((step, idx) => {
    const isLast = idx === orderedSteps.length - 1;
    const result = stepToNarrative(step, streaming, isLast, orderedSteps, idx);
    if (!result) return;

    const key =
      step.type === "step"
        ? step.node.id
        : step.type === "group_start"
          ? `group-${step.groupId}`
          : `critic-${idx}`;

    if (step.type === "step" && step.indent === 1) {
      if (!result.running) return;
    }

    lines.push({ key, text: result.text, running: result.running });
  });

  return lines;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AgentTraceExpanded({
  traceGraph,
  streaming,
  totalTimeMs,
  onCollapse,
  closeButtonRef,
}: AgentTraceExpandedProps) {
  const narrativeLines = React.useMemo(() => {
    return getNarrativeLines(traceGraph, streaming);
  }, [traceGraph, streaming]);

  return (
    <section
      id="agent-trace-expanded-region"
      className="agent-trace-expanded py-0.5"
      role="region"
      aria-label="Agent execution trace"
    >
      {/* Header */}
      <div className="mb-2 flex items-center justify-between">
        <button
          ref={closeButtonRef}
          onClick={onCollapse}
          className="group flex items-center gap-2 text-sm font-medium text-ink-dim hover:text-ink transition-colors cursor-pointer"
          aria-label="Collapse trace"
          type="button"
        >
          <span className="select-none text-xs text-ink-dim shrink-0">▾</span>
          <span>
            {streaming
              ? "Thinking…"
              : `Thought for ${formatDuration(totalTimeMs ?? 0)}`}
          </span>
        </button>
        <button
          onClick={onCollapse}
          className="flex size-6 items-center justify-center rounded text-ink-dim/60 hover:text-ink transition-colors cursor-pointer"
          aria-label="Close"
          type="button"
        >
          <X className="size-3.5" aria-hidden="true" />
        </button>
      </div>

      {/* Narrative trace lines */}
      <div className="flex flex-col gap-1 pl-3 border-l-2 border-hairline-strong/40 ml-1">
        <AnimatePresence initial={false}>
          {narrativeLines.map((line) => (
            <motion.div
              key={line.key}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="flex items-start gap-2.5 py-0.5"
            >
              {line.running ? (
                <span className="relative flex size-2 shrink-0 mt-1.5">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-ocean-cyan opacity-60" />
                  <span className="relative inline-flex size-2 rounded-full bg-ocean-cyan" />
                </span>
              ) : (
                <span className="size-1.5 shrink-0 rounded-full bg-ink-dim/40 mt-1.5" />
              )}

              <span
                className={`text-sm leading-relaxed ${
                  line.running
                    ? "text-shimmer font-medium"
                    : "text-ink-muted"
                }`}
              >
                {line.text}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Fallback streaming indicator */}
        {streaming && narrativeLines.length > 0 && !narrativeLines.some((l) => l.running) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-start gap-2.5 py-0.5"
          >
            <span className="relative flex size-2 shrink-0 mt-1.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-ocean-cyan opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-ocean-cyan" />
            </span>
            <span className="text-sm leading-relaxed text-shimmer font-medium">
              Processing…
            </span>
          </motion.div>
        )}
      </div>

      {/* Screen reader */}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {streaming
          ? `Working. ${narrativeLines.length} steps so far.`
          : `Done. ${narrativeLines.length} steps completed.`}
      </div>
    </section>
  );
}
