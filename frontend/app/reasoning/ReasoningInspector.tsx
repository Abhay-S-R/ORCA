"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Check,
  CheckCheck,
  Clock,
  Cloud,
  Compass,
  Copy,
  Cpu,
  Database,
  FileText,
  Languages,
  ListChecks,
  ShieldAlert,
  Sparkles,
  Waves,
  X,
  Zap,
} from "lucide-react";
import type { ComponentType } from "react";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import type { TraceNode } from "./fixture";
import { formatReasoningSummary } from "./AgentNode";

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
  critic: CheckCheck,
  language_egress: Languages,
};

interface ReasoningInspectorProps {
  node: TraceNode | null;
  onClose: () => void;
}

type TabKey = "reasoning" | "sources" | "payloads" | "telemetry";

export function ReasoningInspector({ node, onClose }: ReasoningInspectorProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("reasoning");
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  if (!node) return null;

  const Icon = ICON[node.id] ?? ICON[node.agent_name.toLowerCase().replace(/ /g, "_")] ?? ShieldAlert;

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1500);
  };

  const inputsJson = JSON.stringify(node.inputs_consumed || {}, null, 2);
  const outputsJson = JSON.stringify(node.outputs || {}, null, 2);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ x: 380, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 380, opacity: 0 }}
        transition={{ type: "spring", damping: 26, stiffness: 280 }}
        className="absolute top-4 right-4 bottom-4 z-30 flex w-[380px] flex-col rounded-2xl border border-hairline-strong/80 bg-shelf-1/95 p-4 shadow-xl backdrop-blur-xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-hairline/80 pb-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="grid size-8 shrink-0 place-items-center rounded-lg border border-ocean-cyan/40 bg-ocean-cyan/10 text-ocean-cyan">
              <Icon className="size-4" />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold tracking-tight text-ink">
                {node.agent_name}
              </h2>
              <p className="text-[10px] font-mono text-ink-dim">
                ID: {node.id} · Step {node.depth}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-hairline p-1.5 text-ink-dim transition-colors hover:border-hairline-strong hover:bg-shelf-2 hover:text-ink"
            aria-label="Close inspector"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="mt-3 flex gap-1 rounded-lg border border-hairline bg-shelf-2/50 p-1">
          {(
            [
              { id: "reasoning", label: "Reasoning" },
              { id: "sources", label: "Sources" },
              { id: "payloads", label: "Payload" },
              { id: "telemetry", label: "Telemetry" },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 rounded-md py-1 text-[11px] font-medium transition-all ${
                activeTab === tab.id
                  ? "bg-shelf-2 text-ink shadow-sm"
                  : "text-ink-dim hover:text-ink"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
          {activeTab === "reasoning" && (
            <div className="space-y-4">
              <div>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                  Confidence Tier
                </span>
                <div className="mt-1.5">
                  <ConfidenceMeter tier={node.confidence_tier} />
                </div>
              </div>

              <div>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                  Decision Summary
                </span>
                <p className="mt-1.5 rounded-lg border border-hairline/60 bg-shelf-2/50 p-3 text-[12px] leading-relaxed text-ink">
                  {formatReasoningSummary(node.reasoning_summary)}
                </p>
              </div>

              <div>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                  Execution Status
                </span>
                <div className="mt-1.5 flex items-center gap-2 rounded-lg border border-hairline bg-shelf-2/30 p-2.5">
                  <div
                    className={`size-2 rounded-full ${
                      node.status === "ok"
                        ? "bg-go"
                        : node.status === "running"
                        ? "bg-ocean-cyan animate-ping"
                        : "bg-caution"
                    }`}
                  />
                  <span className="text-[11px] font-medium text-ink capitalize">
                    {node.status}
                  </span>
                  <span className="ml-auto font-mono text-[11px] text-ink-dim">
                    {node.latency_ms ?? 0} ms latency
                  </span>
                </div>
              </div>

              <div>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                  Agent Pipeline Role
                </span>
                <p className="mt-1 text-[11px] text-ink-muted leading-snug">
                  {node.used_llm
                    ? `Bounded synthesis pass using ${node.tier ?? "mid"} LLM tier (${node.model ?? "gemini-3.5-flash-lite"}). Evaluated under strict causal claims rubric.`
                    : "Deterministic specialist agent. Executes strict scientific formulas, bathymetric lookups, or GeoJSON geofences with zero stochastic variation."}
                </p>
              </div>
            </div>
          )}

          {activeTab === "sources" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                  Source Provenance
                </span>
                <span className="rounded bg-ocean-cyan/10 border border-ocean-cyan/30 px-1.5 py-0.5 text-[10px] font-mono text-ocean-cyan">
                  {node.source_count} dataset{node.source_count === 1 ? "" : "s"}
                </span>
              </div>

              {node.source_provenance ? (
                <div className="rounded-xl border border-hairline bg-shelf-2/50 p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <Database className="size-3.5 text-ocean-cyan" />
                    <span className="text-[12px] font-semibold text-ink">
                      {node.source_provenance.dataset}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-ink-dim pt-2 border-t border-hairline/40">
                    <div>
                      <span className="block text-[9px] uppercase tracking-wider text-ink-dim/80">
                        Acquired
                      </span>
                      <span className="text-ink truncate block">
                        {node.source_provenance.acquisition_timestamp || "Live Cache"}
                      </span>
                    </div>
                    <div>
                      <span className="block text-[9px] uppercase tracking-wider text-ink-dim/80">
                        Freshness
                      </span>
                      <span className="text-ink">
                        {node.source_provenance.freshness_minutes} mins ago
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-hairline p-4 text-center">
                  <p className="text-[11px] text-ink-dim">
                    Derived internally from upstream specialist inputs (no external data fetch needed).
                  </p>
                </div>
              )}

              <div className="rounded-lg border border-hairline/60 bg-shelf-2/20 p-2.5">
                <span className="text-[10px] font-semibold text-ink block mb-1">
                  Authoritative Scientific Providers
                </span>
                <p className="text-[11px] text-ink-dim leading-snug">
                  Data ingest pipeline integrates INCOIS OSF Hycom, MOSDAC Scatsat-1, GEBCO 15-arcsecond bathymetry, and Survey of India tidal tables.
                </p>
              </div>
            </div>
          )}

          {activeTab === "payloads" && (
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                    Inputs Consumed
                  </span>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(inputsJson, "inputs")}
                    className="flex items-center gap-1 text-[10px] text-ink-dim hover:text-ink"
                  >
                    {copiedKey === "inputs" ? (
                      <Check className="size-3 text-go" />
                    ) : (
                      <Copy className="size-3" />
                    )}
                    {copiedKey === "inputs" ? "Copied" : "Copy"}
                  </button>
                </div>
                <pre className="max-h-[160px] overflow-auto rounded-lg border border-white/10 bg-[#141b24] p-2.5 font-mono text-[10px] text-sky-300">
                  {inputsJson}
                </pre>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-dim">
                    Outputs Produced
                  </span>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(outputsJson, "outputs")}
                    className="flex items-center gap-1 text-[10px] text-ink-dim hover:text-ink"
                  >
                    {copiedKey === "outputs" ? (
                      <Check className="size-3 text-go" />
                    ) : (
                      <Copy className="size-3" />
                    )}
                    {copiedKey === "outputs" ? "Copied" : "Copy"}
                  </button>
                </div>
                <pre className="max-h-[220px] overflow-auto rounded-lg border border-white/10 bg-[#141b24] p-2.5 font-mono text-[10px] text-emerald-300">
                  {outputsJson}
                </pre>
              </div>
            </div>
          )}

          {activeTab === "telemetry" && (
            <div className="space-y-4">
              <div className="rounded-xl border border-hairline bg-shelf-2/50 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-[11px] text-ink-dim">
                    <Clock className="size-3.5 text-ocean-cyan" />
                    <span>Execution Latency</span>
                  </div>
                  <span className="font-mono text-sm font-semibold text-ink">
                    {node.latency_ms ?? 0} ms
                  </span>
                </div>
                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-shelf-2">
                  <div
                    className="h-full rounded-full bg-ocean-cyan transition-all duration-500"
                    style={{
                      width: `${Math.min(100, Math.max(5, ((node.latency_ms ?? 0) / 600) * 100))}%`,
                    }}
                  />
                </div>
                <div className="mt-1 flex justify-between text-[9px] font-mono text-ink-dim">
                  <span>0 ms</span>
                  <span>300 ms (budget)</span>
                  <span>600+ ms</span>
                </div>
              </div>

              <div className="rounded-xl border border-hairline bg-shelf-2/50 p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <Cpu className="size-3.5 text-accent" />
                  <span className="text-[12px] font-semibold text-ink">
                    Execution Architecture
                  </span>
                </div>
                <p className="text-[11px] text-ink-muted">
                  {node.used_llm
                    ? `Model: ${node.model ?? "gemini-3.5-flash-lite"} · Tier: ${node.tier ?? "mid"}`
                    : "Zero LLM tokens used. Pure mathematical/geospatial code execution."}
                </p>
              </div>

              <div className="rounded-xl border border-hairline bg-shelf-2/50 p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <Zap className="size-3.5 text-caution" />
                  <span className="text-[12px] font-semibold text-ink">
                    Ground Rule Adherence
                  </span>
                </div>
                <p className="text-[11px] text-ink-dim leading-snug">
                  Ground Rule 2: Specialist agents shape raw data deterministically and never reason over it with a generative model.
                </p>
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
