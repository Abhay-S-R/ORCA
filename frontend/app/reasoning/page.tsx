"use client";

import "@xyflow/react/dist/style.css";
import {
  ReactFlow,
  Background,
  Controls,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Compass,
  Download,
  History,
  ImageDown,
  Info,
  Maximize2,
  Minimize2,
  Play,
  Search,
  ShieldAlert,
  Sparkles,
  Waves,
  Workflow,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { toPng } from "html-to-image";

import { AgentNode, FanoutGroupNode } from "./AgentNode";
import { AnimatedFlowEdge } from "./AnimatedFlowEdge";
import { ReasoningInspector } from "./ReasoningInspector";
import { ReasoningTimeline, PIPELINE_STAGES } from "./ReasoningTimeline";
import { layoutTrace } from "./dagre-layout";
import { EXAMPLE_TRACE, type TraceGraph, type TraceNode } from "./fixture";
import { API_BASE } from "../lib/apiBase";
import { usePersona } from "../persona/context";
import { freshnessLabel } from "../components/SourceChip";

const nodeTypes: NodeTypes = {
  agent: AgentNode,
  fanoutGroup: FanoutGroupNode,
};

const edgeTypes: EdgeTypes = {
  animatedFlow: AnimatedFlowEdge,
};

// Anything the stored trace doesn't hold arrives as null and is shown as
// "not recorded" — never replaced by a plausible-looking value.
type RecentTraceSummary = {
  query_id: string;
  query_text: string | null;
  verdict: string | null;
  confidence_tier: string | null;
  node_count: number;
  total_latency_ms: number | null;
};

const NOT_RECORDED = "not recorded";

type QuickScenario = {
  id: string;
  title: string;
  query?: string;
  href?: string;
  badge: string;
  tone: string;
  icon: typeof Waves;
};

const SCENARIOS: QuickScenario[] = [
  {
    id: "thoothukudi-safe",
    title: "Thoothukudi Safe Passage",
    query: "Is it safe to fish near Thoothukudi tomorrow morning?",
    badge: "GO Verdict",
    tone: "emerald",
    icon: Waves,
  },
  // P6.7 (orca_final §7.1) — links to /demo's stepped scenario rather than
  // running a single live query: this is a track of positions, not one
  // question, so it has no single `query` string this rail's runLiveQuery
  // could send.
  {
    id: "imbl-approach-palk-bay",
    title: "IMBL Approach — Palk Bay",
    href: "/demo#imbl_border_crossing",
    badge: "Geofence Escalation",
    tone: "amber",
    icon: Compass,
  },
  {
    id: "pamban-hazard",
    title: "Pamban Wave Exceedance",
    query: "Evaluate sea conditions, wave heights, and weather hazards near Pamban Island.",
    badge: "CAUTION Verdict",
    tone: "amber",
    icon: AlertTriangle,
  },
  {
    id: "emergency-sos",
    title: "2ms SOS Distress Signal",
    query: "MAYDAY MAYDAY: Fishing vessel taking on water at 8.75N, 78.20E, engine failure!",
    badge: "DISTRESS Handoff",
    tone: "red",
    icon: ShieldAlert,
  },
  {
    id: "deep-critique",
    title: "Deep Multi-Agent Audit",
    query: "Perform deep risk assessment of IMBL proximity, MPA geofences, and catch decline trends.",
    badge: "Critic Loop",
    tone: "purple",
    icon: Sparkles,
  },
];

// P4.7 (R-PS-10) — what POST /render returns for a fisherman re-render: the
// same zero-re-query mechanism P3.13's language switcher already uses.
type FishermanWhy = {
  deciding: string;
  source: string;
  freshness: string;
};

function ReasoningContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialQueryId = searchParams.get("query_id");
  const { persona } = usePersona();
  const [showTechnical, setShowTechnical] = useState(false);
  const [fishermanWhy, setFishermanWhy] = useState<FishermanWhy | null>(null);
  const [fishermanWhyLoading, setFishermanWhyLoading] = useState(false);

  const [trace, setTrace] = useState<TraceGraph>(EXAMPLE_TRACE);
  // Agents that have already reported in the current live run. A second span for one of them is a
  // re-invocation, which must not restart the flow from that agent.
  const seenRef = useRef<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<TraceNode | null>(null);
  const [queryInput, setQueryInput] = useState("Is it safe to fish near Thoothukudi tomorrow morning?");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeNodeIds, setActiveNodeIds] = useState<Set<string>>(new Set());
  const [completedNodeIds, setCompletedNodeIds] = useState<Set<string>>(new Set());
  const [recentTraces, setRecentTraces] = useState<RecentTraceSummary[]>([]);
  const [showRecentDropdown, setShowRecentDropdown] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [finalVerdict, setFinalVerdict] = useState<{
    verdict: string;
    text: string;
    confidence: string;
    queryId: string;
  } | null>(null);
  const [isVerdictExpanded, setIsVerdictExpanded] = useState(false);

  // Timeline scrubber state
  const [timelineIndex, setTimelineIndex] = useState(PIPELINE_STAGES.length - 1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);
  const sourceRef = useRef<EventSource | null>(null);

  // Fetch recent queries from backend on mount
  const refreshRecentTraces = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/traces/recent`);
      if (res.ok) {
        const data = await res.json();
        setRecentTraces(data);
      }
    } catch {
      // Graceful fallback
    }
  }, []);

  const loadTraceById = useCallback(async (qid: string) => {
    try {
      const res = await fetch(`${API_BASE}/trace/${qid}`);
      if (res.ok) {
        const data: TraceGraph = await res.json();
        setTrace(data);
        const done = new Set(data.nodes.map((n) => n.id));
        setCompletedNodeIds(done);
        setActiveNodeIds(new Set());
        setTimelineIndex(PIPELINE_STAGES.length - 1);
        setFinalVerdict({
          verdict: data.nodes.find((n) => n.id === "risk_assessment")?.reasoning_summary?.split(":")[0] ?? NOT_RECORDED,
          text: data.nodes.find((n) => n.id === "reporting")?.reasoning_summary ?? "Trace loaded from session.",
          confidence: data.nodes.find((n) => n.id === "risk_assessment")?.confidence_tier ?? NOT_RECORDED,
          queryId: qid,
        });
        setIsVerdictExpanded(false);
      }
    } catch {
      // Fallback
    }
  }, []);

  // Both effects below are network fetches whose setState calls only run after
  // an await. They are written as an inner async IIFE rather than a bare call
  // so `react-hooks/set-state-in-effect` can see that too — calling an async
  // useCallback directly reads to the rule as a synchronous cascade.
  useEffect(() => {
    void (async () => {
      await refreshRecentTraces();
    })();
  }, [refreshRecentTraces]);

  // If URL has query_id, fetch it
  useEffect(() => {
    if (!initialQueryId) return;
    void (async () => {
      await loadTraceById(initialQueryId);
    })();
  }, [initialQueryId, loadTraceById]);

  // P4.7 — "Why this answer?" for the fisherman persona: three plain
  // sentences (deciding factor, source, freshness), not the agent graph.
  // Re-renders through the same POST /render P3.13 already built for the
  // persona/language switcher — zero re-query, byte-identical numbers, and
  // the fisherman rendering instruction (reporting.py) is already "plain,
  // simple language" with no agent names, so no separate jargon-stripping
  // logic is needed here.
  const queryIdForWhy = finalVerdict?.queryId;
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (persona !== "fisherman" || !queryIdForWhy || queryIdForWhy === "live") {
        if (!cancelled) setFishermanWhy(null);
        return;
      }
      if (!cancelled) setFishermanWhyLoading(true);
      try {
        const res = await fetch(`${API_BASE}/render`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query_id: queryIdForWhy, persona: "fisherman" }),
        });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const primarySource = (data.citations ?? [])[0] as
          | { dataset?: string; freshness_minutes?: number }
          | undefined;
        if (cancelled) return;
        setFishermanWhy({
          deciding: data.final_english_response || "No answer recorded for this query.",
          source: primarySource?.dataset
            ? `Based on ${primarySource.dataset}.`
            : "No source is recorded for this answer.",
          freshness:
            primarySource && typeof primarySource.freshness_minutes === "number"
              ? `That reading is ${freshnessLabel(primarySource.freshness_minutes)}.`
              : "",
        });
      } catch {
        if (!cancelled) setFishermanWhy(null);
      } finally {
        if (!cancelled) setFishermanWhyLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [persona, queryIdForWhy]);

  // Run live query via SSE
  const runLiveQuery = (queryText: string) => {
    if (!queryText.trim()) return;
    sourceRef.current?.close();

    setIsStreaming(true);
    setFinalVerdict(null);
    setIsVerdictExpanded(false);
    setSelectedNode(null);
    setIsPlaying(false);

    // Reset pipeline nodes to pending
    // Seeded from EXAMPLE_TRACE (today's pipeline, Discovery and the Critic included), NOT from
    // whichever trace is on screen. A loaded older trace has no node for `critic` or
    // `marine_data_discovery`, and a live span for a node that does not exist was silently
    // dropped, which is why the Critic never appeared in a live run.
    seenRef.current = new Set();
    const resetNodes = EXAMPLE_TRACE.nodes.map((n) => ({
      ...n,
      status: "pending" as const,
      latency_ms: 0,
      run_count: 1,
    }));
    setTrace({ ...EXAMPLE_TRACE, query_id: "live", nodes: resetNodes });
    setCompletedNodeIds(new Set());
    setActiveNodeIds(new Set(["distress_check", "distress"]));
    setTimelineIndex(0);

    const isDeep = queryText.toLowerCase().includes("deep");
    const es = new EventSource(
      `${API_BASE}/query?q=${encodeURIComponent(queryText)}${isDeep ? "&depth=DEEP" : ""}`
    );
    sourceRef.current = es;

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);

        if (data.type === "agent_span") {
          const agentName = data.agent_name;
          const realName = data.agent_real_name || agentName;

          // Update node state
          setTrace((prev) => {
            const updatedNodes = prev.nodes.map((n) => {
              if (n.id === agentName || n.id === realName) {
                return {
                  ...n,
                  status: (data.status as TraceNode["status"]) || "ok",
                  confidence_tier: data.confidence_tier ?? n.confidence_tier,
                  confidence_score: data.confidence_score ?? null,
                  confidence_detail: data.confidence_detail ?? null,
                  reasoning_summary: data.reasoning_summary || n.reasoning_summary,
                  inputs_consumed: data.inputs_consumed,
                  outputs: data.outputs,
                  source_provenance: data.source_provenance,
                  used_llm: data.used_llm ?? n.used_llm,
                  engine: data.engine ?? n.engine,
                  model: data.model ?? null,
                  tier: data.tier ?? null,
                  skip_reason: data.skip_reason ?? null,
                  // A repeat span is a re-invocation: same node, one more run, time added not replaced.
                  run_count: (n.run_count ?? 1) + (seenRef.current.has(n.id) ? 1 : 0),
                  latency_ms: (seenRef.current.has(n.id) ? n.latency_ms : 0) + (data.latency_ms ?? 0),
                };
              }
              return n;
            });
            return { ...prev, nodes: updatedNodes };
          });

          // Mark completed
          setCompletedNodeIds((prev) => new Set([...prev, agentName, realName]));

          // Transition downstream nodes to active
          setActiveNodeIds((prev) => {
            const nextActive = new Set(prev);
            nextActive.delete(agentName);
            nextActive.delete(realName);

            // What runs next, from the graph as it is built today (graph.py). The Critic follows
            // Reporting on EVERY query (the old `if (isDeep)` branch skipped it on ordinary ones),
            // and Marine Data Discovery sits between Planning and the fan-out.
            const rerun = seenRef.current.has(agentName);
            const successors: Record<string, string[]> = {
              distress_check: ["language_ingress"],
              distress: ["language_ingress"],
              language_ingress: ["planning"],
              planning: ["marine_data_discovery"],
              marine_data_discovery: ["weather_intelligence", "geospatial", "ocean_analytics"],
              weather_intelligence: ["risk_assessment", "visualization"],
              geospatial: ["risk_assessment", "visualization"],
              ocean_analytics: ["risk_assessment", "visualization"],
              risk_assessment: ["reporting"],
              visualization: ["reporting"],
              reporting: ["critic"],
              critic: ["language_egress"],
            };
            // A re-run specialist hands straight to Reporting; Risk and Visualization do not re-run.
            const next =
              rerun && ["weather_intelligence", "geospatial", "ocean_analytics"].includes(agentName)
                ? ["reporting"]
                : successors[agentName] ?? [];
            next.forEach((id) => nextActive.add(id));
            const stageOf = PIPELINE_STAGES.findIndex((st) => st.nodeIds.includes(agentName));
            if (stageOf >= 0) {
              setTimelineIndex((cur) => Math.max(cur, Math.min(stageOf + 1, PIPELINE_STAGES.length - 1)));
            }
            seenRef.current.add(agentName);
            return nextActive;
          });
        } else if (data.type === "final_response") {
          setIsStreaming(false);
          setActiveNodeIds(new Set());
          setTimelineIndex(PIPELINE_STAGES.length - 1);
          es.close();
          // The run is over: replace the streamed skeleton with the recorded trace, which carries what
          // streaming cannot: the Critic's loop edge, a cancelled edge, and run counts.
          if (data.query_id) void loadTraceById(data.query_id);

          const verdict = data.distress_flag
            ? "DISTRESS"
            : data.risk_assessment?.go_no_go || NOT_RECORDED;

          setFinalVerdict({
            verdict,
            text: data.final_english_response || "Analysis complete.",
            confidence: data.confidence_tier || NOT_RECORDED,
            queryId: data.query_id,
          });

          refreshRecentTraces();
        }
      } catch {
        // Fallback for parse issues
      }
    };

    es.onerror = () => {
      setIsStreaming(false);
      setActiveNodeIds(new Set());
      es.close();
    };
  };

  // Playback timeline controller
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      setTimelineIndex((prev) => {
        if (prev >= PIPELINE_STAGES.length - 1) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, 1800 / playbackSpeed);

    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed]);

  // Compute Dagre layout dynamically
  const { nodes, edges } = useMemo(() => {
    return layoutTrace(trace, {
      activeNodeIds,
      completedNodeIds,
    });
  }, [trace, activeNodeIds, completedNodeIds]);

  // Keyboard navigation: activate selected node on Enter or Space
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const target = e.target as HTMLElement | null;
      const active = document.activeElement as HTMLElement | null;
      const el =
        target?.closest<HTMLElement>(".react-flow__node:not(.react-flow__node-fanoutGroup)") ||
        active?.closest<HTMLElement>(".react-flow__node:not(.react-flow__node-fanoutGroup)");
      if (!el) return;
      const id = el.getAttribute("data-id") || el.dataset.id;
      if (!id) return;
      const found = nodes.find((n) => n.id === id);
      const nodeData = found?.data as { node?: TraceNode } | undefined;
      if (!nodeData?.node) return;
      e.preventDefault();
      setSelectedNode(nodeData.node);
    };

    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [nodes]);

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  // P4.14 — the trace itself, exactly as `GET /trace/{query_id}` returns it,
  // not the client's own laid-out copy: a report or an incident review needs
  // the record, not this page's rendering of it.
  async function exportTraceJson() {
    if (!trace.query_id || trace.query_id === "live") return;
    const res = await fetch(`${API_BASE}/trace/${trace.query_id}`);
    if (!res.ok) return;
    const blob = new Blob([await res.text()], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `orca-trace-${trace.query_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // The rendered graph, not the trace data — a PNG for a slide or an
  // incident review shows what the reviewer saw, which the JSON export
  // above does not. `.react-flow` is the library's own root element.
  async function exportGraphPng() {
    const node = containerRef.current?.querySelector<HTMLElement>(".react-flow");
    if (!node) return;
    const dataUrl = await toPng(node, { backgroundColor: "#f2ead4", pixelRatio: 2 });
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = `orca-reasoning-graph-${trace.query_id}.png`;
    a.click();
  }

  // P4.7 — fisherman persona sees this instead of the agent graph: no agent
  // names, no jargon, an explicit opt-in to the engineer-facing view below.
  if (persona === "fisherman" && !showTechnical) {
    return (
      <div className="mx-auto flex h-[calc(100vh-70px)] max-w-lg flex-col justify-center gap-4 p-4">
        <div className="rounded-2xl border border-hairline-strong/70 bg-shelf-1/60 p-5 shadow-lg">
          <div className="flex items-center gap-2 text-ink-dim">
            <Info className="size-4 shrink-0 text-ocean-cyan" aria-hidden="true" />
            <h1 className="text-sm font-semibold text-ink">Why this answer?</h1>
          </div>
          {fishermanWhyLoading && <p className="mt-3 text-sm text-ink-muted">Loading…</p>}
          {!fishermanWhyLoading && !fishermanWhy && (
            <p className="mt-3 text-sm text-ink-muted">
              Ask a question on the home screen first, then come back here to see why.
            </p>
          )}
          {!fishermanWhyLoading && fishermanWhy && (
            <div className="mt-3 flex flex-col gap-2 text-sm leading-relaxed text-ink">
              <p>{fishermanWhy.deciding}</p>
              <p className="text-ink-muted">{fishermanWhy.source}</p>
              {fishermanWhy.freshness && <p className="text-ink-muted">{fishermanWhy.freshness}</p>}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => setShowTechnical(true)}
          className="self-center text-xs font-medium text-ink-dim underline-offset-2 hover:text-ink hover:underline"
        >
          Show the technical trace
        </button>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`relative flex flex-col gap-3 p-4 select-none ${
        isFullscreen ? "h-screen bg-abyss p-6" : "h-[calc(100vh-70px)]"
      }`}
    >
      {persona === "fisherman" && (
        <button
          type="button"
          onClick={() => setShowTechnical(false)}
          className="self-start text-xs font-medium text-ink-dim underline-offset-2 hover:text-ink hover:underline"
        >
          ← Back to the plain answer
        </button>
      )}
      {/* Top Bar / Command Hub */}
      <div className="relative z-30 flex flex-col gap-3 rounded-2xl border border-hairline/80 bg-shelf-1/80 p-3.5 shadow-lg backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="grid size-9 place-items-center rounded-xl border border-ocean-cyan/40 bg-ocean-cyan/10 text-ocean-cyan shadow-md">
              <Workflow className="size-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold tracking-tight text-ink">
                  Reasoning & Agent Graph
                </h1>
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide border ${
                    isStreaming
                      ? "border-ocean-cyan/60 bg-ocean-cyan/10 text-ocean-cyan shadow-sm"
                      : "border-go/40 bg-go/15 text-go"
                  }`}
                >
                  <span
                    className={`size-1.5 rounded-full ${
                      isStreaming ? "bg-ocean-cyan animate-ping" : "bg-go"
                    }`}
                  />
                  {isStreaming ? "LIVE EXECUTION" : "READY · REAL-TIME"}
                </span>
              </div>
              <p className="text-[11px] text-ink-dim">
                Real-time execution telemetry across 12 specialized intelligence agents
              </p>
            </div>
          </div>

          {/* Recent Traces Dropdown & Controls */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowRecentDropdown((v) => !v)}
                className="flex items-center gap-1.5 rounded-xl border border-hairline bg-shelf-2/60 px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:border-hairline-strong hover:bg-shelf-2"
              >
                <History className="size-3.5 text-ocean-cyan" />
                <span>Recent Traces</span>
                {recentTraces.length > 0 && (
                  <span className="rounded-full bg-ocean-cyan/10 px-1.5 py-0.2 text-[10px] font-mono text-ocean-cyan">
                    {recentTraces.length}
                  </span>
                )}
                <ChevronDown className="size-3 text-ink-dim" />
              </button>

              {showRecentDropdown && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setShowRecentDropdown(false)}
                  />
                  <div className="absolute right-0 top-full z-50 mt-1.5 w-80 rounded-xl border border-hairline-strong bg-shelf-1/95 p-2 shadow-2xl backdrop-blur-xl">
                    <div className="flex items-center justify-between border-b border-hairline/60 px-2 pb-1.5 text-[10px] font-semibold text-ink-dim uppercase tracking-wider">
                      <span>Recent Query Traces</span>
                      <button
                        type="button"
                        onClick={() => setShowRecentDropdown(false)}
                        className="hover:text-ink"
                      >
                        Close
                      </button>
                    </div>
                    <div className="mt-1 max-h-64 overflow-y-auto space-y-1">
                      {recentTraces.length === 0 ? (
                        <p className="p-3 text-center text-xs text-ink-dim">
                          No previous traces recorded yet in this session.
                        </p>
                      ) : (
                        recentTraces.map((item) => (
                          <button
                            key={item.query_id}
                            type="button"
                            onClick={() => {
                              loadTraceById(item.query_id);
                              setShowRecentDropdown(false);
                            }}
                            className="w-full rounded-lg p-2 text-left transition-colors hover:bg-shelf-2/80"
                          >
                            <div className="flex items-center justify-between">
                              <span className="truncate text-xs font-medium text-ink">
                                {item.query_text ?? `Query ${item.query_id.slice(0, 8)} (text ${NOT_RECORDED})`}
                              </span>
                              <span
                                className={`rounded px-1.5 py-0.2 text-[9px] font-bold ${
                                  item.verdict === "GO"
                                    ? "bg-go/15 text-go border border-go/30"
                                    : item.verdict === "DISTRESS"
                                    ? "bg-no-go/10 text-no-go border border-no-go/30"
                                    : "bg-caution/15 text-caution border border-caution/30"
                                }`}
                              >
                                {item.verdict ?? NOT_RECORDED}
                              </span>
                            </div>
                            <div className="mt-1 flex items-center gap-2 text-[10px] font-mono text-ink-dim">
                              <span>{item.node_count} agents</span>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>

            {trace.query_id !== "live" && (
              <button
                type="button"
                onClick={() => void exportTraceJson()}
                className="grid size-8 place-items-center rounded-xl border border-hairline bg-shelf-2/60 text-ink-dim transition-colors hover:border-hairline-strong hover:text-ink"
                title="Export trace as JSON"
              >
                <Download className="size-4" />
              </button>
            )}
            <button
              type="button"
              onClick={() => void exportGraphPng()}
              className="grid size-8 place-items-center rounded-xl border border-hairline bg-shelf-2/60 text-ink-dim transition-colors hover:border-hairline-strong hover:text-ink"
              title="Export graph as PNG"
            >
              <ImageDown className="size-4" />
            </button>
            <button
              type="button"
              onClick={toggleFullscreen}
              className="grid size-8 place-items-center rounded-xl border border-hairline bg-shelf-2/60 text-ink-dim transition-colors hover:border-hairline-strong hover:text-ink"
              title={isFullscreen ? "Exit Fullscreen" : "Fullscreen Graph"}
            >
              {isFullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
            </button>
          </div>
        </div>

        {/* Query Input + Run Form */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            runLiveQuery(queryInput);
          }}
          className="flex items-center gap-2"
        >
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-ink-dim" />
            <input
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              aria-label="Ask Sagar Sarathi"
              placeholder="Ask Sagar Sarathi a question to observe real-time agentic reasoning..."
              className="w-full rounded-xl border border-hairline bg-abyss/70 py-2.5 pl-10 pr-4 text-sm text-ink placeholder:text-ink-dim/60 transition-colors hover:border-hairline-strong focus:border-ocean-cyan/70 focus:outline-none"
            />
          </div>

          <button
            type="submit"
            disabled={isStreaming || !queryInput.trim()}
            className="flex items-center gap-2 rounded-xl border border-ocean-cyan/50 bg-ocean-cyan/10 px-4 py-2.5 text-xs font-semibold text-ocean-cyan shadow-md transition-all hover:bg-ocean-cyan/15 disabled:opacity-40"
          >
            {isStreaming ? (
              <>
                <span className="size-3 rounded-full border-2 border-ocean-cyan border-t-transparent animate-spin" />
                <span>Executing Pipeline...</span>
              </>
            ) : (
              <>
                <Play className="size-3.5 fill-current" />
                <span>Run Live Query</span>
              </>
            )}
          </button>
        </form>

        {/* Quick Scenario Chips — a real grid (equal widths, deliberate row
            alignment) rather than left-aligned wrapping chips, so a
            shorter second row never reads as an accidental gap. */}
        <div className="border-t border-hairline/40 pt-2">
          <span className="mb-1.5 block text-[11px] font-semibold text-ink-dim">
            Scenarios
          </span>
          <div className="grid grid-cols-2 gap-1.5 lg:grid-cols-4">
            {SCENARIOS.map((sc) => {
              const ScIcon = sc.icon;
              return (
                <button
                  key={sc.id}
                  type="button"
                  onClick={() => {
                    if (sc.href) {
                      router.push(sc.href);
                      return;
                    }
                    if (sc.query) {
                      setQueryInput(sc.query);
                      runLiveQuery(sc.query);
                    }
                  }}
                  disabled={isStreaming}
                  className="flex items-center gap-1.5 rounded-lg border border-hairline/80 bg-shelf-2/40 px-2.5 py-1.5 text-[11px] text-ink-muted transition-all hover:border-ocean-cyan/60 hover:bg-shelf-2 hover:text-ink disabled:opacity-40"
                >
                  <ScIcon className="size-3 shrink-0 text-ocean-cyan" />
                  <span className="min-w-0 flex-1 truncate text-left">{sc.title}</span>
                  <span className="shrink-0 rounded bg-shelf-1/80 px-1 py-0.2 text-[9px] font-mono text-ink-dim">
                    {sc.badge}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Main Canvas Container */}
      <div className="relative flex-1 overflow-hidden rounded-2xl border border-hairline-strong/70 bg-shelf-1/30 shadow-inner">
        {/* Floating Final Response Banner when complete */}
        <AnimatePresence>
          {finalVerdict && (
            <motion.div
              initial={{ y: -50, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: -50, opacity: 0 }}
              className="absolute top-4 left-4 right-4 z-20 mx-auto max-w-2xl rounded-2xl border border-hairline-strong/90 bg-shelf-1/95 p-3.5 shadow-xl backdrop-blur-xl"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-md px-2 py-0.5 text-xs font-bold ${
                      finalVerdict.verdict === "GO"
                        ? "bg-go/15 text-go border border-go/30"
                        : finalVerdict.verdict === "DISTRESS"
                        ? "bg-no-go/10 text-no-go border border-no-go/30"
                        : "bg-caution/15 text-caution border border-caution/30"
                    }`}
                  >
                    VERDICT: {finalVerdict.verdict}
                  </span>
                  <span className="text-xs font-mono text-ink-dim">
                    Confidence: {finalVerdict.confidence}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setFinalVerdict(null)}
                  className="text-ink-dim hover:text-ink"
                >
                  <X className="size-4" />
                </button>
              </div>
              <div className="mt-1.5">
                <p
                  className={`text-xs text-ink leading-snug transition-all ${
                    isVerdictExpanded ? "max-h-60 overflow-y-auto pr-1" : "line-clamp-2"
                  }`}
                >
                  {finalVerdict.text}
                </p>
                {finalVerdict.text && finalVerdict.text.length > 100 && (
                  <button
                    type="button"
                    onClick={() => setIsVerdictExpanded((prev) => !prev)}
                    className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-ocean-cyan hover:underline focus:outline-none"
                  >
                    {isVerdictExpanded ? (
                      <>
                        <span>Read less</span>
                        <ChevronUp className="size-3" />
                      </>
                    ) : (
                      <>
                        <span>Read more</span>
                        <ChevronDown className="size-3" />
                      </>
                    )}
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ReactFlow Graph Canvas.
            React Flow makes each node focusable but does not activate one on
            Enter/Space, so the inspector was mouse-only. The keydown sits on
            the wrapper rather than inside the custom node component because
            the focusable element is React Flow's own node wrapper, which the
            custom component never renders. */}
        <div
          className="contents"
          onKeyDown={(e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            const el = (document.activeElement as HTMLElement | null)?.closest<HTMLElement>(
              ".react-flow__node",
            );
            const found = el && nodes.find((n) => n.id === el.dataset.id);
            const nodeData = found?.data as { node?: TraceNode } | undefined;
            if (!nodeData?.node) return;
            e.preventDefault();  // Space would otherwise scroll the canvas
            setSelectedNode(nodeData.node);
          }}
        >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodeClick={(_, n) => {
            const nodeData = n.data as { node?: TraceNode };
            if (nodeData?.node) {
              setSelectedNode(nodeData.node);
            }
          }}
          onPaneClick={() => setSelectedNode(null)}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          proOptions={{ hideAttribution: true }}
          colorMode="light"
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
        >
          <Background gap={24} color="#d8cfb0" />
          <Controls showInteractive={false} className="!bg-shelf-1/90 !border-hairline !rounded-xl" />
        </ReactFlow>
        </div>

        {/* Floating Slide-out Inspector */}
        {selectedNode && (
          <ReasoningInspector
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
          />
        )}
      </div>

      {/* Execution progress — a panel below the graph, not an overlay on
          top of it: a timer covering nodes/edges was never legible as
          "part of the product" no matter how it was styled. */}
      <ReasoningTimeline
        currentStageIndex={timelineIndex}
        maxStages={PIPELINE_STAGES.length}
        isPlaying={isPlaying}
        playbackSpeed={playbackSpeed}
        onSelectStage={(idx) => {
          setTimelineIndex(idx);
          setIsPlaying(false);
        }}
        onTogglePlay={() => setIsPlaying((p) => !p)}
        onChangeSpeed={(s) => setPlaybackSpeed(s)}
        onReset={() => {
          setTimelineIndex(0);
          setIsPlaying(false);
        }}
      />
    </div>
  );
}

export default function ReasoningPage() {
  return (
    <Suspense
      fallback={
        <div className="grid h-[calc(100vh-70px)] place-items-center bg-abyss text-ink-dim">
          <div className="flex items-center gap-2">
            <span className="size-4 rounded-full border-2 border-ocean-cyan border-t-transparent animate-spin" />
            <span>Loading Reasoning Pipeline...</span>
          </div>
        </div>
      }
    >
      <ReasoningContent />
    </Suspense>
  );
}
