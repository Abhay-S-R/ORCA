"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  Anchor,
  Check,
  Cloud,
  Compass,
  Database,
  Eye,
  FileText,
  Languages,
  Layers,
  ListChecks,
  Loader2,
  Radar,
  ShieldAlert,
  Sparkles,
  Waves,
  X,
} from "lucide-react";
import type { ComponentType } from "react";
import type { AgentStatus } from "../components/AgentPill";
import { confidenceClass, confidenceLabel } from "../components/Badge";
import type { AgentNodeData } from "./dagre-layout";

export type AgentFlowNode = Node<AgentNodeData, "agent">;

const ICON: Record<string, ComponentType<{ className?: string }>> = {
  distress: ShieldAlert,
  marine_data_discovery: Database,
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
  sentinel: Radar,
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
    border: "border-ocean-cyan",
    bg: "bg-ocean-cyan/5",
    glow: "ring-1 ring-ocean-cyan/40",
    label: "Running",
  },
  ok: {
    border: "border-hairline-strong",
    bg: "bg-shelf-1/90",
    glow: "shadow-sm",
    label: "Completed",
  },
  degraded: {
    border: "border-caution/70",
    bg: "bg-caution/10",
    glow: "",
    label: "Degraded",
  },
  failed: {
    border: "border-no-go/80",
    bg: "bg-no-go/10",
    glow: "",
    label: "Failed",
  },
  skipped: {
    border: "border-dashed border-hairline",
    bg: "bg-shelf-1/20 opacity-40",
    glow: "",
    label: "Skipped",
  },
  // P2.12 (orca_final §4.1, §24) — drawn dotted and in the caution hue, not
  // faded away like a skip. The two mean different things: a skip is work the
  // plan never asked for, a cancellation is work that was pending when a hard
  // constraint (a red/orange cyclone, lightning, an IMBL or MPA breach) made
  // it pointless. A judge should be able to see that decision being made.
  cancelled: {
    border: "border-dotted border-caution/60",
    bg: "bg-caution/5 opacity-70",
    glow: "",
    label: "Cancelled",
  },
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
  const isSentinel = node.id === "sentinel" || node.agent_name.toLowerCase().includes("sentinel");
  const Icon = ICON[node.id] ?? ICON[node.agent_name.toLowerCase().replace(/ /g, "_")] ?? Anchor;
  const reduce = useReducedMotion();
  const statusCfg = STATUS_CONFIG[node.status] ?? STATUS_CONFIG.pending;
  const isRunning = node.status === "running";
  const isOk = node.status === "ok";
  const isFailed = node.status === "failed";
  const isDegraded = node.status === "degraded";

  return (
    <div className={`relative ${isSentinel ? "overflow-visible" : ""}`}>
      {/* Animated glowing border and outer bloom for Sentinel background daemon */}
      {isSentinel && (
        <>
          {/* Deep ambient luminous bloom spreading outward */}
          <motion.div
            aria-hidden="true"
            animate={
              reduce
                ? {}
                : {
                    opacity: [0.55, 0.95, 0.55],
                    scale: [0.99, 1.025, 0.99],
                    boxShadow: [
                      "0 0 16px 2px rgba(6, 182, 212, 0.4), 0 0 32px 6px rgba(6, 182, 212, 0.25)",
                      "0 0 28px 4px rgba(6, 182, 212, 0.8), 0 0 56px 12px rgba(6, 182, 212, 0.45)",
                      "0 0 16px 2px rgba(6, 182, 212, 0.4), 0 0 32px 6px rgba(6, 182, 212, 0.25)",
                    ],
                  }
            }
            transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
            className="pointer-events-none absolute -inset-1 rounded-2xl bg-ocean-cyan/20 blur-md"
          />

          {/* High-intensity glowing neon border ring */}
          <motion.div
            aria-hidden="true"
            animate={
              reduce
                ? {}
                : {
                    borderColor: [
                      "rgba(6, 182, 212, 0.7)",
                      "rgba(6, 182, 212, 1)",
                      "rgba(6, 182, 212, 0.7)",
                    ],
                    boxShadow: [
                      "0 0 12px rgba(6, 182, 212, 0.6), inset 0 0 8px rgba(6, 182, 212, 0.3)",
                      "0 0 26px rgba(6, 182, 212, 0.95), inset 0 0 16px rgba(6, 182, 212, 0.55)",
                      "0 0 12px rgba(6, 182, 212, 0.6), inset 0 0 8px rgba(6, 182, 212, 0.3)",
                    ],
                  }
            }
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
            className="pointer-events-none absolute -inset-[1px] z-10 rounded-xl border-2 border-ocean-cyan"
          />
        </>
      )}

      {/* Main Card */}
      <div
        className={`relative h-[124px] w-[270px] min-w-[270px] max-w-[270px] select-none overflow-hidden rounded-xl border p-3 text-left backdrop-blur-md transition-all duration-200 ${
          isSentinel
            ? "border-ocean-cyan/90 bg-shelf-1/95 ring-1 ring-ocean-cyan/70 shadow-lg"
            : `${statusCfg.border} ${statusCfg.bg} ${statusCfg.glow}`
        } ${selected ? "!border-accent ring-2 ring-accent ring-offset-2 ring-offset-shelf-1 scale-[1.02]" : "hover:border-hairline-strong"}`}
      >
        {/* Subtle scanning sweep for Sentinel */}
        {isSentinel && (
          <>
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(6,182,212,0.18),transparent_70%)]"
            />
            <motion.div
              aria-hidden="true"
              animate={reduce ? {} : { x: ["-120%", "220%"] }}
              transition={{ duration: 3.2, repeat: Infinity, ease: "linear" }}
              className="pointer-events-none absolute -inset-y-2 w-14 -skew-x-12 bg-gradient-to-r from-transparent via-ocean-cyan/25 to-transparent"
            />
          </>
        )}

        {/* Handles only for pipeline nodes; independent Sentinel has no wire handles */}
        {!isSentinel && (
          <>
            <Handle
              type="target"
              position={Position.Left}
              isConnectable={false}
              className="!size-2 !-left-1 !border-0 !bg-ocean-cyan/80 shadow-sm"
            />
            <Handle
              type="source"
              position={Position.Right}
              isConnectable={false}
              className="!size-2 !-right-1 !border-0 !bg-ocean-cyan/80 shadow-sm"
            />
          </>
        )}

        {/* Top row: Icon, Name, and Status Glyph */}
        <div className="flex items-center justify-between gap-1.5">
          <div className="flex items-center gap-2 min-w-0">
            <div
              className={`grid size-6 shrink-0 place-items-center rounded-md border ${
                isSentinel
                  ? "border-ocean-cyan/70 bg-ocean-cyan/20 text-ocean-cyan shadow-[0_0_10px_rgba(6,182,212,0.5)]"
                  : isRunning
                  ? "border-ocean-cyan/60 bg-ocean-cyan/10 text-ocean-cyan"
                  : isOk
                  ? "border-hairline-strong bg-shelf-2/80 text-ink"
                  : "border-hairline bg-shelf-2/40 text-ink-dim"
              }`}
            >
              {isSentinel ? (
                <motion.div
                  animate={reduce ? {} : { rotate: 360 }}
                  transition={{ duration: 3.5, repeat: Infinity, ease: "linear" }}
                  className="text-ocean-cyan"
                >
                  <Radar className="size-3.5 text-ocean-cyan" />
                </motion.div>
              ) : isRunning ? (
                <motion.div
                  animate={reduce ? {} : { rotate: 360 }}
                  transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                >
                  <Loader2 className="size-3.5 text-ocean-cyan" />
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
            {isSentinel ? (
              <span className="flex items-center gap-1.5 rounded-full bg-ocean-cyan/25 px-2 py-0.5 text-[9px] font-bold tracking-wider text-ocean-cyan border border-ocean-cyan/60 shadow-[0_0_10px_rgba(6,182,212,0.4)]">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ocean-cyan opacity-90"></span>
                  <span className="relative inline-flex size-2 rounded-full bg-ocean-cyan"></span>
                </span>
                RUNNING IN BACKGROUND
              </span>
            ) : isRunning ? (
              <motion.span
                animate={reduce ? {} : { opacity: [1, 0.4, 1] }}
                transition={{ duration: 0.8, repeat: Infinity }}
                className="rounded-full bg-ocean-cyan/10 px-1.5 py-0.5 text-[9px] font-medium tracking-wide text-ocean-cyan border border-ocean-cyan/40"
              >
                RUNNING
              </motion.span>
            ) : isOk ? (
              <span className="grid size-4 place-items-center rounded-full bg-go/15 text-go border border-go/30">
                <Check className="size-2.5" />
              </span>
            ) : isDegraded ? (
              <span className="grid size-4 place-items-center rounded-full bg-caution/15 text-caution border border-caution/30">
                <AlertTriangle className="size-2.5" />
              </span>
            ) : isFailed ? (
              <span className="grid size-4 place-items-center rounded-full bg-no-go/15 text-no-go border border-no-go/30">
                <X className="size-2.5" />
              </span>
            ) : null}
          </div>
        </div>

        {/* Middle row: Reasoning summary */}
        <p className="mt-1.5 line-clamp-2 min-h-[28px] text-[11px] leading-snug text-ink-muted break-words overflow-hidden">
          {formatReasoningSummary(node.reasoning_summary) || "Awaiting pipeline inputs..."}
        </p>

        {/* Bottom row: Independent Sentinel badge vs Confidence */}
        {isSentinel ? (
          <div className="mt-2.5 flex items-center justify-between gap-1 border-t border-ocean-cyan/40 pt-2 text-[10px]">
            <span className="inline-flex items-center gap-1.5 font-mono text-ocean-cyan text-[10px] font-semibold">
              <span className="size-1.5 rounded-full bg-ocean-cyan animate-pulse shadow-[0_0_6px_rgba(6,182,212,0.8)]" />
              INDEPENDENT DAEMON
            </span>
            <span className="rounded bg-ocean-cyan/15 px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wide text-ocean-cyan border border-ocean-cyan/40">
              AUTONOMOUS 24/7
            </span>
          </div>
        ) : (
          <div className="mt-2.5 flex items-center justify-between gap-1 border-t border-hairline/60 pt-2 text-[10px]">
            <span className={confidenceClass(node.confidence_tier)}>
              {confidenceLabel(node.confidence_tier)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export function FanoutGroupNode({ data }: NodeProps) {
  const label = (data as { label?: string })?.label || "Parallel Specialists · 3 Concurrent Streams";
  return (
    <div className="relative h-full w-full rounded-2xl border border-dashed border-ocean-cyan/30 bg-shelf-2/10 backdrop-blur-[2px]">
      <div className="absolute -top-3 left-4 flex items-center gap-1.5 rounded-full border border-ocean-cyan/30 bg-shelf-1 px-2.5 py-0.5 text-[10px] font-medium tracking-wide text-ocean-cyan shadow-md">
        <Layers className="size-3 text-ocean-cyan" />
        <span>{label}</span>
      </div>
    </div>
  );
}
