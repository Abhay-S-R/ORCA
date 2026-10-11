"use client";

// AgentTraceStep — Individual agent execution step component
//
// Renders a single agent execution step within the expanded trace view.
// Displays status icon, agent name, latency, confidence badge, run count,
// and provides an info tooltip with detailed metadata (engine, model,
// reasoning_summary).
//
// This component handles:
// - Status-based visual indicators and color coding
// - Formatted latency display (1200ms → "1.2s", 450ms → "450ms")
// - Confidence badges (H/M/L) when available
// - Run count badges (×2) for multi-run agents
// - Info tooltip with engine, model, reasoning_summary
// - Indentation levels: 0 (base), 1 (parallel), 2 (critic loop)
// - Accessibility: ARIA labels, semantic HTML, keyboard navigation
//
// Requirements fulfilled: 3.1, 3.2, 3.3, 3.4, 3.5, 9.1, 9.2, 9.3, 9.4, 9.5,
// 10.1, 10.2, 10.3, 10.4, 10.5, 17.1, 17.2, 17.3, 17.4, 17.5

import React, { useState } from "react";
import { motion } from "framer-motion";
import { Check, AlertTriangle, X, Circle, Ban, Loader2, Info } from "lucide-react";
import type { AgentStatus } from "./AgentPill";
import type { ConfidenceTier } from "./Badge";
import type { TraceNode } from "../reasoning/fixture";
import { AGENT_LABEL } from "../reasoning/trace-adapter";

/**
 * Props for individual agent step component
 * 
 * Requirements:
 * - 3.1-3.5: Display agent step content with all metadata
 * - 9.1-9.5: Agent status visualization
 * - 10.1-10.5: Engine and confidence display
 */
export interface AgentTraceStepProps {
  /** TraceNode from TraceGraph */
  node: TraceNode;
  /** Whether this agent is newly added and should animate in */
  isNew?: boolean;
  /** Whether this agent is currently executing */
  isRunning?: boolean;
  /** Indentation level: 0 (base), 1 (parallel), 2 (critic loop) */
  indent?: number;
  /** Optional group label like "Parallel execution (4 agents)" */
  showGroupLabel?: string;
  /** Optional index of this step among all steps */
  stepIndex?: number;
  /** Optional total count of all steps */
  totalSteps?: number;
  /** Key down handler for list keyboard navigation */
  onKeyDown?: (e: React.KeyboardEvent<HTMLLIElement>) => void;
  /** Ref callback for the step listitem DOM node */
  itemRef?: (el: HTMLLIElement | null) => void;
}

// ============================================================================
// Status Icons and Colors
// ============================================================================

/**
 * Status icon mapping
 * Requirement 9.1: Display visual indicators for all status values
 * Requirement 9.3: Use both color and icons for accessibility
 */
const STATUS_ICON: Record<AgentStatus, React.ReactNode> = {
  ok: <Check className="size-3.5 shrink-0" aria-hidden="true" strokeWidth={2.5} />,
  degraded: <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" strokeWidth={2} />,
  failed: <X className="size-3.5 shrink-0" aria-hidden="true" strokeWidth={2.5} />,
  skipped: <Circle className="size-3.5 shrink-0" aria-hidden="true" strokeWidth={2} />,
  cancelled: <Ban className="size-3.5 shrink-0" aria-hidden="true" strokeWidth={2} />,
  running: <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden="true" />,
  pending: <Circle className="size-3.5 shrink-0" aria-hidden="true" strokeWidth={1.5} />,
};

/**
 * Status text labels for screen readers
 * Requirement 9.3: Display status through both color and text
 */
const STATUS_TEXT: Record<AgentStatus, string> = {
  ok: "completed",
  running: "running",
  degraded: "degraded",
  failed: "failed",
  pending: "pending",
  skipped: "skipped",
  cancelled: "cancelled",
};

/**
 * Status color styling
 * Requirement 9.1: Visual indicators for status values
 * Requirement 9.2: Color coding that is WCAG AA compliant
 * Requirement 9.5: Visually emphasize failures
 */
const STATUS_COLOR: Record<AgentStatus, string> = {
  ok: "text-ink",
  degraded: "text-caution",
  failed: "text-no-go",
  skipped: "text-ink-dim/60",
  cancelled: "text-caution/70",
  running: "text-ocean-cyan",
  pending: "text-ink-dim/80",
};

/**
 * Status background styling for the entire step
 * Requirement 9.1-9.5: Status-based visual presentation
 */
const STATUS_BG: Record<AgentStatus, string> = {
  ok: "border-hairline/60 bg-shelf-1/40 hover:bg-shelf-2/50",
  degraded: "border-caution/30 bg-caution/5 hover:bg-caution/10",
  failed: "border-no-go/40 bg-no-go/5 hover:bg-no-go/10",
  skipped: "border-hairline/40 bg-shelf-1/30 opacity-70",
  cancelled: "border-dashed border-caution/40 bg-shelf-1/30 opacity-75",
  running: "border-ocean-cyan/40 bg-ocean-cyan/5 animate-pulse",
  pending: "border-hairline/40 bg-shelf-1/30 opacity-60",
};

// ============================================================================
// Confidence Badge Styling
// ============================================================================

/**
 * Confidence badge colors
 * Requirement 10.2: Display confidence level for completed agents
 * Requirement 9.2: WCAG AA compliant colors
 */
const CONFIDENCE_COLOR: Record<ConfidenceTier, string> = {
  HIGH: "bg-[color-mix(in_oklab,var(--color-confidence-high)_85%,black)] text-white",
  MEDIUM: "bg-[color-mix(in_oklab,var(--color-confidence-medium)_85%,black)] text-white",
  LOW_DATA: "bg-[color-mix(in_oklab,var(--color-confidence-low)_85%,black)] text-white",
};

/**
 * Confidence badge labels
 * Requirement 10.2: Display H/M/L confidence badge
 */
const CONFIDENCE_LABEL: Record<ConfidenceTier, string> = {
  HIGH: "H",
  MEDIUM: "M",
  LOW_DATA: "L",
};

const CONFIDENCE_FULL_LABEL: Record<ConfidenceTier, string> = {
  HIGH: "High",
  MEDIUM: "Medium",
  LOW_DATA: "Low Data",
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Format latency in milliseconds to human-readable string
 * Requirement 3.4: Display execution time in ms or seconds
 * 
 * Examples:
 * - 1200ms → "1.2s"
 * - 450ms → "450ms"
 * - 0ms → "0ms"
 */
function formatLatency(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Get indentation class based on indent level
 * Requirement 3.5: Handle indentation levels (0=base, 1=parallel, 2=critic loop)
 * 
 * @param indent - Indentation level: 0 (base), 1 (parallel), 2 (critic loop)
 */
function getIndentClass(indent: number): string {
  switch (indent) {
    case 0:
      return ""; // Base level, no indentation
    case 1:
      return "pl-4"; // 16px indentation for parallel agents
    case 2:
      return "pl-8"; // 32px indentation for critic loops
    default:
      return "";
  }
}

// ============================================================================
// AgentTraceStep Component
// ============================================================================

/**
 * AgentTraceStep - Renders a single agent execution step
 * 
 * Requirements fulfilled:
 * - 3.1: Display trace_line or reasoning_summary
 * - 3.2: Display reasoning_summary when trace_line not available
 * - 3.3: Display agent name/label
 * - 3.4: Display execution time formatted
 * - 3.5: Display status visually with indentation
 * - 9.1-9.5: Status visualization with icons and colors
 * - 10.1-10.5: Engine and confidence display
 * - 17.1-17.5: Run count display for multi-run agents
 * 
 * MEMOIZATION (Requirement 15.3):
 * This component is wrapped with React.memo to prevent unnecessary re-renders
 * when new steps are added to the trace. Only steps with changed props will
 * re-render, keeping the UI responsive during streaming updates.
 */
function AgentTraceStepComponent({
  node,
  isNew = false,
  isRunning = false,
  indent = 0,
  showGroupLabel,
  stepIndex,
  totalSteps,
  onKeyDown,
  itemRef,
}: AgentTraceStepProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  
  // Determine effective status (override with running if isRunning is true)
  const effectiveStatus = isRunning ? "running" : node.status;
  
  // Determine if agent should show confidence badge
  // Requirement 10.2: Display confidence when available for completed agents
  // Requirement 10.5: Don't show engine/confidence for skipped/cancelled
  const didNotRun = effectiveStatus === "skipped" || effectiveStatus === "cancelled";
  const showConfidence = !didNotRun && 
    (effectiveStatus === "ok" || effectiveStatus === "degraded") &&
    node.confidence_tier;
  
  // Requirement 17.1-17.5: Display run count badge for multi-run agents
  const showRunCount = node.run_count && node.run_count > 1;

  /**
   * Build tooltip content with engine, model, reasoning_summary
   * Requirement 10.1: Display engine field when available
   * Requirement 10.3: Display in non-intrusive way (tooltip)
   * Requirement 10.4: Indicate model tier when available
   * Requirement 10.5: Don't show engine for skipped/cancelled
   */
  const getTooltipContent = () => {
    const parts: string[] = [];
    
    // Status and skip reason
    // Requirement 9.4: Display skip_reason for skipped/cancelled
    if (didNotRun && node.skip_reason) {
      parts.push(`${STATUS_TEXT[effectiveStatus]}: ${node.skip_reason}`);
    } else {
      parts.push(STATUS_TEXT[effectiveStatus]);
    }
    
    // Engine information (only for agents that ran)
    // Requirement 10.1, 10.4: Display engine and model tier
    if (!didNotRun && node.engine) {
      parts.push(`Engine: ${node.engine}`);
      if (node.model) {
        parts.push(`Model: ${node.model}`);
      }
      if (node.tier) {
        parts.push(`Tier: ${node.tier}`);
      }
    }
    
    // Confidence
    if (showConfidence) {
      parts.push(`Confidence: ${CONFIDENCE_FULL_LABEL[node.confidence_tier]}`);
    }
    
    // Run count
    // Requirement 17.3: Explain multi-run indicates critic refinement
    if (showRunCount) {
      parts.push(`Ran ${node.run_count} times (critic-driven refinement)`);
    }
    
    // Reasoning summary
    // Requirement 3.1, 3.2: Display reasoning_summary
    if (node.reasoning_summary) {
      parts.push(`Summary: ${node.reasoning_summary}`);
    }
    
    return parts.join("\n");
  };

  const displayName = AGENT_LABEL[node.agent_name] ?? AGENT_LABEL[node.id] ?? node.agent_name;

  /**
   * Build ARIA label for accessibility
   * Requirement 16.2: Use ARIA labels to describe steps
   * Requirement 16.3: Announce relationships (parallel, critic loop)
   */
  const getAriaLabel = () => {
    const parts = [
      displayName,
      STATUS_TEXT[effectiveStatus],
      node.latency_ms > 0 ? formatLatency(node.latency_ms) : null,
    ].filter(Boolean);
    
    if (indent === 1) {
      parts.push("parallel execution");
    } else if (indent === 2) {
      parts.push("re-invoked under critic loop");
    }

    if (showConfidence) {
      parts.push(`${CONFIDENCE_FULL_LABEL[node.confidence_tier]} confidence`);
    }
    
    if (showRunCount) {
      parts.push(`ran ${node.run_count} times`);
    }

    if (stepIndex !== undefined && totalSteps !== undefined) {
      parts.push(`step ${stepIndex + 1} of ${totalSteps}`);
    }
    
    return parts.join(", ");
  };

  /**
   * Keyboard handler for step item
   * Requirement 16.4: Enter/Space toggles tooltip details, Escape closes tooltip
   */
  const handleStepKeyDown = (e: React.KeyboardEvent<HTMLLIElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setShowTooltip((prev) => !prev);
    } else if (e.key === "Escape" && showTooltip) {
      e.stopPropagation();
      setShowTooltip(false);
    }
    onKeyDown?.(e);
  };

  return (
    <>
      {/* Group label (if provided) */}
      {/* Requirement 6.4: Visually indicate parallel execution */}
      {showGroupLabel && (
        <div 
          className="mb-1 text-[9px] sm:text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim/70"
          role="heading"
          aria-level={3}
        >
          {showGroupLabel}
        </div>
      )}

      {/* Agent step container */}
      {/* Requirement 16.1: Semantic HTML structure (li element) */}
      {/* Requirement 16.4: Accessible keyboard navigation focus and interactions */}
      <motion.li
        ref={itemRef}
        tabIndex={0}
        onKeyDown={handleStepKeyDown}
        initial={isNew ? { opacity: 0, x: -8 } : undefined}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.15 }}
        className={`group relative flex items-center gap-1.5 sm:gap-2 rounded border px-1.5 py-2 sm:px-2 sm:py-1.5 transition-colors duration-150 min-h-[48px] sm:min-h-[44px] focus:outline-none focus:ring-2 focus:ring-ocean-cyan/50 focus:ring-offset-1 ${STATUS_BG[effectiveStatus]} ${getIndentClass(indent)}`}
        aria-label={getAriaLabel()}
        role="listitem"
      >
        {/* Status icon */}
        {/* Requirement 9.1, 9.3: Visual indicator with icon and color */}
        <span className={`shrink-0 ${STATUS_COLOR[effectiveStatus]}`}>
          {STATUS_ICON[effectiveStatus]}
        </span>

        {/* Agent name */}
        {/* Requirement 3.3: Display agent name/label */}
        <span className="flex-1 truncate text-[10px] sm:text-[11px] lg:text-xs font-medium text-ink">
          {displayName}
        </span>

        {/* Latency display */}
        {/* Requirement 3.4: Display execution time formatted */}
        {node.latency_ms > 0 && (
          <span className="shrink-0 text-[9px] sm:text-[10px] font-mono text-ink-muted">
            {formatLatency(node.latency_ms)}
          </span>
        )}

        {/* Confidence badge */}
        {/* Requirement 10.2: Display confidence badge (H/M/L) when available */}
        {showConfidence && (
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-mono font-bold tracking-wide ${CONFIDENCE_COLOR[node.confidence_tier]}`}
            aria-label={`${CONFIDENCE_FULL_LABEL[node.confidence_tier]} confidence`}
            title={`${CONFIDENCE_FULL_LABEL[node.confidence_tier]} confidence`}
          >
            {CONFIDENCE_LABEL[node.confidence_tier]}
          </span>
        )}

        {/* Run count badge */}
        {/* Requirement 17.1: Display visual indicator when run_count > 1 */}
        {/* Requirement 17.5: Show run count prominently near agent name */}
        {showRunCount && (
          <span
            className="shrink-0 rounded border border-hairline bg-shelf-3 px-1 text-[8px] font-mono font-bold text-ink-muted"
            aria-label={`Ran ${node.run_count} times`}
            title={`Ran ${node.run_count} times, re-invoked after critic critique`}
          >
            ×{node.run_count}
          </span>
        )}

        {/* Info icon with tooltip */}
        {/* Requirement 10.3: Display engine, model, reasoning_summary in tooltip */}
        <button
          className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
          onFocus={() => setShowTooltip(true)}
          onBlur={() => setShowTooltip(false)}
          aria-label="Show step details"
          type="button"
        >
          <Info className="size-3.5 text-ink-dim hover:text-ink" aria-hidden="true" />
        </button>

        {/* Tooltip */}
        {showTooltip && (
          <div
            className="absolute right-0 top-full z-10 mt-1 w-52 sm:w-64 lg:w-72 rounded-lg border border-hairline bg-shelf-3 p-2 text-[9px] sm:text-[10px] leading-relaxed text-ink shadow-md"
            role="tooltip"
          >
            <pre className="whitespace-pre-wrap font-sans">{getTooltipContent()}</pre>
          </div>
        )}

        {/* Screen reader only text with full details */}
        {/* Requirement 16.3: Screen reader text for step relationships */}
        <span className="sr-only">
          {node.reasoning_summary && `. ${node.reasoning_summary}`}
          {didNotRun && node.skip_reason && `. Reason: ${node.skip_reason}`}
        </span>
      </motion.li>
    </>
  );
}

/**
 * Export memoized version to prevent re-rendering completed steps
 * Requirement 15.3: Use memoization to prevent re-rendering completed steps
 * 
 * The comparison function checks if node.id and isRunning have changed.
 * This ensures completed steps don't re-render when new steps are added.
 */
export const AgentTraceStep = React.memo(
  AgentTraceStepComponent,
  (prevProps, nextProps) => {
    // Re-render only if these props change
    return (
      prevProps.node.id === nextProps.node.id &&
      prevProps.isRunning === nextProps.isRunning &&
      prevProps.indent === nextProps.indent &&
      prevProps.showGroupLabel === nextProps.showGroupLabel &&
      prevProps.node.status === nextProps.node.status &&
      prevProps.node.latency_ms === nextProps.node.latency_ms &&
      prevProps.stepIndex === nextProps.stepIndex &&
      prevProps.totalSteps === nextProps.totalSteps
    );
  }
);

AgentTraceStep.displayName = "AgentTraceStep";
