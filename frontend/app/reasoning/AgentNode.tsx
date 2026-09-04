"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  Anchor,
  Check,
  CheckCheck,
  Clock,
  Cloud,
  Compass,
  Cpu,
  Database,
  Eye,
  FileText,
  Languages,
  Layers,
  ListChecks,
  Loader2,
  ShieldAlert,
  Sparkles,
  Waves,
  X,
} from "lucide-react";
import type { ComponentType } from "react";
import type { AgentStatus } from "../components/AgentPill";
import { confidenceClass, confidenceLabel, type ConfidenceTier } from "../components/Badge";
import type { AgentNodeData } from "./dagre-layout";

export type AgentFlowNode = Node<AgentNodeData, "agent">;

const ICON: Record<string, ComponentType<{ className?: string }>> = {
  distress: ShieldAlert,
  distress_check: ShieldAlert,
  language_ingress: Languages,
  planning: ListChecks,
  weather_intelligence: Cloud,
  geospatial: Compass,
  ocean_analytics: Waves,
  risk_assessment: ShieldAlert,
  visualization: Sparkles,
  reporting: FileText,
  critic: Eye,
  language_egress: Languages,
};

const STATUS_CONFIG: Record<
  AgentStatus,
  { border: string; bg: string; glow: string; label: string }
> = {
  pending: {
    border: "border-hairline/80",
    bg: "bg-shelf-1/40 opacity-70",
    glow: "",
    label: "Queued",
  },
  running: {
    border: "border-sky-400",
    bg: "bg-sky-950/40",
    glow: "shadow-[0_0_25px_rgba(56,189,248,0.35)] ring-1 ring-sky-400/50",
    label: "Running",
  },
  ok: {
    border: "border-hairline-strong",
    bg: "bg-shelf-1/90",
    glow: "shadow-[0_8px_20px_-6px_rgba(0,0,0,0.6)]",
    label: "Completed",
  },
  degraded: {
    border: "border-caution/70",
    bg: "bg-caution/10",
    glow: "shadow-[0_0_20px_rgba(251,191,36,0.25)]",
    label: "Degraded",
  },
  failed: {
    border: "border-no-go/80",
    bg: "bg-no-go/15",
    glow: "shadow-[0_0_20px_rgba(255,92,92,0.3)]",
    label: "Failed",
  },
  skipped: {
    border: "border-dashed border-hairline",
    bg: "bg-shelf-1/20 opacity-40",
    glow: "",
    label: "Skipped",
  },
};

const CONFIDENCE_ACCENT: Record<ConfidenceTier, string> = {
  HIGH: "border-l-sky-400",
  MEDIUM: "border-l-indigo-400",
  LOW_DATA: "border-l-amber-400",
};

export function formatReasoningSummary(summary?: string): string {
  if (!summary) return "";
  // If summary contains raw python dict dump like Tide: {'...'}
  if (summary.includes("{'") || summary.includes('{"')) {
    const tideMatch = summary.match(/Tide:\s*\{([^}]+)\}(?:\s*·\s*(.*))?/);
    if (tideMatch) {
      const inner = tideMatch[1];
      const rest = tideMatch[2] ? ` · ${tideMatch[2]}` : "";
      const stateMatch = inner.match(/['"]tidal_state['"]:\s*['"]([^'"]+)['"]/);
      const stationMatch = inner.match(/['"]station_name['"]:\s*['"]([^'"]+)['"]/);
      const state = stateMatch ? stateMatch[1] : "Slack tide";
      const station = stationMatch ? ` (${stationMatch[1]})` : "";
      return `Tide: ${state}${station}${rest}`;
    }
  }
  return summary;
}

export function AgentNode({ data, selected }: NodeProps<AgentFlowNode>) {
  const { node } = data;
  const Icon = ICON[node.id] ?? ICON[node.agent_name.toLowerCase().replace(/ /g, "_")] ?? Anchor;
  const reduce = useReducedMotion();
  const statusCfg = STATUS_CONFIG[node.status] ?? STATUS_CONFIG.pending;
  const isRunning = node.status === "running";
  const isOk = node.status === "ok";
  const isFailed = node.status === "failed";
  const isDegraded = node.status === "degraded";

  return (
    <div
      className={`relative h-[124px] w-[270px] min-w-[270px] max-w-[270px] select-none overflow-hidden rounded-xl border border-t-white/10 p-3 text-left backdrop-blur-md transition-all duration-200 ${statusCfg.border} ${statusCfg.bg} ${statusCfg.glow} ${CONFIDENCE_ACCENT[node.confidence_tier]} border-l-4 ${selected ? "!border-accent ring-2 ring-accent ring-offset-2 ring-offset-abyss scale-[1.02]" : "hover:border-hairline-strong"}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        isConnectable={false}
        className="!size-2 !-left-1 !border-0 !bg-sky-400/80 shadow-sm"
      />
      <Handle
        type="source"
        position={Position.Right}
        isConnectable={false}
        className="!size-2 !-right-1 !border-0 !bg-sky-400/80 shadow-sm"
      />

      {/* Top row: Icon, Name, and Status Glyph */}
      <div className="flex items-center justify-between gap-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={`grid size-6 shrink-0 place-items-center rounded-md border ${isRunning ? "border-sky-400/60 bg-sky-900/50 text-sky-400" : isOk ? "border-hairline-strong bg-shelf-2/80 text-ink" : "border-hairline bg-shelf-2/40 text-ink-dim"}`}
          >
            {isRunning ? (
              <motion.div
                animate={reduce ? {} : { rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
              >
                <Loader2 className="size-3.5 text-sky-400" />
              </motion.div>
            ) : (
              <Icon className="size-3.5" />
            )}
          </div>
          <span className="truncate text-[12px] font-semibold tracking-tight text-ink">
            {node.agent_name}
          </span>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {isRunning && (
            <motion.span
              animate={reduce ? {} : { opacity: [1, 0.4, 1] }}
              transition={{ duration: 0.8, repeat: Infinity }}
              className="rounded-full bg-sky-400/20 px-1.5 py-0.5 text-[9px] font-medium tracking-wide text-sky-400 border border-sky-400/40"
            >
              RUNNING
            </motion.span>
          )}
          {isOk && (
            <span className="grid size-4 place-items-center rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
              <Check className="size-2.5" />
            </span>
          )}
          {isDegraded && (
            <span className="grid size-4 place-items-center rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
              <AlertTriangle className="size-2.5" />
            </span>
          )}
          {isFailed && (
            <span className="grid size-4 place-items-center rounded-full bg-red-500/15 text-red-400 border border-red-500/30">
              <X className="size-2.5" />
            </span>
          )}
        </div>
      </div>

      {/* Middle row: Reasoning summary */}
      <p className="mt-1.5 line-clamp-2 min-h-[28px] text-[11px] leading-snug text-ink-muted break-words overflow-hidden">
        {formatReasoningSummary(node.reasoning_summary) || "Awaiting pipeline inputs..."}
      </p>

      {/* Bottom row: Confidence, Latency, and Architecture Badge */}
      <div className="mt-2.5 flex items-center justify-between gap-1 border-t border-hairline/60 pt-2 text-[10px]">
        <div className="flex items-center gap-1.5">
          <span className={confidenceClass(node.confidence_tier)}>
            {confidenceLabel(node.confidence_tier)}
          </span>
          {node.latency_ms !== null && node.latency_ms !== undefined && (
            <span
              data-readout
              className="inline-flex items-center gap-0.5 text-ink-dim font-mono"
            >
              <Clock className="size-2.5" />
              {node.latency_ms}ms
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 text-[9px]">
          {node.used_llm ? (
            <span
              className="inline-flex items-center gap-1 rounded bg-purple-950/50 border border-purple-800/40 px-1.5 py-0.5 text-purple-300 font-mono"
              title={`LLM Model: ${node.model || "gemini-3.5-flash-lite"} (${node.tier || "mid"} tier)`}
            >
              <Cpu className="size-2.5 shrink-0" />
              <span>{node.model || "gemini-3.5-flash-lite"}</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded bg-sky-950/40 border border-sky-800/30 px-1 py-0.5 text-sky-300 font-mono">
              Deterministic
            </span>
          )}
          {node.source_count > 0 && (
            <span className="inline-flex items-center gap-0.5 text-ink-dim font-mono">
              <Database className="size-2.5" />
              {node.source_count}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function FanoutGroupNode({ data }: NodeProps) {
  const label = (data as { label?: string })?.label || "Parallel Specialists · 3 Concurrent Streams";
  return (
    <div className="relative h-full w-full rounded-2xl border border-dashed border-sky-500/25 bg-shelf-2/10 backdrop-blur-[2px]">
      <div className="absolute -top-3 left-4 flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-abyss px-2.5 py-0.5 text-[10px] font-medium tracking-wide text-sky-300 shadow-md">
        <Layers className="size-3 text-sky-400" />
        <span>{label}</span>
      </div>
    </div>
  );
}
