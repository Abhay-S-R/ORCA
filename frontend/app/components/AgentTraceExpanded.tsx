"use client";

// AgentTraceExpanded — Detail view for the Agent Trace UI
//
// Displays a flat chronological list of agent execution steps with real-time
// streaming updates. This component integrates calculateExecutionOrder to
// get the chronological step list and renders AgentTraceStep components in
// execution order.
//
// The implementation uses a FLAT LIST structure (Requirement 2.2, 2.3) to
// show agent steps in chronological order. This design allows teammates to
// migrate to a tree structure later if product requirements change. Parallel
// execution is indicated through indentation and grouping labels, not through
// actual tree nesting in the DOM.
//
// Key features:
// - Flat chronological list of agent steps
// - Parallel execution grouping with "Parallel execution (N agents):" label
// - Critic loop display with indentation and "↻ Critic calls X again" text
// - Header with collapse button
// - Collapse callback for returning to summary view
// - Container styling: border, background, shadows
//
// Requirements fulfilled:
// - 2.1: Expanded view shows flat chronological list
// - 2.2: Display steps in execution order as flat list
// - 2.3: Document flat list structure explicitly in code comments
// - 2.4: Display steps in chronological order based on execution sequence
// - 2.5: Provide way to collapse back to summary view
// - 5.1: Display re-invocations as separate steps
// - 5.2: Display re-invoked steps with indentation
// - 5.4: Show steps indented under critic's critique step
// - 6.1: Identify parallel execution from TraceGraph.groups
// - 6.2: Display individual lines for each specialist agent
// - 6.3: Display timestamps showing concurrent execution
// - 6.4: Visually indicate parallel execution through layout/spacing
// - 6.5: Show individual execution times for parallel agents
// - 11.1: Display normal sequential flow for handoff edges
// - 11.2: Display re-invocation flow with visual distinction

import React, { useState, useEffect } from "react";
import { X } from "lucide-react";
import { motion } from "framer-motion";
import type { TraceGraph, TraceNode } from "../reasoning/fixture";
import { AgentTraceStep } from "./AgentTraceStep";
import { calculateExecutionOrder, type OrderedStep } from "./calculateExecutionOrder";

/**
 * Props for the expanded detail view component
 * 
 * Requirements:
 * - 2.1: Expand to show chronological list of steps
 * - 2.5: Provide way to collapse back
 */
export interface AgentTraceExpandedProps {
  /** Adapted TraceGraph from trace-adapter.ts */
  traceGraph: TraceGraph;
  /** Whether agents are still running (show running indicators) */
  streaming: boolean;
  /** Callback when user clicks to collapse */
  onCollapse: () => void;
}

/**
 * AgentTraceExpanded - Detail view showing chronological list of steps
 *
 * This component renders agent execution steps in a flat chronological list,
 * showing parallel execution through grouping labels and indentation, and
 * critic loops through indented re-invocations.
 *
 * DESIGN NOTE - FLAT LIST STRUCTURE:
 * The current implementation uses a FLAT LIST for displaying agent steps
 * in chronological order (Requirements 2.2, 2.3). This allows for simple,
 * intuitive rendering that matches the actual execution flow. The parallel
 * execution pattern is indicated through indentation and grouping labels,
 * NOT through actual tree nesting in the DOM.
 *
 * If product requirements change in the future, this can be migrated to a
 * tree structure. The calculateExecutionOrder utility already identifies
 * the relationships needed for that transformation (see its documentation
 * for migration notes).
 *
 * Requirements fulfilled:
 * - 2.1: Chronological list of agent steps
 * - 2.2: Steps in execution order as flat list (NOT tree)
 * - 2.3: Explicit documentation of flat list structure
 * - 2.4: Chronological order based on execution sequence
 * - 2.5: Collapse callback for returning to summary view
 * - 5.1, 5.2, 5.4: Critic loop visualization with indentation
 * - 6.1-6.5: Parallel execution display with grouping
 * - 11.1, 11.2: Edge type visualization (handoff, critic_loop)
 */
export function AgentTraceExpanded({
  traceGraph,
  streaming,
  onCollapse,
}: AgentTraceExpandedProps) {
  /**
   * Calculate chronological execution order from TraceGraph
   * Requirement 2.4: Steps in chronological order based on execution sequence
   * Requirement 6.1: Identify parallel execution from TraceGraph.groups
   * Requirement 15.3: Memoize to prevent unnecessary recalculation
   */
  const orderedSteps = React.useMemo(() => {
    return calculateExecutionOrder(traceGraph);
  }, [traceGraph]);

  /**
   * Track rendered node IDs for incremental updates
   * Requirement 15.2: Update incrementally when new agent spans arrive
   * Requirement 15.3: Don't re-render completed steps
   */
  const [renderedNodeIds, setRenderedNodeIds] = React.useState<Set<string>>(new Set());

  /**
   * Update rendered node IDs when new nodes arrive
   * Requirement 4.1: Incremental step updates as agent_span events arrive
   */
  React.useEffect(() => {
    const currentNodeIds = new Set(
      orderedSteps
        .filter((step) => step.type === "step")
        .map((step) => (step as { type: "step"; node: TraceNode }).node.id)
    );
    
    setRenderedNodeIds(currentNodeIds);
  }, [orderedSteps]);

  /**
   * Track which node IDs were in the previous render
   * This helps us identify newly added steps for entry animations
   * Requirement 4.1: Animate new steps as they arrive
   */
  const prevNodeIdsRef = React.useRef<Set<string>>(new Set());
  
  /**
   * Check if a node is newly added (should animate in)
   */
  const isNewNode = React.useCallback((nodeId: string): boolean => {
    return !prevNodeIdsRef.current.has(nodeId);
  }, []);

  /**
   * Update previous node IDs after render
   */
  React.useEffect(() => {
    prevNodeIdsRef.current = renderedNodeIds;
  }, [renderedNodeIds]);

  /**
   * Handle keyboard accessibility for collapse button
   * Requirement 2.5: Collapse back to summary view
   */
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onCollapse();
    }
    if (event.key === "Escape") {
      onCollapse();
    }
  };

  /**
   * Render individual ordered steps
   * This function handles the flat list rendering of steps, group labels,
   * and critic re-invocation markers.
   * 
   * Requirement 4.1: Animate new steps with entry animation
   * Requirement 15.3: Memoized AgentTraceStep prevents re-rendering completed steps
   */
  const renderOrderedStep = (step: OrderedStep, index: number) => {
    switch (step.type) {
      case "step": {
        // Regular agent execution step
        // Requirements: 2.4 (chronological order), 3.1-3.5 (step content)
        const isNew = isNewNode(step.node.id);
        const isCurrentlyRunning = streaming && (step.node.status === "running" || (index === orderedSteps.length - 1 && step.node.status === "pending"));
        
        return (
          <AgentTraceStep
            key={`${step.node.id}-${index}`}
            node={step.node}
            isNew={isNew}
            isRunning={isCurrentlyRunning}
            indent={step.indent}
          />
        );
      }

      case "group_start":
        // Parallel execution group label
        // Requirement 6.4: Visually indicate parallel execution through layout
        return (
          <li
            key={`group-start-${step.groupId}`}
            className="mb-1 mt-2 text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim/70"
            role="heading"
            aria-level={3}
          >
            {step.label}
          </li>
        );

      case "group_end":
        // Parallel execution group end (visual spacing)
        // Requirement 6.4: Visual indication of parallel execution
        return (
          <li
            key={`group-end-${step.groupId}`}
            className="mb-1"
            aria-hidden="true"
          />
        );

      case "critic_reinvoke":
        // Critic re-invocation marker
        // Requirements: 5.1 (re-invocations as separate steps),
        //               5.2 (indentation for re-invoked steps),
        //               11.2 (visual distinction for critic_loop)
        return (
          <li
            key={`critic-${index}`}
            className={`mb-1 text-[10px] font-mono text-ink-dim/80 ${
              step.indent === 1 ? "pl-4" : step.indent === 2 ? "pl-8" : ""
            }`}
            role="listitem"
          >
            {step.label}
          </li>
        );

      default:
        return null;
    }
  };

  return (
    <div
      className="agent-trace-expanded rounded-lg border border-hairline/60 bg-shelf-1/40 p-2.5 shadow-sm"
      role="region"
      aria-label="Agent execution steps"
    >
      {/* Header with collapse button */}
      {/* Requirement 2.5: Collapse callback for returning to summary */}
      <div className="mb-2 flex items-center justify-between border-b border-hairline/40 pb-2">
        <h2 className="text-[11px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
          ▾ Agent Reasoning Trace
        </h2>
        <button
          onClick={onCollapse}
          onKeyDown={handleKeyDown}
          className="flex size-6 shrink-0 items-center justify-center rounded border border-hairline/60 bg-shelf-1 text-ink-dim transition-colors hover:border-hairline-strong hover:bg-shelf-2 focus:outline-none focus:ring-2 focus:ring-ocean-cyan/30"
          aria-label="Collapse trace to summary view"
          type="button"
        >
          <X className="size-3.5" aria-hidden="true" />
        </button>
      </div>

      {/* Flat chronological list of agent steps */}
      {/* Requirements:
            - 2.2: Steps in execution order as flat list
            - 2.3: Explicit documentation of flat list structure
            - 2.4: Chronological order based on execution sequence
            - 16.1: Semantic HTML structure (ol/li for steps)
       */}
      <ol className="flex flex-col gap-1" role="list">
        {orderedSteps.length === 0 ? (
          <li className="py-4 text-center text-sm text-ink-dim">
            No agent execution data available
          </li>
        ) : (
          orderedSteps.map((step, index) => renderOrderedStep(step, index))
        )}

        {/* Streaming indicator for next step */}
        {/* Requirement 4.2: Show progress indicator for running agents */}
        {/* Requirement 4.4: Remove progress indicators when all agents complete */}
        {streaming && orderedSteps.length > 0 && (
          <motion.li
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            className="mt-1 flex items-center gap-2 rounded border border-ocean-cyan/40 bg-ocean-cyan/5 px-2 py-1.5 text-[11px] text-ink-dim"
            role="status"
            aria-live="polite"
          >
            <motion.span 
              className="text-ocean-cyan"
              animate={{ opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
            >
              ⟳
            </motion.span>
            <span>Processing...</span>
          </motion.li>
        )}
      </ol>

      {/* ARIA live region for streaming updates */}
      {/* Requirement 16.3: Announce state changes via aria-live regions */}
      {streaming && (
        <div className="sr-only" aria-live="polite" aria-atomic="false">
          Agents are still working
        </div>
      )}
    </div>
  );
}
