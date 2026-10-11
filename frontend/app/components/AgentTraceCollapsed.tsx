"use client";

// AgentTraceCollapsed — Single-line summary trigger for the narrative trace
//
// Matches response font size (text-sm leading-relaxed).
// Starts with "Thinking…", dynamically updates to show the current active
// action in real-time with a left-to-right text shimmer loading animation.
// When finished, displays "Thought for Xs". Clicking expands previous traces.

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { formatDuration } from "./AgentTraceExpanded";

export interface AgentTraceCollapsedProps {
  /** Total execution time in milliseconds */
  totalTimeMs: number;
  /** Whether agents are still running */
  streaming: boolean;
  /** Current trace text to display on the single line */
  currentText?: string;
  /** Callback when user clicks to expand */
  onExpand: () => void;
  /** Optional button ref for keyboard focus restoration */
  buttonRef?: React.RefObject<HTMLButtonElement | null>;
}

export function AgentTraceCollapsed({
  totalTimeMs,
  streaming,
  currentText = "Thinking…",
  onExpand,
  buttonRef,
}: AgentTraceCollapsedProps) {
  const displayText = streaming
    ? currentText
    : `Thought for ${formatDuration(totalTimeMs)}`;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onExpand();
    }
  };

  return (
    <button
      ref={buttonRef}
      onClick={onExpand}
      onKeyDown={handleKeyDown}
      className="group flex items-center gap-2 text-sm leading-relaxed font-normal text-ink-dim hover:text-ink transition-colors cursor-pointer py-1 text-left"
      aria-expanded={false}
      aria-controls="agent-trace-expanded-region"
      aria-label={
        streaming
          ? `${displayText}. Click to view reasoning trace.`
          : `${displayText}. Click to view reasoning trace.`
      }
      type="button"
    >
      {/* Expand chevron */}
      <span className="select-none transition-transform duration-150 group-hover:translate-x-0.5 text-xs text-ink-dim shrink-0">
        ▸
      </span>

      {/* Dynamic single line text */}
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={streaming ? displayText : "done"}
          initial={{ opacity: 0, y: 3 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -3 }}
          transition={{ duration: 0.18 }}
          className={
            streaming
              ? "text-shimmer font-medium"
              : "text-ink-dim group-hover:text-ink transition-colors"
          }
        >
          {displayText}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
