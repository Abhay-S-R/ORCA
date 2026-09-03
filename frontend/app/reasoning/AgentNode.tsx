"use client";

// The node IS the deliverable (plan §5.10 Day 16) — not a labelled box, a
// readable summary of what that agent actually did. Border carries
// confidence tier (the design system's own cool ramp — the go/caution/no-go
// triad is reserved exclusively for verdicts, never for a pipeline node,
// per globals.css). Fill carries execution state instead, the same status
// vocabulary AgentPill already uses on the live activity strip. Every
// channel here also has a text form, so none of it is colour alone.
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Anchor, Check, Cloud, Compass, FileText, Languages, ListChecks, ShieldAlert, Sparkles, Waves, X,
} from "lucide-react";
import type { ComponentType } from "react";
import type { AgentStatus } from "../components/AgentPill";
import { confidenceClass, confidenceLabel, type ConfidenceTier } from "../components/Badge";
import type { AgentNodeData } from "./dagre-layout";

export type AgentFlowNode = Node<AgentNodeData, "agent">;

const ICON: Record<string, ComponentType<{ className?: string }>> = {
  distress_check: ShieldAlert, language_ingress: Languages, planning: ListChecks,
  weather_intelligence: Cloud, geospatial: Compass, ocean_analytics: Waves,
  risk_assessment: ShieldAlert, visualization: Sparkles, reporting: FileText, language_egress: Languages,
};

const STATUS_FILL: Record<AgentStatus, string> = {
  pending: "bg-shelf-1/30 opacity-60",
  running: "bg-accent/10",
  ok: "bg-shelf-1/85",
  degraded: "border-caution/40 bg-caution/10",
  failed: "border-dashed bg-no-go/10",
  skipped: "border-dashed bg-shelf-1/20 opacity-50",
};

const CONFIDENCE_BORDER: Record<ConfidenceTier, string> = {
  HIGH: "border-confidence-high/70",
  MEDIUM: "border-confidence-medium/70",
  LOW_DATA: "border-confidence-low/70",
};

export function AgentNode({ data, selected }: NodeProps<AgentFlowNode>) {
  const { node } = data;
  const Icon = ICON[node.id] ?? Anchor;
  const reduce = useReducedMotion();

  return (
    <div
      className={`h-full w-full overflow-hidden rounded-md border-2 p-2.5 text-left shadow-md shadow-black/30 transition-colors ${CONFIDENCE_BORDER[node.confidence_tier]} ${STATUS_FILL[node.status]} ${selected ? "ring-2 ring-accent ring-offset-2 ring-offset-abyss" : ""}`}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} className="!border-0 !bg-hairline-strong" />
      <Handle type="source" position={Position.Right} isConnectable={false} className="!border-0 !bg-hairline-strong" />

      <div className="flex items-center gap-1.5">
        {node.status === "running" ? (
          <motion.span aria-hidden="true" animate={reduce ? {} : { opacity: [1, 0.3, 1] }} transition={{ duration: 1, repeat: Infinity }}>
            <Icon className="size-3.5 text-accent" />
          </motion.span>
        ) : (
          <Icon className="size-3.5 shrink-0 text-ink-dim" aria-hidden="true" />
        )}
        <span className="truncate text-xs font-semibold text-ink">{node.agent_name}</span>
        {node.status === "failed" && <X className="ml-auto size-3.5 shrink-0 text-no-go" aria-hidden="true" />}
        {node.status === "ok" && <Check className="ml-auto size-3 shrink-0 text-ink-dim" aria-hidden="true" />}
      </div>

      <p className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-ink-muted">{node.reasoning_summary}</p>

      <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px]">
        <span className={confidenceClass(node.confidence_tier)}>{confidenceLabel(node.confidence_tier)}</span>
        <span data-readout className="text-ink-dim">{node.latency_ms}ms</span>
      </div>
      <p className="mt-1 truncate text-[10px] text-ink-dim">
        {node.source_count} source{node.source_count === 1 ? "" : "s"} ·{" "}
        {node.used_llm ? `${node.tier} LLM (${node.model})` : "deterministic · no LLM"}
      </p>
    </div>
  );
}

// A real bounding box around a real parallel group (dagre's compound-graph
// layout, layout.ts), so fan-out is seen, not inferred from edge shape.
export function FanoutGroupNode() {
  return (
    <div className="relative h-full w-full rounded-lg border border-dashed border-hairline-strong bg-shelf-2/10">
      <span className="absolute -top-2.5 left-2 rounded-sm bg-abyss px-1.5 text-[10px] font-medium tracking-wide text-ink-dim">
        parallel fan-out
      </span>
    </div>
  );
}
