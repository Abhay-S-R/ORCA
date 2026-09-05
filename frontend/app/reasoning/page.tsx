"use client";

import "@xyflow/react/dist/style.css";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
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
  History,
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

import { AgentNode, FanoutGroupNode } from "./AgentNode";
import { AnimatedFlowEdge } from "./AnimatedFlowEdge";
import { ReasoningInspector } from "./ReasoningInspector";
import { ReasoningTimeline, PIPELINE_STAGES } from "./ReasoningTimeline";
import { layoutTrace } from "./dagre-layout";
import { EXAMPLE_TRACE, type TraceGraph, type TraceNode } from "./fixture";
import { API_BASE } from "../lib/apiBase";

const nodeTypes: NodeTypes = {
  agent: AgentNode,
  fanoutGroup: FanoutGroupNode,
};

const edgeTypes: EdgeTypes = {
  animatedFlow: AnimatedFlowEdge,
};

type RecentTraceSummary = {
  query_id: string;
  query_text: string;
  verdict: string;
  confidence_tier: string;
  node_count: number;
  total_latency_ms: number;
};

const SCENARIOS = [
  {
    id: "thoothukudi-safe",
    title: "Thoothukudi Safe Passage",
    query: "Is it safe to fish near Thoothukudi tomorrow morning?",
    badge: "GO Verdict",
    tone: "emerald",
    icon: Waves,
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

function ReasoningContent() {
  const searchParams = useSearchParams();
  const initialQueryId = searchParams.get("query_id");

  const [trace, setTrace] = useState<TraceGraph>(EXAMPLE_TRACE);
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
          verdict: data.nodes.find((n) => n.id === "risk_assessment")?.reasoning_summary?.split(":")[0] ?? "COMPLETED",
          text: data.nodes.find((n) => n.id === "reporting")?.reasoning_summary ?? "Trace loaded from session.",
          confidence: data.nodes.find((n) => n.id === "risk_assessment")?.confidence_tier ?? "HIGH",
          queryId: qid,
        });
        setIsVerdictExpanded(false);
      }
    } catch {
      // Fallback
    }
  }, []);

  useEffect(() => {
    void refreshRecentTraces();
  }, [refreshRecentTraces]);

  // If URL has query_id, fetch it
  useEffect(() => {
    if (!initialQueryId) return;
    void loadTraceById(initialQueryId);
  }, [initialQueryId, loadTraceById]);

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
    const resetNodes = trace.nodes.map((n) => ({
      ...n,
      status: "pending" as const,
      latency_ms: 0,
    }));
    setTrace((prev) => ({ ...prev, nodes: resetNodes }));
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
                  latency_ms: data.latency_ms ?? n.latency_ms,
                  confidence_tier: data.confidence_tier ?? n.confidence_tier,
                  reasoning_summary: data.reasoning_summary || n.reasoning_summary,
                  inputs_consumed: data.inputs_consumed,
                  outputs: data.outputs,
                  source_provenance: data.source_provenance,
                  used_llm: data.used_llm ?? n.used_llm,
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

            // Flow logic:
            if (agentName === "distress_check" || agentName === "distress") {
              nextActive.add("language_ingress");
              setTimelineIndex(1);
            } else if (agentName === "language_ingress") {
              nextActive.add("planning");
              setTimelineIndex(2);
            } else if (agentName === "planning") {
              // Fan-out to all 3 specialists simultaneously
              nextActive.add("weather_intelligence");
              nextActive.add("geospatial");
              nextActive.add("ocean_analytics");
              setTimelineIndex(3);
            } else if (
              agentName === "weather_intelligence" ||
              agentName === "geospatial" ||
              agentName === "ocean_analytics"
            ) {
              nextActive.add("risk_assessment");
              nextActive.add("visualization");
              setTimelineIndex(4);
            } else if (agentName === "risk_assessment" || agentName === "visualization") {
              nextActive.add("reporting");
              setTimelineIndex(5);
            } else if (agentName === "reporting") {
              if (isDeep) {
                nextActive.add("critic");
                setTimelineIndex(6);
              } else {
                nextActive.add("language_egress");
                setTimelineIndex(7);
              }
            } else if (agentName === "critic") {
              nextActive.add("language_egress");
              setTimelineIndex(7);
            }
            return nextActive;
          });
        } else if (data.type === "final_response") {
          setIsStreaming(false);
          setActiveNodeIds(new Set());
          setTimelineIndex(PIPELINE_STAGES.length - 1);
          es.close();

          const verdict = data.distress_flag
            ? "DISTRESS"
            : data.risk_assessment?.go_no_go || "CAUTION";

          setFinalVerdict({
            verdict,
            text: data.final_english_response || "Analysis complete.",
            confidence: data.confidence_tier || "HIGH",
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

  // Compute total latency
  const totalLatency = useMemo(() => {
    return trace.nodes.reduce((acc, n) => acc + (n.latency_ms || 0), 0);
  }, [trace]);

  const activeStage = PIPELINE_STAGES[timelineIndex];
  const activeStageLatency = useMemo(() => {
    if (!activeStage) return 0;
    return trace.nodes
      .filter((n) => activeStage.nodeIds.includes(n.id))
      .reduce((acc, n) => acc + (n.latency_ms || 0), 0);
  }, [trace, activeStage]);

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

  return (
    <div
      ref={containerRef}
      className={`relative flex flex-col gap-3 p-4 select-none ${
        isFullscreen ? "h-screen bg-abyss p-6" : "h-[calc(100vh-70px)]"
      }`}
    >
      {/* Top Bar / Command Hub */}
      <div className="relative z-30 flex flex-col gap-3 rounded-2xl border border-hairline/80 bg-shelf-1/80 p-3.5 shadow-lg backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="grid size-9 place-items-center rounded-xl border border-sky-400/40 bg-sky-950/60 text-sky-400 shadow-md">
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
                      ? "border-sky-400/60 bg-sky-950/50 text-sky-400 shadow-sm shadow-sky-400/30"
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
                Real-time execution telemetry across 10 specialized intelligence agents
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
                <History className="size-3.5 text-sky-400" />
                <span>Recent Traces</span>
                {recentTraces.length > 0 && (
                  <span className="rounded-full bg-sky-500/20 px-1.5 py-0.2 text-[10px] font-mono text-sky-300">
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
                                {item.query_text}
                              </span>
                              <span
                                className={`rounded px-1.5 py-0.2 text-[9px] font-bold ${
                                  item.verdict === "GO"
                                    ? "bg-go/15 text-go border border-go/30"
                                    : item.verdict === "DISTRESS"
                                    ? "bg-red-950 text-red-400 border border-red-800/40"
                                    : "bg-caution/15 text-caution border border-caution/30"
                                }`}
                              >
                                {item.verdict}
                              </span>
                            </div>
                            <div className="mt-1 flex items-center gap-2 text-[10px] font-mono text-ink-dim">
                              <span>{item.node_count} agents</span>
                              <span>·</span>
                              <span>{item.total_latency_ms} ms</span>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>

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
              aria-label="Ask ORCA"
              placeholder="Ask ORCA a question to observe real-time agentic reasoning..."
              className="w-full rounded-xl border border-hairline bg-abyss/70 py-2.5 pl-10 pr-4 text-sm text-ink placeholder:text-ink-dim/60 transition-colors hover:border-hairline-strong focus:border-sky-400 focus:outline-none"
            />
          </div>

          <button
            type="submit"
            disabled={isStreaming || !queryInput.trim()}
            className="flex items-center gap-2 rounded-xl border border-sky-400/50 bg-sky-500/20 px-4 py-2.5 text-xs font-semibold text-sky-300 shadow-md transition-all hover:bg-sky-500/30 disabled:opacity-40"
          >
            {isStreaming ? (
              <>
                <span className="size-3 rounded-full border-2 border-sky-400 border-t-transparent animate-spin" />
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

        {/* Quick Scenario Chips */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-hairline/40">
          <span className="text-[11px] font-semibold text-ink-dim mr-1">
            Scenarios:
          </span>
          {SCENARIOS.map((sc) => {
            const ScIcon = sc.icon;
            return (
              <button
                key={sc.id}
                type="button"
                onClick={() => {
                  setQueryInput(sc.query);
                  runLiveQuery(sc.query);
                }}
                disabled={isStreaming}
                className="inline-flex items-center gap-1.5 rounded-lg border border-hairline/80 bg-shelf-2/40 px-2.5 py-1 text-[11px] text-ink-muted transition-all hover:border-sky-400/60 hover:bg-shelf-2 hover:text-ink disabled:opacity-40"
              >
                <ScIcon className="size-3 text-sky-400" />
                <span>{sc.title}</span>
                <span className="rounded bg-abyss/80 px-1 py-0.2 text-[9px] font-mono text-ink-dim">
                  {sc.badge}
                </span>
              </button>
            );
          })}
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
              className="absolute top-4 left-4 right-4 z-20 mx-auto max-w-2xl rounded-2xl border border-hairline-strong/90 bg-shelf-1/95 p-3.5 shadow-2xl shadow-black/80 backdrop-blur-xl"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-md px-2 py-0.5 text-xs font-bold ${
                      finalVerdict.verdict === "GO"
                        ? "bg-go/15 text-go border border-go/30"
                        : finalVerdict.verdict === "DISTRESS"
                        ? "bg-red-950 text-red-400 border border-red-800/60"
                        : "bg-caution/15 text-caution border border-caution/30"
                    }`}
                  >
                    VERDICT: {finalVerdict.verdict}
                  </span>
                  <span className="text-xs font-mono text-ink-dim">
                    Confidence: {finalVerdict.confidence} · {totalLatency} ms
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
        totalLatencyMs={totalLatency}
        activeStageLatencyMs={activeStageLatency}
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
            <span className="size-4 rounded-full border-2 border-sky-400 border-t-transparent animate-spin" />
            <span>Loading Reasoning Pipeline...</span>
          </div>
        </div>
      }
    >
      <ReasoningContent />
    </Suspense>
  );
}
