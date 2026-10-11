"use client";

// AgentTraceCollapsed — Summary view for the Agent Trace UI
//
// Displays a collapsed, single-line view showing total execution time
// in the format "Worked for {N}s". This component renders above the
// answer content and provides a minimal, professional interface that
// indicates expandability on hover.
//
// The component calculates total execution time by summing all agent
// latency_ms values from the spans array and formats the time appropriately
// (milliseconds vs seconds). When streaming is active, it shows a progress
// indicator.
//
// Requirements fulfilled:
// - 1.1: Display collapsed view showing total execution time
// - 1.2: Calculate total time by summing latency_ms values
// - 1.3: Display as single line above answer content
// - 1.4: Minimal, professional visual style
// - 1.5: Indicate expandability on hover

import React from "react";
import { ChevronRight } from "lucide-react";

/**
 * Props for the collapsed summary view component
 */
export interface AgentTraceCollapsedProps {
  /** Total execution time in milliseconds (sum of all agent latency_ms) */
  totalTimeMs: number;
  /** Whether agents are still running (show progress indicator) */
  streaming: boolean;
  /** Callback when user clicks to expand */
  onExpand: () => void;
}

/**
 * AgentTraceCollapsed - Summary view showing total execution time
 *
 * Displays "Worked for {N}s" in a collapsed, clickable format.
 * Indicates expandability through chevron icon and hover states.
 *
 * Requirements fulfilled:
 * - 1.1: Display total execution time
 * - 1.2: Time from sum of latency_ms values
 * - 1.3: Single line display
 * - 1.4: Minimal, professional styling (shelf-1/40 bg, subtle border)
 * - 1.5: Hover states indicate expandability
 */
export function AgentTraceCollapsed({
  totalTimeMs,
  streaming,
  onExpand,
}: AgentTraceCollapsedProps) {
  /**
   * Format duration in milliseconds to human-readable string
   * Requirement 1.1: Display time as "Worked for {N}s"
   *
   * @param ms - Duration in milliseconds
   * @returns Formatted string like "3.2s" or "450ms"
   */
  const formatDuration = (ms: number): string => {
    if (ms < 1000) {
      return `${Math.round(ms)}ms`;
    }
    return `${(ms / 1000).toFixed(1)}s`;
  };

  /**
   * Handle keyboard accessibility
   * Requirement 1.5: Keyboard accessible (Enter/Space triggers expand)
   */
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onExpand();
    }
  };

  return (
    <button
      onClick={onExpand}
      onKeyDown={handleKeyDown}
      className="group w-full cursor-pointer rounded-lg border border-hairline/60 bg-shelf-1/40 px-4 py-2 text-left text-xs font-medium text-ink-dim shadow-2xs transition-all duration-150 hover:border-hairline-strong hover:shadow-xs focus:outline-none focus:ring-2 focus:ring-ocean-cyan/30 focus:ring-offset-2"
      aria-expanded={false}
      aria-label={`Agent trace: worked for ${formatDuration(totalTimeMs)}. Click to expand details.`}
      type="button"
    >
      <span className="inline-flex items-center gap-2">
        {/* Chevron icon to indicate expandability (Requirement 1.5) */}
        <ChevronRight
          className="size-3.5 shrink-0 text-ink-dim transition-transform duration-150 group-hover:text-ink"
          aria-hidden="true"
        />

        {/* Total execution time display (Requirements 1.1, 1.2) */}
        <span>Worked for {formatDuration(totalTimeMs)}</span>

        {/* Streaming progress indicator (Requirement 1.5) */}
        {streaming && (
          <span className="inline-flex items-center gap-1" aria-label="Still working">
            <span className="animate-pulse text-ocean-cyan" aria-hidden="true">
              ⟳
            </span>
          </span>
        )}
      </span>
    </button>
  );
}
