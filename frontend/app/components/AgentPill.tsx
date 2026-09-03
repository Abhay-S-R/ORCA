"use client";

// The live agent activity strip (differentiator 1 — "what makes the UI
// visibly agentic", §4.5). Twelve agents execute per query; this is how a
// user sees that happening instead of watching a spinner.
//
// Status is carried by BOTH a glyph and a colour, and the running state adds
// motion on top — three redundant channels, so reduced-motion and colour
// blindness each still leave two.
import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, Check, Minus, X } from "lucide-react";

export type AgentStatus = "pending" | "running" | "ok" | "degraded" | "failed" | "skipped";

const STATUS: Record<AgentStatus, { cls: string; label: string }> = {
  pending: { cls: "border-hairline text-ink-dim", label: "queued" },
  running: { cls: "border-accent/50 text-accent", label: "running" },
  ok: { cls: "border-hairline-strong text-ink-muted", label: "done" },
  // Agent completed but fell back (e.g. a missing optional model dependency
  // degrading translation to a pass-through) — distinct from "failed", which
  // is what run_traced_node's own exception boundary reports.
  degraded: { cls: "border-caution/45 text-caution", label: "degraded" },
  failed: { cls: "border-no-go/45 text-no-go", label: "failed" },
  skipped: { cls: "border-hairline text-ink-dim", label: "skipped" },
};

export function AgentPill({
  name,
  status,
  latencyMs,
}: {
  name: string;
  status: AgentStatus;
  latencyMs?: number;
}) {
  const { cls, label } = STATUS[status];
  const reduce = useReducedMotion();

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm border bg-shelf-1/60 px-2 py-1 text-[11px] whitespace-nowrap ${cls}`}
      title={`${name} — ${label}`}
    >
      {status === "running" ? (
        <motion.span
          aria-hidden="true"
          className="size-1.5 rounded-full bg-current"
          animate={reduce ? {} : { opacity: [1, 0.25, 1] }}
          transition={{ duration: 1, repeat: Infinity }}
        />
      ) : status === "ok" ? (
        <Check className="size-3" aria-hidden="true" />
      ) : status === "degraded" ? (
        <AlertTriangle className="size-3" aria-hidden="true" />
      ) : status === "failed" ? (
        <X className="size-3" aria-hidden="true" />
      ) : (
        <Minus className="size-3" aria-hidden="true" />
      )}
      <span className="font-medium">{name}</span>
      <span className="sr-only">{label}</span>
      {latencyMs != null && status === "ok" && (
        <span data-readout className="text-[10px] text-ink-dim">
          {latencyMs}ms
        </span>
      )}
    </span>
  );
}

export function AgentStrip({ children }: { children: React.ReactNode }) {
  return (
    <div
      aria-live="polite"
      aria-label="Agent activity"
      className="flex flex-wrap gap-1.5"
    >
      {children}
    </div>
  );
}
