// D1's real `TraceGraph` payload and `GET /trace/{query_id}` replay API
// (plan §5.1, orca/api/trace_routes.py) now ship — reasoning/page.tsx swaps
// to a live trace via trace-adapter.ts the moment a run through its panel
// finishes. This fixture stays as the page's default/example view (labelled
// "Example trace — replay, not live") and as the shape reference the
// adapter's output is normalized to.
//
// It is not invented data: every node/edge here is the *actual* current
// LangGraph wiring in orca/graph/graph.py (distress_check -> language_ingress
// -> planning -> [weather_intelligence, geospatial, ocean_analytics] ->
// [risk_assessment, visualization] -> reporting -> language_egress), with
// plausible-but-labelled-as-example per-node numbers. It does not include a
// Critic node/`critic_loop` edge — the Critic only appears on a DEEP query
// that it actually flagged, and a real one now shows up automatically for
// any live trace where that happened, so a fixture stand-in isn't needed.
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
  // P2.1 (`R-JUDGE-1`) — what actually computed this node: "Deterministic"
  // for the safety path, the local IndicTrans2 weights for Agent 1, a model
  // id for a node that really reached a provider. Optional only so the
  // hand-written fixture below does not have to be rewritten; every live and
  // replayed node carries it.
  engine?: string;
  // P2.7/P2.12 — why a node did not run, when it did not.
  skip_reason?: string | null;
  // How many times this agent ran in the query. A Critic-driven re-invocation runs the named
  // specialist, Reporting and the Critic a second time; the graph draws one node per agent and
  // says so here rather than drawing duplicates.
  run_count?: number;
  inputs_consumed?: Record<string, any>;
  outputs?: Record<string, any>;
  source_provenance?: {
    dataset: string;
    acquisition_timestamp: string;
    freshness_minutes: number;
  } | null;
  // orca/confidence_score.py — the measured score behind confidence_tier.
  confidence_score?: number | null;
  confidence_detail?: ConfidenceDetail | null;
};

export type ConfidenceDetail = {
  score: number;
  label: ConfidenceTier;
  rule_label: ConfidenceTier;
  rule_rationale: string;
  capped_by_rule_label: boolean;
  factors: { factor: string; value: number | null; detail: string }[];
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
      latency_ms: 610, reasoning_summary: "Matched SAFETY_CHECK on the keyword rules; handed the data-source decision to Marine Data Discovery.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
    {
      id: "marine_data_discovery", agent_name: "Marine Data Discovery", depth: 3, status: "ok", confidence_tier: "HIGH",
      latency_ms: 8, reasoning_summary: "Chose a source for each data type and validated the ones held on disk; the specialists consume this decision.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
    {
      id: "weather_intelligence", agent_name: "Weather Intelligence", depth: 4, status: "ok", confidence_tier: "HIGH",
      latency_ms: 480, reasoning_summary: "Hs 2.4 m vs small_fishing class band 2.0 m → exceeded. Wind 22 km/h, no lightning.",
      source_count: 2, used_llm: false, model: null, tier: null,
    },
    {
      id: "geospatial", agent_name: "Geospatial", depth: 4, status: "ok", confidence_tier: "HIGH",
      latency_ms: 190, reasoning_summary: "0.8 nm from the Sri Lanka EEZ (IMBL proxy) — CAUTION band, no MPA violation.",
      source_count: 3, used_llm: false, model: null, tier: null,
    },
    {
      id: "ocean_analytics", agent_name: "Ocean Analytics", depth: 4, status: "ok", confidence_tier: "MEDIUM",
      latency_ms: 260, reasoning_summary: "Falling tide, nearest PFZ 4.2 km. SOI table gap forced a Stormglass fallback.",
      source_count: 2, used_llm: false, model: null, tier: null,
    },
    {
      id: "risk_assessment", agent_name: "Risk Assessment", depth: 5, status: "ok", confidence_tier: "HIGH",
      latency_ms: 40, reasoning_summary: "Worst-tier rollup across the three inputs above → verdict CAUTION (wave height exceeded).",
      source_count: 4, used_llm: false, model: null, tier: null,
    },
    {
      id: "visualization", agent_name: "Visualization", depth: 5, status: "ok", confidence_tier: "HIGH",
      latency_ms: 75, reasoning_summary: "Built 3 map layers and 2 charts; all passed validate_payload.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
    {
      id: "reporting", agent_name: "Reporting", depth: 6, status: "ok", confidence_tier: "HIGH",
      latency_ms: 720, reasoning_summary: "Assembled the English narrative, citing 4 sources. No causal-claim issue raised.",
      source_count: 4, used_llm: true, model: "gemini-3.5-flash-lite", tier: "mid",
    },
    {
      id: "critic", agent_name: "Critic", depth: 7, status: "ok", confidence_tier: "HIGH",
      latency_ms: 1400, reasoning_summary: "Judged the narrative against the measured facts and passed it.",
      source_count: 0, used_llm: true, model: "gemini-3.5-flash-lite", tier: "reasoning",
    },
    {
      id: "language_egress", agent_name: "Language Egress", depth: 8, status: "ok", confidence_tier: "HIGH",
      latency_ms: 410, reasoning_summary: "Translated the verdict and reasoning back to Tamil.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
  ],
  edges: [
    { from: "distress_check", to: "language_ingress", kind: "handoff" },
    { from: "language_ingress", to: "planning", kind: "handoff" },
    { from: "planning", to: "marine_data_discovery", kind: "handoff" },
    { from: "marine_data_discovery", to: "weather_intelligence", kind: "handoff" },
    { from: "marine_data_discovery", to: "geospatial", kind: "handoff" },
    { from: "marine_data_discovery", to: "ocean_analytics", kind: "handoff" },
    { from: "weather_intelligence", to: "risk_assessment", kind: "handoff" },
    { from: "geospatial", to: "risk_assessment", kind: "handoff" },
    { from: "ocean_analytics", to: "risk_assessment", kind: "handoff" },
    { from: "weather_intelligence", to: "visualization", kind: "handoff" },
    { from: "geospatial", to: "visualization", kind: "handoff" },
    { from: "ocean_analytics", to: "visualization", kind: "handoff" },
    { from: "risk_assessment", to: "reporting", kind: "handoff" },
    { from: "visualization", to: "reporting", kind: "handoff" },
    { from: "reporting", to: "critic", kind: "handoff" },
    { from: "critic", to: "language_egress", kind: "handoff" },
  ],
  groups: [
    { id: "fanout-forecast", node_ids: ["weather_intelligence", "geospatial", "ocean_analytics"], reason: "parallel_fanout" },
    { id: "fanout-synthesis", node_ids: ["risk_assessment", "visualization"], reason: "parallel_fanout" },
  ],
};
