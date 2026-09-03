// D1 owns the real `TraceGraph` payload and `/trace/{query_id}` replay API
// (plan §5.1) — neither exists on `main` yet. This fixture matches that
// contract's documented shape exactly, so swapping it for a live fetch later
// is a data-source change, not a rewrite of this page.
//
// It is not invented data: every node/edge here is the *actual* current
// LangGraph wiring in orca/graph/graph.py (distress_check -> language_ingress
// -> planning -> [weather_intelligence, geospatial, ocean_analytics] ->
// [risk_assessment, visualization] -> reporting -> language_egress), with
// plausible-but-labelled-as-example per-node numbers. What it deliberately
// does NOT contain: a Critic node or a `critic_loop` edge — Agent 10 is D1's
// unshipped work, and a fixture-backed stand-in for it would misrepresent a
// subsystem that does not exist yet (out of scope, D3 plan §8).
import type { ConfidenceTier } from "../components/Badge";
import type { AgentStatus } from "../components/AgentPill";

export type TraceNode = {
  id: string;
  agent_name: string;
  depth: number;
  status: AgentStatus;
  confidence_tier: ConfidenceTier;
  latency_ms: number;
  reasoning_summary: string;
  source_count: number;
  used_llm: boolean;
  model: string | null;
  tier: "cheap" | "mid" | "reasoning" | null;
};

export type TraceEdge = {
  from: string;
  to: string;
  kind: "handoff" | "critic_loop" | "cancelled";
  label?: string;
};

export type TraceGroup = { id: string; node_ids: string[]; reason: "parallel_fanout" };

export type TraceGraph = {
  query_id: string;
  nodes: TraceNode[];
  edges: TraceEdge[];
  groups: TraceGroup[];
};

export const EXAMPLE_TRACE: TraceGraph = {
  query_id: "example-8f2c1a9e-safety-deep",
  nodes: [
    {
      id: "distress_check", agent_name: "Distress Check", depth: 0, status: "ok", confidence_tier: "HIGH",
      latency_ms: 2, reasoning_summary: "No distress flag set — pipeline continues to language_ingress.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
    {
      id: "language_ingress", agent_name: "Language Ingress", depth: 1, status: "ok", confidence_tier: "HIGH",
      latency_ms: 340, reasoning_summary: "Detected Tamil, normalized to English: \"Is it safe to fish near Thoothukudi tomorrow?\"",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
    {
      id: "planning", agent_name: "Planning", depth: 2, status: "ok", confidence_tier: "HIGH",
      latency_ms: 610, reasoning_summary: "Classified SAFETY_CHECK, reasoning_depth=DEEP, fanned out to Weather, Geospatial, Ocean Analytics.",
      source_count: 0, used_llm: true, model: "gemini-3.5-flash-lite", tier: "cheap",
    },
    {
      id: "weather_intelligence", agent_name: "Weather Intelligence", depth: 3, status: "ok", confidence_tier: "HIGH",
      latency_ms: 480, reasoning_summary: "Hs 2.4 m vs small_fishing class band 2.0 m → exceeded. Wind 22 km/h, no lightning.",
      source_count: 2, used_llm: false, model: null, tier: null,
    },
    {
      id: "geospatial", agent_name: "Geospatial", depth: 3, status: "ok", confidence_tier: "HIGH",
      latency_ms: 190, reasoning_summary: "0.8 nm from the Sri Lanka EEZ (IMBL proxy) — CAUTION band, no MPA violation.",
      source_count: 3, used_llm: false, model: null, tier: null,
    },
    {
      id: "ocean_analytics", agent_name: "Ocean Analytics", depth: 3, status: "ok", confidence_tier: "MEDIUM",
      latency_ms: 260, reasoning_summary: "Falling tide, nearest PFZ 4.2 km. SOI table gap forced a Stormglass fallback.",
      source_count: 2, used_llm: false, model: null, tier: null,
    },
    {
      id: "risk_assessment", agent_name: "Risk Assessment", depth: 4, status: "ok", confidence_tier: "HIGH",
      latency_ms: 40, reasoning_summary: "Worst-tier rollup across the three inputs above → verdict CAUTION (wave height exceeded).",
      source_count: 4, used_llm: false, model: null, tier: null,
    },
    {
      id: "visualization", agent_name: "Visualization", depth: 4, status: "ok", confidence_tier: "HIGH",
      latency_ms: 75, reasoning_summary: "Built 3 map layers and 2 charts; all passed validate_payload.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
    {
      id: "reporting", agent_name: "Reporting", depth: 5, status: "ok", confidence_tier: "HIGH",
      latency_ms: 720, reasoning_summary: "Assembled the English narrative, citing 4 sources. No causal-claim issue raised.",
      source_count: 4, used_llm: true, model: "gemini-3.5-flash-lite", tier: "mid",
    },
    {
      id: "language_egress", agent_name: "Language Egress", depth: 6, status: "ok", confidence_tier: "HIGH",
      latency_ms: 410, reasoning_summary: "Translated the verdict and reasoning back to Tamil.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
  ],
  edges: [
    { from: "distress_check", to: "language_ingress", kind: "handoff" },
    { from: "language_ingress", to: "planning", kind: "handoff" },
    { from: "planning", to: "weather_intelligence", kind: "handoff" },
    { from: "planning", to: "geospatial", kind: "handoff" },
    { from: "planning", to: "ocean_analytics", kind: "handoff" },
    { from: "weather_intelligence", to: "risk_assessment", kind: "handoff" },
    { from: "geospatial", to: "risk_assessment", kind: "handoff" },
    { from: "ocean_analytics", to: "risk_assessment", kind: "handoff" },
    { from: "weather_intelligence", to: "visualization", kind: "handoff" },
    { from: "geospatial", to: "visualization", kind: "handoff" },
    { from: "ocean_analytics", to: "visualization", kind: "handoff" },
    { from: "risk_assessment", to: "reporting", kind: "handoff" },
    { from: "visualization", to: "reporting", kind: "handoff" },
    { from: "reporting", to: "language_egress", kind: "handoff" },
  ],
  groups: [
    { id: "fanout-forecast", node_ids: ["weather_intelligence", "geospatial", "ocean_analytics"], reason: "parallel_fanout" },
    { id: "fanout-synthesis", node_ids: ["risk_assessment", "visualization"], reason: "parallel_fanout" },
  ],
};
