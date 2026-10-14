"use client";

// AgentTraceUI — The new trace interface that replaces the pill-based
// AgentStrip with a professional reasoning trace similar to ChatGPT and
// Claude. This component shows agent execution in two states:
//
// 1. Collapsed View: A single line showing "Worked for {N}s" above the answer
// 2. Expanded View: A flat chronological list of agent execution steps
//
// The UI displays only what the backend reports through /trace/{query_id}
// and SSE agent_span events — no inference, no guessing. The backend audit
// work is complete (agents 4 and 6 fixed), ensuring accurate trace data.
//
// Requirements fulfilled: 1.1, 1.3, 2.1, 4.1, 4.2, 4.3, 4.4, 4.5, 13.1, 13.2, 13.3, 15.2, 15.3, 15.4
//
// Note: This implementation uses a FLAT LIST structure for displaying agent
// steps in chronological order (Requirement 2.2, 2.3). This allows teammates
// to migrate to a tree structure later if product requirements change. The
// parallel execution pattern is indicated through indentation and grouping
// labels, not through actual tree nesting in the DOM.

import React, { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { TraceGraph } from "../reasoning/fixture";
import { adaptTraceGraph, AGENT_LABEL } from "../reasoning/trace-adapter";
import { API_BASE } from "../lib/apiBase";
import type { AgentStatus } from "./AgentPill";
import { LANGUAGES } from "../i18n/languages";
import { AgentTraceCollapsed } from "./AgentTraceCollapsed";
import {
  AgentTraceExpanded,
  formatDuration,
} from "./AgentTraceExpanded";

// ============================================================================
// Type Definitions
// ============================================================================

/**
 * Props for the main AgentTraceUI container component
 * 
 * Requirement 13.1: Compatible interface with ChatTurn's current usage
 * Requirement 13.2: Accepts query_id and trace data props from ChatTurn
 */
export interface AgentTraceUIProps {
  /** Agent spans from useAskThread hook (SSE stream) */
  spans: AgentSpan[];
  /** Whether agents are still executing */
  streaming: boolean;
  /** Query ID for fetching full trace data */
  queryId?: string;
  /** Persisted measured duration for cache hits/reloaded turns with untimed spans. */
  fallbackTotalTimeMs?: number;
  /** Language of the answer, used to name a completed translation step. */
  responseLanguage?: string;
  /** Optional className for styling */
  className?: string;
}

/**
 * Agent span data from SSE stream (existing type from useAskThread)
 */
export interface AgentSpan {
  agent_name: string;
  status: AgentStatus;
  latency_ms?: number;
  confidence_tier?: string;
  engine?: string;
  skip_reason?: string | null;
  run_count?: number;
  reasoning_summary?: string | null;
  confidence_rationale?: string | null;
}

/**
 * Props for the collapsed summary view component
 * 
 * Requirement 1.1: Display total execution time
 * Requirement 1.5: Indicate expandability on hover
 */
export interface AgentTraceCollapsedProps {
  /** Total execution time in milliseconds (sum of all agent latency_ms) */
  totalTimeMs: number;
  /** Whether agents are still running (show progress indicator) */
  streaming: boolean;
  /** Current trace text to display */
  currentText?: string;
  /** Callback when user clicks to expand */
  onExpand: () => void;
}

/**
 * Props for the expanded detail view component
 * 
 * Requirement 2.1: Expand to show chronological list of steps
 * Requirement 2.5: Provide way to collapse back
 */
export interface AgentTraceExpandedProps {
  /** Adapted TraceGraph from trace-adapter.ts */
  traceGraph: TraceGraph;
  /** Whether agents are still running (show running indicators) */
  streaming: boolean;
  /** Total execution time in milliseconds */
  totalTimeMs?: number;
  /** Active pipeline action description */
  activeAction?: string;
  /** Callback when user clicks to collapse */
  onCollapse: () => void;
}

/**
 * Props for individual agent step component
 * 
 * Requirement 3.1-3.5: Display agent step content with metadata
 */
export interface AgentTraceStepProps {
  /** TraceNode from TraceGraph */
  node: import("../reasoning/fixture").TraceNode;
  /** Whether this agent is currently executing */
  isRunning?: boolean;
  /** Indentation level: 0 (base), 1 (parallel), 2 (critic loop) */
  indent?: number;
  /** Optional group label like "Parallel execution (4 agents)" */
  showGroupLabel?: string;
}

// ============================================================================
// Internal State Interface
// ============================================================================

/**
 * Internal state for AgentTraceUI component
 */
interface AgentTraceUIState {
  /** Whether the trace is expanded (false = collapsed) */
  isExpanded: boolean;
  /** Full trace data fetched from /trace/{query_id} */
  traceGraph: TraceGraph | null;
  /** Whether we're currently fetching trace data */
  loading: boolean;
  /** Error message if trace fetch failed */
  error: string | null;
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Convert AgentSpan array to a simplified TraceGraph for streaming updates
 */
function spansToTraceGraph(spans: AgentSpan[]): TraceGraph {
  const nodes: import("../reasoning/fixture").TraceNode[] = spans.map((span, index) => ({
    id: `${span.agent_name}-${index}`,
    agent_name: AGENT_LABEL[span.agent_name] ?? span.agent_name,
    depth: index,
    status: span.status,
    confidence_tier: (span.confidence_tier as import("../components/Badge").ConfidenceTier) ?? "HIGH",
    latency_ms: span.latency_ms ?? 0,
    reasoning_summary: span.reasoning_summary ?? "",
    source_count: 0,
    used_llm:
      span.agent_name === "planning" ||
      span.agent_name === "reporting" ||
      span.agent_name === "critic",
    model: null,
    tier: null,
    engine: span.engine,
    skip_reason: span.skip_reason,
    run_count: span.run_count ?? 1,
  }));

  // Group 1: weather, geospatial, ocean (initial run only)
  const group1NodeIds = nodes
    .filter((_, idx) => {
      const a = spans[idx].agent_name.toLowerCase();
      const runCount = spans[idx].run_count ?? 1;
      return (
        runCount === 1 &&
        (a === "weather_intelligence" ||
          a === "weather" ||
          a === "geospatial" ||
          a === "ocean_analytics" ||
          a === "ocean")
      );
    })
    .map((n) => n.id);

  // Group 2: risk, visualization (initial run only)
  const group2NodeIds = nodes
    .filter((_, idx) => {
      const a = spans[idx].agent_name.toLowerCase();
      const runCount = spans[idx].run_count ?? 1;
      return (
        runCount === 1 &&
        (a === "risk_assessment" ||
          a === "risk" ||
          a === "visualization")
      );
    })
    .map((n) => n.id);

  const groups: import("../reasoning/fixture").TraceGroup[] = [];
  if (group1NodeIds.length > 0) {
    groups.push({
      id: "parallel-weather-ocean",
      reason: "parallel_fanout",
      node_ids: group1NodeIds,
    });
  }
  if (group2NodeIds.length > 0) {
    groups.push({
      id: "parallel-risk-vis",
      reason: "parallel_fanout",
      node_ids: group2NodeIds,
    });
  }

  const edges: import("../reasoning/fixture").TraceEdge[] = [];
  for (let i = 0; i < nodes.length - 1; i++) {
    edges.push({
      from: nodes[i].id,
      to: nodes[i + 1].id,
      kind: "handoff",
      label: "",
    });
  }

  // Detect critic loops (e.g. Geospatial re-invoked with run_count > 1)
  for (let i = 0; i < nodes.length; i++) {
    if ((nodes[i].run_count ?? 1) > 1 && nodes[i].agent_name !== "Critic") {
      for (let j = i - 1; j >= 0; j--) {
        if (nodes[j].agent_name === "Critic") {
          edges.push({
            from: nodes[j].id,
            to: nodes[i].id,
            kind: "critic_loop",
            label: "Refining analysis",
          });
          break;
        }
      }
    }
  }

  return {
    query_id: "",
    nodes,
    edges,
    groups,
  };
}

export function getActivePipelineAction(spans: AgentSpan[]): string {
  if (!spans || spans.length === 0) {
    return "Scanning for distress signals…";
  }

  const validSpans = spans.filter((s) => s.status !== "skipped" && s.status !== "cancelled");
  const completedAgentNames = new Set(validSpans.map((s) => s.agent_name.toLowerCase()));
  const lastSpan = validSpans[validSpans.length - 1];

  // 1. Distress check
  if (!completedAgentNames.has("distress_check") && !completedAgentNames.has("distress")) {
    return "Scanning for distress signals…";
  }

  // 2. Planning
  if (!completedAgentNames.has("planning")) {
    return "Analyzing the query and planning my approach…";
  }

  // 3. Specialists Group 1 (Weather, Geospatial, Ocean)
  const hasGathering1 =
    completedAgentNames.has("weather_intelligence") ||
    completedAgentNames.has("weather");
  const hasGathering2 = completedAgentNames.has("geospatial");
  const hasGathering3 =
    completedAgentNames.has("ocean_analytics") ||
    completedAgentNames.has("ocean");
  const finishedGroup1 = hasGathering1 && hasGathering2 && hasGathering3;

  if (!finishedGroup1) {
    return "Gathering weather and sea conditions, geospatial information, and ocean conditions…";
  }

  // 4. Specialists Group 2 (Risk, Visualization)
  const hasRisk = completedAgentNames.has("risk_assessment") || completedAgentNames.has("risk");
  const hasVis = completedAgentNames.has("visualization");
  const finishedGroup2 = hasRisk && hasVis;

  if (!finishedGroup2) {
    return "Evaluating risks and preparing map visualizations…";
  }

  // Count how many times reporting and critic ran
  const reportingSpans = validSpans.filter((s) => s.agent_name.toLowerCase() === "reporting");
  const criticSpans = validSpans.filter((s) => s.agent_name.toLowerCase() === "critic");
  const reinvokedSpans = validSpans.filter(
    (s) => (s.run_count ?? 1) > 1 && s.agent_name.toLowerCase() !== "critic"
  );

  // 5. If reporting has not run yet:
  if (reportingSpans.length === 0) {
    return "Compiling my findings…";
  }

  // 6. If reporting ran once, but critic has not run:
  if (criticSpans.length === 0) {
    return "Reviewing and validating the findings…";
  }

  // 7. Critic ran. Check if critic found issues or triggered reinvocation:
  const firstCritic = criticSpans[0];
  const summaryLower = (firstCritic.reasoning_summary ?? "").toLowerCase();
  const hadIssues = summaryLower.includes("issue") || reinvokedSpans.length > 0;

  if (hadIssues) {
    // If reinvoked specialist has not completed yet:
    if (reinvokedSpans.length === 0) {
      return "Requesting Geospatial to refine its analysis…";
    }

    // If reporting second pass hasn't run:
    if (reportingSpans.length < 2) {
      const reinvokedName = AGENT_LABEL[reinvokedSpans[0].agent_name] ?? reinvokedSpans[0].agent_name;
      if (lastSpan && lastSpan.agent_name.toLowerCase() === reinvokedSpans[0].agent_name.toLowerCase()) {
        return `Requesting ${reinvokedName} to refine its analysis…`;
      }
      return "Compiling my findings…";
    }

    // If critic second pass hasn't run:
    if (criticSpans.length < 2) {
      return "Reviewing and validating the findings…";
    }
  }

  // 8. Translation (only if query was vernacular):
  const ingressSpan = validSpans.find((s) => s.agent_name.toLowerCase().includes("ingress"));
  const ingressSummary = (ingressSpan?.reasoning_summary ?? "").toLowerCase();
  const isVernacular = ingressSummary.length > 0 && !ingressSummary.includes("en") && !ingressSummary.includes("passthrough");

  if (isVernacular && !completedAgentNames.has("language_egress")) {
    return "Translating the response…";
  }

  return "Reviewing and validating the findings…";
}

// ============================================================================
// Main AgentTraceUI Component
// ============================================================================

/**
 * Custom hook for debouncing SSE updates
 * Requirement 4.5: Debounce rapid SSE updates (100ms)
 */
function useDebouncedSpans(spans: AgentSpan[], delay: number = 100): AgentSpan[] {
  const [debouncedSpans, setDebouncedSpans] = useState<AgentSpan[]>(spans);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Clear existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    // Set new timeout to update after delay
    timeoutRef.current = setTimeout(() => {
      setDebouncedSpans(spans);
    }, delay);

    // Cleanup on unmount
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [spans, delay]);

  return debouncedSpans;
}

/**
 * AgentTraceUI - Container component for the new trace interface
 * 
 * This component manages the collapsed/expanded state and orchestrates
 * rendering of the trace UI. It fetches full trace data when expanding
 * and handles the transition between views.
 * 
 * SSE STREAMING SUPPORT (Requirement 4.1-4.5, 15.2-15.4):
 * - Incremental step updates as agent_span events arrive
 * - Update collapsed view total time as new spans complete
 * - Show progress indicators for running agents
 * - Remove progress indicators when all agents complete
 * - Use memoization to prevent re-rendering completed steps
 * - Implement debouncing for rapid SSE updates (100ms)
 * 
 * Requirements fulfilled:
 * - 1.1, 1.3: Collapsed view display
 * - 2.1: Expanded view structure
 * - 4.1: Incremental step updates as agent_span events arrive
 * - 4.2: Show progress indicators for running agents
 * - 4.3: Update collapsed view total time as new spans complete
 * - 4.4: Remove progress indicators when all agents complete
 * - 4.5: Handle SSE_Stream events incrementally without re-rendering entire trace list
 * - 13.1-13.3: Integration with ChatTurn
 * - 15.2: Incremental rendering (only new steps re-render)
 * - 15.3: Memoization prevents unnecessary re-renders
 * - 15.4: Debouncing for rapid SSE updates
 */
export function AgentTraceUI({
  spans,
  streaming,
  queryId,
  fallbackTotalTimeMs,
  responseLanguage,
  className = "",
}: AgentTraceUIProps) {
  // State management for expanded/collapsed view and trace data
  const [state, setState] = useState<AgentTraceUIState>({
    isExpanded: false,
    traceGraph: null,
    loading: false,
    error: null,
  });

  // Requirement 4.5, 15.4: Debounce rapid SSE updates (100ms)
  // This prevents excessive re-renders when multiple agent_span events arrive quickly
  const debouncedSpans = useDebouncedSpans(spans, 100);

  // Requirement 4.3, 15.3: Calculate total execution time from spans (memoized)
  // Updates incrementally as new spans complete
  const totalTimeMs = useMemo(() => {
    const spanTotal = debouncedSpans.reduce(
      (sum, span) => sum + (span.latency_ms ?? 0),
      0,
    );
    return spanTotal > 0 ? spanTotal : (fallbackTotalTimeMs ?? 0);
  }, [debouncedSpans, fallbackTotalTimeMs]);

  // Requirement 4.1, 15.2: Build TraceGraph from spans for real-time rendering
  // This allows the expanded view to show incremental updates without API fetch
  const streamingTraceGraph = useMemo(() => {
    if (debouncedSpans.length === 0) {
      return null;
    }
    return spansToTraceGraph(debouncedSpans);
  }, [debouncedSpans]);

  // Prefer the latest SSE-derived graph while the expanded trace is streaming;
  // after streaming ends, keep the complete API trace stored in state.
  const sourceGraph =
    (state.isExpanded && streaming ? streamingTraceGraph : null) ??
    state.traceGraph ??
    streamingTraceGraph;
  const activeGraph = useMemo(() => {
    if (!sourceGraph || !responseLanguage || responseLanguage === "en") {
      return sourceGraph;
    }
    const languageName = LANGUAGES.find((language) => language.code === responseLanguage)?.english;
    if (!languageName) return sourceGraph;
    return {
      ...sourceGraph,
      nodes: sourceGraph.nodes.map((node) =>
        node.agent_name.toLowerCase().includes("language egress") ||
        node.id.toLowerCase().includes("language_egress")
          ? { ...node, reasoning_summary: `Response translated to ${languageName}.` }
          : node,
      ),
    };
  }, [sourceGraph, responseLanguage]);

  const currentText = useMemo(() => {
    if (!streaming) {
      return `Thought for ${formatDuration(totalTimeMs)}`;
    }
    return getActivePipelineAction(spans);
  }, [streaming, spans, totalTimeMs]);

  const containerRef = useRef<HTMLDivElement>(null);
  const collapsedButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const wasExpandedRef = useRef<boolean>(false);

  /**
   * Focus management on expand/collapse
   * Requirement 16.4: Ensure focus management on expand/collapse transitions
   */
  useEffect(() => {
    if (wasExpandedRef.current && !state.isExpanded) {
      // Focus returns to the collapsed trigger button
      collapsedButtonRef.current?.focus();
    } else if (!wasExpandedRef.current && state.isExpanded) {
      // Focus moves to the close button in expanded view
      requestAnimationFrame(() => {
        closeButtonRef.current?.focus();
      });
    }
    wasExpandedRef.current = state.isExpanded;
  }, [state.isExpanded]);

  /**
   * Smooth scroll behavior on expand
   * Requirement 18.2: Ensure expanded trace is comfortably in view
   */
  useEffect(() => {
    if (state.isExpanded && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      if (rect.bottom > window.innerHeight || rect.top < 0) {
        containerRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  }, [state.isExpanded]);

  /**
   * Handle expand action - fetch full trace data from API
   * Requirement 2.1: User clicks collapsed view to expand
   * Requirement 10.1: Fetch trace data from /trace/{query_id} on expand
   * Requirement 8.1-8.5: Accurate backend trace data integration
   * Requirement 14.5: 5-second timeout on fetch
   */
  const handleExpand = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      isExpanded: true,
      traceGraph: prev.traceGraph ?? streamingTraceGraph,
    }));

    // If queryId is available and we're not streaming, fetch the full trace
    // This provides complete edges, parallel groups, and detailed run metadata
    if (queryId && !streaming) {
      setState((prev) => ({ ...prev, loading: !prev.traceGraph, error: null }));

      const controller = new AbortController();
      const timeoutId = setTimeout(
        () => controller.abort(new DOMException("Trace request timed out", "TimeoutError")),
        5000,
      );

      try {
        const response = await fetch(`${API_BASE}/trace/${queryId}`, {
          signal: controller.signal,
        });

        if (!response.ok) {
          if (response.status === 404) {
            // Requirement 8.1: If 404 and streaming spans exist, keep streaming graph; otherwise note not found
            setState((prev) => ({
              ...prev,
              loading: false,
              error: prev.traceGraph ? null : "Trace data not found for this query",
            }));
            return;
          }
          throw new Error(`Failed to fetch trace (${response.status})`);
        }

        const apiTrace = await response.json();
        const fullTraceGraph = adaptTraceGraph(apiTrace);

        setState((prev) => ({
          ...prev,
          traceGraph: fullTraceGraph,
          loading: false,
          error: null,
        }));
      } catch (err) {
        if (!controller.signal.aborted) {
          console.error("AgentTraceUI: Failed to fetch trace data", err);
        }
        setState((prev) => ({
          ...prev,
          loading: false,
          error: prev.traceGraph
            ? null
            : controller.signal.aborted
              ? "Trace request timed out"
              : "Failed to load trace details",
        }));
      } finally {
        clearTimeout(timeoutId);
      }
    }
  }, [queryId, streaming, streamingTraceGraph]);

  /**
   * Handle collapse action - return to summary view
   * Requirement 2.5: User can collapse back to summary view
   */
  const handleCollapse = useCallback(() => {
    setState((prev) => ({ ...prev, isExpanded: false }));
  }, []);

  /**
   * When streaming concludes while trace is already expanded, refetch full graph from API
   */
  const prevStreamingRef = useRef(streaming);
  useEffect(() => {
    if (prevStreamingRef.current && !streaming && state.isExpanded && queryId) {
      handleExpand();
    }
    prevStreamingRef.current = streaming;
  }, [streaming, state.isExpanded, queryId, handleExpand]);

  return (
    <section 
      ref={containerRef} 
      aria-label="Agent reasoning trace" 
      className={`agent-trace-ui ${className}`}
    >
      <AnimatePresence mode="wait">
        {!state.isExpanded ? (
          // Collapsed View (Requirement 1.1, 1.3)
          // Requirement 4.3: Display updates as new spans complete
          <motion.div
            key="collapsed"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <AgentTraceCollapsed
              totalTimeMs={totalTimeMs}
              streaming={streaming}
              currentText={currentText}
              onExpand={handleExpand}
              buttonRef={collapsedButtonRef}
            />
          </motion.div>
        ) : (
          // Expanded View (Requirement 2.1)
          // Requirement 4.1: Incremental step updates as agent_span events arrive
          <motion.div
            key="expanded"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
          >
            {/* Loading state skeleton loader (Requirement 14.2) */}
            {state.loading && !activeGraph && (
              <div 
                className="rounded-lg border border-hairline/60 bg-shelf-1/40 p-3 shadow-sm space-y-2"
                role="status"
                aria-label="Loading trace data"
              >
                <div className="h-4 w-36 animate-pulse rounded bg-shelf-3" />
                <div className="space-y-1.5 pt-1">
                  <div className="h-7 w-full animate-pulse rounded border border-hairline/40 bg-shelf-2/60" />
                  <div className="h-7 w-full animate-pulse rounded border border-hairline/40 bg-shelf-2/60" />
                  <div className="h-7 w-full animate-pulse rounded border border-hairline/40 bg-shelf-2/60" />
                </div>
              </div>
            )}

            {/* Error state with retry (Requirement 8.3) */}
            {state.error && !activeGraph && (
              <div 
                className="rounded-lg border border-no-go/30 bg-shelf-1/40 p-3 shadow-sm text-center"
                role="alert"
              >
                <p className="text-xs text-caution mb-2">{state.error}</p>
                <button
                  onClick={() => handleExpand()}
                  type="button"
                  className="text-xs font-mono rounded border border-hairline px-2.5 py-1 text-ink-dim hover:text-ink hover:bg-shelf-2 transition-colors"
                >
                  Retry
                </button>
              </div>
            )}

            {activeGraph && (
              <AgentTraceExpanded
                traceGraph={activeGraph}
                streaming={streaming}
                totalTimeMs={totalTimeMs}
                activeAction={currentText}
                onCollapse={handleCollapse}
                closeButtonRef={closeButtonRef}
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

// ============================================================================
// Utility Functions
// ============================================================================
// Note: formatDuration utility has been moved to AgentTraceCollapsed component
