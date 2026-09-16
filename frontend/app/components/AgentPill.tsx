"use client";

// The live agent activity strip (differentiator 1 — "what makes the UI
// visibly agentic", §4.5). Up to ten agents execute per query (nine on the
// query path plus the conditional Critic on DEEP depth); this is how a user
// sees that happening instead of watching a spinner.
//
// Status is carried by BOTH a glyph and a colour, and the running state adds
// motion on top — three redundant channels, so reduced-motion and colour
// blindness each still leave two.
import React, { useRef, type ComponentType } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronRight,
  Clock,
  Cloud,
  Compass,
  Eye,
  FileText,
  Languages,
  ListChecks,
  Loader2,
  Minus,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Waves,
  X,
} from "lucide-react";

export type AgentStatus = "pending" | "running" | "ok" | "degraded" | "failed" | "skipped";

export const AGENT_REGISTRY: Record<
  string,
  { label: string; shortLabel: string; icon: ComponentType<{ className?: string }> }
> = {
  distress: { label: "Distress Check", shortLabel: "Distress", icon: ShieldAlert },
  distresscheck: { label: "Distress Check", shortLabel: "Distress", icon: ShieldAlert },
  distress_check: { label: "Distress Check", shortLabel: "Distress", icon: ShieldAlert },
  languageingress: { label: "Language Ingress", shortLabel: "Ingress", icon: Languages },
  language_ingress: { label: "Language Ingress", shortLabel: "Ingress", icon: Languages },
  planning: { label: "Planning", shortLabel: "Planning", icon: ListChecks },
  weatherintelligence: { label: "Weather Intel", shortLabel: "Weather", icon: Cloud },
  weather_intelligence: { label: "Weather Intel", shortLabel: "Weather", icon: Cloud },
  weather: { label: "Weather Intel", shortLabel: "Weather", icon: Cloud },
  geospatial: { label: "Geospatial", shortLabel: "Geospatial", icon: Compass },
  oceananalytics: { label: "Ocean Analytics", shortLabel: "Ocean", icon: Waves },
  ocean_analytics: { label: "Ocean Analytics", shortLabel: "Ocean", icon: Waves },
  ocean: { label: "Ocean Analytics", shortLabel: "Ocean", icon: Waves },
  riskassessment: { label: "Risk Assessment", shortLabel: "Risk", icon: ShieldCheck },
  risk_assessment: { label: "Risk Assessment", shortLabel: "Risk", icon: ShieldCheck },
  risk: { label: "Risk Assessment", shortLabel: "Risk", icon: ShieldCheck },
  visualization: { label: "Visualization", shortLabel: "Visuals", icon: Sparkles },
  reporting: { label: "Reporting", shortLabel: "Reporting", icon: FileText },
  critic: { label: "Critic", shortLabel: "Critic", icon: Eye },
  languageegress: { label: "Language Egress", shortLabel: "Egress", icon: Languages },
  language_egress: { label: "Language Egress", shortLabel: "Egress", icon: Languages },
  working: { label: "Processing...", shortLabel: "Running", icon: Loader2 },
};

export function getAgentMeta(raw: string) {
  const normalizedKey = raw.toLowerCase().replace(/[^a-z0-9]/g, "");
  return AGENT_REGISTRY[raw] ?? AGENT_REGISTRY[normalizedKey];
}

export function formatAgentLabel(raw: string): string {
  const meta = getAgentMeta(raw);
  if (meta?.label) return meta.label;
  return raw
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function AgentPill({
  name,
  status,
  latencyMs,
  className = "",
}: {
  name: string;
  status: AgentStatus;
  latencyMs?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const meta = getAgentMeta(name);
  const fullLabel = formatAgentLabel(name);
  const shortLabel = meta?.shortLabel ?? fullLabel;
  const Icon = meta?.icon ?? Activity;

  const statusConfig = {
    ok: {
      container:
        "border-hairline/80 bg-shelf-3 text-ink hover:border-hairline-strong shadow-2xs hover:shadow-xs",
      badge: "bg-go/15 text-go",
      iconColor: "text-ocean-cyan",
      badgeIcon: Check,
      text: "done",
    },
    running: {
      container:
        "border-ocean-cyan/70 bg-ocean-cyan/10 text-ocean-cyan ring-1 ring-ocean-cyan/30 shadow-xs",
      badge: "bg-ocean-cyan/25 text-ocean-cyan",
      iconColor: "text-ocean-cyan",
      badgeIcon: Loader2,
      text: "running",
    },
    degraded: {
      container: "border-caution/50 bg-caution/10 text-caution shadow-2xs hover:shadow-xs",
      badge: "bg-caution/20 text-caution",
      iconColor: "text-caution",
      badgeIcon: AlertTriangle,
      text: "degraded",
    },
    failed: {
      container: "border-no-go/50 bg-no-go/10 text-no-go shadow-2xs hover:shadow-xs",
      badge: "bg-no-go/20 text-no-go",
      iconColor: "text-no-go",
      badgeIcon: X,
      text: "failed",
    },
    pending: {
      container: "border-hairline/50 bg-shelf-1/60 text-ink-dim/80 opacity-75",
      badge: "bg-shelf-2 text-ink-dim",
      iconColor: "text-ink-dim",
      badgeIcon: Clock,
      text: "queued",
    },
    skipped: {
      container: "border-hairline/40 bg-shelf-1/40 text-ink-dim/60 opacity-60",
      badge: "bg-shelf-2 text-ink-dim",
      iconColor: "text-ink-dim",
      badgeIcon: Minus,
      text: "skipped",
    },
  }[status];

  const BadgeIcon = statusConfig.badgeIcon;

  return (
    <span
      className={`inline-flex w-full min-w-0 h-7 shrink-0 items-center justify-center gap-1 sm:gap-1.5 rounded-md border px-1.5 sm:px-2 text-[11px] sm:text-xs font-medium tracking-tight whitespace-nowrap select-none transition-all duration-150 ${statusConfig.container} ${className}`}
      title={`${fullLabel} — ${statusConfig.text}${latencyMs ? ` (${latencyMs}ms)` : ""}`}
    >
      <span
        className={`flex size-3 shrink-0 items-center justify-center rounded-full ${statusConfig.badge}`}
        aria-hidden="true"
      >
        <BadgeIcon
          className={`size-2 ${status === "running" && !reduce ? "animate-spin" : ""} stroke-[2.5]`}
        />
      </span>

      <Icon className={`size-3 shrink-0 hidden md:inline-block ${statusConfig.iconColor}`} aria-hidden="true" />

      <span className="truncate">{shortLabel}</span>
      <span className="sr-only">({statusConfig.text})</span>

      {latencyMs != null && status === "ok" && (
        <span
          data-readout
          className="hidden 2xl:inline ml-0.5 rounded bg-shelf-2/90 px-1 py-0.2 font-mono text-[9px] text-ink-dim"
        >
          {latencyMs}ms
        </span>
      )}
    </span>
  );
}

export function AgentStrip({
  children,
  className = "",
}: {
  children: React.ReactNode;
  connectors?: boolean;
  className?: string;
}) {
  const items = React.Children.toArray(children).filter(Boolean);

  const row1 = items.slice(0, 5);
  const row2 = items.slice(5, 10);

  const renderRow = (rowItems: React.ReactNode[]) => (
    <div className="flex items-center w-full justify-between gap-1 sm:gap-1.5">
      {Array.from({ length: 5 }).map((_, index) => {
        const item = rowItems[index];
        return (
          <React.Fragment key={index}>
            <div className="flex-1 min-w-0 flex justify-center">
              {item ?? (
                <div className="h-7 w-full rounded-md border border-dashed border-hairline/30 bg-shelf-1/20" />
              )}
            </div>
            {index < 4 && (
              <ArrowRight
                className="size-3 text-ink-dim/40 shrink-0 select-none"
                strokeWidth={1.5}
                aria-hidden="true"
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );

  return (
    <div
      aria-live="polite"
      aria-label="Agent reasoning trace"
      className={`w-full rounded-xl border border-hairline/60 bg-shelf-1/40 p-2 sm:p-2.5 shadow-2xs ${className}`}
    >
      <div className="flex flex-col gap-1.5 sm:gap-2">
        {renderRow(row1)}
        {renderRow(row2)}
      </div>
    </div>
  );
}
