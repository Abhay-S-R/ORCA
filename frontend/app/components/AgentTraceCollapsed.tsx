"use client";

// AgentTraceCollapsed — Summary trigger for expanding the narrative trace
//
// Displays a minimal "▸ Thought for Xs" clickable line (ChatGPT-style).
// When streaming, shows "Thinking…" with a subtle animated indicator.

import React from "react";

export interface AgentTraceCollapsedProps {
  /** Total execution time in milliseconds (sum of all agent latency_ms) */
  totalTimeMs: number;
  /** Whether agents are still running */
  streaming: boolean;
  /** Callback when user clicks to expand */
  onExpand: () => void;
  /** Optional button ref for keyboard focus restoration */
  buttonRef?: React.RefObject<HTMLButtonElement | null>;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function AgentTraceCollapsed({
  totalTimeMs,
  streaming,
  onExpand,
  buttonRef,
}: AgentTraceCollapsedProps) {
  return (
    <button
      ref={buttonRef}
      onClick={onExpand}
      className="group flex items-center gap-1.5 text-[11px] sm:text-xs font-medium text-ink-dim hover:text-ink transition-colors cursor-pointer py-1"
      aria-expanded={false}
      aria-controls="agent-trace-expanded-region"
      aria-label={
        streaming
          ? "Thinking. Click to expand details."
          : `Thought for ${formatDuration(totalTimeMs)}. Click to expand details.`
      }
      type="button"
    >
      {/* Expand chevron */}
      <span className="select-none transition-transform duration-150 group-hover:translate-x-0.5">
        ▸
      </span>

      {streaming ? (
        <span className="inline-flex items-center gap-1.5">
          <span>Thinking</span>
          <span className="inline-flex gap-0.5">
            <span className="animate-bounce text-ocean-cyan" style={{ animationDelay: "0ms" }}>.</span>
            <span className="animate-bounce text-ocean-cyan" style={{ animationDelay: "150ms" }}>.</span>
            <span className="animate-bounce text-ocean-cyan" style={{ animationDelay: "300ms" }}>.</span>
          </span>
        </span>
      ) : (
        <span>Thought for {formatDuration(totalTimeMs)}</span>
      )}
    </button>
  );
}
