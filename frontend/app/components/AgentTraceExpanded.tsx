"use client";

// AgentTraceExpanded — Human-like narrative trace for Sagar Sarathi
//
// Each agent step is narrated as a natural language sentence describing
// WHAT the system is doing, not which component is running. This makes
// the trace feel like a pipeline of intelligent work, not a list of tools.
//
// Key principles:
// - Only show agents that actually ran (skip skipped/cancelled)
// - For LLM agents, show reasoning_summary when available
// - Parallel groups describe what's being gathered, not who's running
// - Every agent has a unique, human-like phrase
// - Critic explains what it's validating or who it's calling back

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import type { TraceGraph, TraceNode } from "../reasoning/fixture";
import { calculateExecutionOrder, type OrderedStep } from "./calculateExecutionOrder";
import { AGENT_LABEL } from "../reasoning/trace-adapter";

export interface AgentTraceExpandedProps {
  traceGraph: TraceGraph;
  streaming: boolean;
  onCollapse: () => void;
  closeButtonRef?: React.RefObject<HTMLButtonElement | null>;
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
  /** Short noun phrase for parallel group descriptions (e.g. "weather and sea conditions") */
  activity?: string;
}

/**
 * Human-like narrative for each agent, keyed by display name.
 * These make the trace read like Sagar Sarathi is narrating its own process.
 */
const AGENT_NARRATIVE: Record<string, AgentNarrative> = {
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

/** Resolve the human-readable display name for a node */
function getDisplayName(node: TraceNode): string {
  return AGENT_LABEL[node.agent_name] ?? AGENT_LABEL[node.id] ?? node.agent_name;
}

/** Get the narrative config for a node */
function getNarrative(node: TraceNode): AgentNarrative | undefined {
  const name = getDisplayName(node);
  return AGENT_NARRATIVE[name];
}

/** Did this agent actually run? (false for skipped/cancelled) */
function didRun(node: TraceNode): boolean {
  return node.status !== "skipped" && node.status !== "cancelled";
}

/** Is this step currently executing? */
function isRunning(node: TraceNode, streaming: boolean, isLast: boolean): boolean {
  if (!streaming) return false;
  return node.status === "running" || (isLast && node.status === "pending");
}

/**
 * Get the "done" text for an agent.
 * For LLM agents with a reasoning_summary, use it to make the trace richer.
 * Otherwise fall back to the narrative's done phrase.
 */
function getDoneText(node: TraceNode, narrative: AgentNarrative | undefined): string {
  // For LLM agents, prefer the reasoning summary — it tells us WHAT the agent thought
  if (node.used_llm && node.reasoning_summary && node.reasoning_summary.trim()) {
    return node.reasoning_summary;
  }
  return narrative?.done ?? `${getDisplayName(node)} complete`;
}

/**
 * Format a list with commas and "and" before the last item.
 * ["a"] → "a"
 * ["a", "b"] → "a and b"
 * ["a", "b", "c"] → "a, b, and c"
 */
function joinNatural(items: string[]): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

// ---------------------------------------------------------------------------
// Step → narrative line conversion
// ---------------------------------------------------------------------------

function stepToNarrative(
  step: OrderedStep,
  streaming: boolean,
  isLastStep: boolean,
  allSteps: OrderedStep[],
  index: number,
): { text: string; running: boolean } | null {
  switch (step.type) {
    case "step": {
      // ---- SKIP agents that didn't run ----
      if (!didRun(step.node)) return null;

      const narrative = getNarrative(step.node);
      const active = isRunning(step.node, streaming, isLastStep);

      if (active) {
        return {
          text: narrative?.running ?? `Processing ${getDisplayName(step.node)}…`,
          running: true,
        };
      }

      // Terminal statuses
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
      // Build a natural description of what's being gathered in parallel.
      // Uses each agent's "activity" noun phrase instead of its name.
      const activities: string[] = [];
      for (let i = index + 1; i < allSteps.length; i++) {
        const s = allSteps[i];
        if (s.type === "group_end") break;
        if (s.type === "step" && didRun(s.node)) {
          const n = getNarrative(s.node);
          activities.push(n?.activity ?? getDisplayName(s.node).toLowerCase());
        }
      }
      if (activities.length === 0) return null; // All agents in group were skipped
      return {
        text: `Gathering ${joinNatural(activities)}`,
        running: false,
      };
    }

    case "group_end":
      return null;

    case "critic_reinvoke":
      // Label is already set by calculateExecutionOrder with human phrasing
      return { text: step.label, running: false };

    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AgentTraceExpanded({
  traceGraph,
  streaming,
  onCollapse,
  closeButtonRef,
}: AgentTraceExpandedProps) {
  const orderedSteps = React.useMemo(
    () => calculateExecutionOrder(traceGraph),
    [traceGraph],
  );

  const narrativeLines = React.useMemo(() => {
    const lines: { key: string; text: string; running: boolean }[] = [];

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

      // Skip individual parallel agent steps — they're covered by
      // the "Gathering X, Y, and Z" group line
      if (step.type === "step" && step.indent === 1) {
        if (!result.running) return; // Still show actively-running ones
      }

      lines.push({ key, text: result.text, running: result.running });
    });

    return lines;
  }, [orderedSteps, streaming]);

  return (
    <section
      id="agent-trace-expanded-region"
      className="agent-trace-expanded"
      role="region"
      aria-label="Agent execution trace"
    >
      {/* Header */}
      <div className="mb-2 flex items-center justify-between">
        <button
          ref={closeButtonRef}
          onClick={onCollapse}
          className="flex items-center gap-1.5 text-[11px] sm:text-xs font-medium text-ink-dim hover:text-ink transition-colors"
          aria-label="Collapse trace"
          type="button"
        >
          <span className="select-none">▾</span>
          <span>Thinking</span>
        </button>
        <button
          onClick={onCollapse}
          className="flex size-5 items-center justify-center rounded text-ink-dim/60 hover:text-ink transition-colors"
          aria-label="Close"
          type="button"
        >
          <X className="size-3" aria-hidden="true" />
        </button>
      </div>

      {/* Narrative trace lines */}
      <div className="flex flex-col gap-0.5 pl-2 border-l-2 border-ink-dim/15">
        <AnimatePresence initial={false}>
          {narrativeLines.map((line) => (
            <motion.div
              key={line.key}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="flex items-center gap-2 py-0.5"
            >
              {line.running ? (
                <span className="relative flex size-1.5 shrink-0">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-ocean-cyan opacity-60" />
                  <span className="relative inline-flex size-1.5 rounded-full bg-ocean-cyan" />
                </span>
              ) : (
                <span className="size-1 shrink-0 rounded-full bg-ink-dim/30" />
              )}

              <span
                className={`text-[11px] sm:text-xs leading-relaxed ${
                  line.running ? "text-ink font-medium" : "text-ink-dim"
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
            className="flex items-center gap-2 py-0.5"
          >
            <span className="relative flex size-1.5 shrink-0">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-ocean-cyan opacity-60" />
              <span className="relative inline-flex size-1.5 rounded-full bg-ocean-cyan" />
            </span>
            <span className="text-[11px] sm:text-xs text-ink-dim">
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
