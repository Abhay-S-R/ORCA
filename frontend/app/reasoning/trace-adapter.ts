// Adapts the real `GET /trace/{query_id}` response (backend/orca/api/trace_routes.py)
// into the same `TraceGraph` shape fixture.ts already defines, so `layoutTrace`,
// `AgentNode` and the inspector drawer render live and replayed data identically —
// exactly the "one-line swap, not a rebuild" the D3 plan called for.
//
// `model` and `tier` used to be hardcoded `null` here with a comment saying the
// backend never sends them. It does, and has since the per-node LLM detail
// landed — so the inspector's null-safe branch was doing all the work and the
// drawer showed a default model string instead of the real one. They are now
// read from the response, alongside P2.1's `engine` (what actually computed the
// node) and P2.7/P2.12's `skip_reason`.
import type { AgentStatus } from "../components/AgentPill";
import type { ConfidenceTier } from "../components/Badge";
import type { TraceEdge, TraceGraph, TraceGroup, TraceNode } from "./fixture";

type ApiTraceNode = {
  id: string;
  agent_name: string;
  depth: number;
  status: string;
  confidence_tier: string;
  latency_ms: number | null;
  reasoning_summary: string;
  source_count: number;
  used_llm: boolean;
  engine?: string;
  model?: string | null;
  tier?: string | null;
  skip_reason?: string | null;
  run_count?: number;
};

type ApiTraceEdge = { from: string; to: string; kind: "handoff" | "critic_loop" | "cancelled"; label: string };
type ApiTraceGroup = { id: string; node_ids: string[]; reason: string };
export type ApiTraceGraph = {
  query_id: string;
  nodes: ApiTraceNode[];
  edges: ApiTraceEdge[];
  groups: ApiTraceGroup[];
};

// The backend records one agent_name per run_traced_node call — human labels
// live only in the frontend, same as AgentNode's own ICON map.
const AGENT_LABEL: Record<string, string> = {
  distress: "Distress Check",
  language_ingress: "Language Ingress",
  planning: "Planning",
  // Agent 3, promoted to a real node before the fan-out (P2.6).
  marine_data_discovery: "Marine Data Discovery",
  weather_intelligence: "Weather Intelligence",
  geospatial: "Geospatial",
  ocean_analytics: "Ocean Analytics",
  risk_assessment: "Risk Assessment",
  visualization: "Visualization",
  reporting: "Reporting",
  critic: "Critic",
  language_egress: "Language Egress",
};

const STATUS_SET = new Set<AgentStatus>([
  "pending", "running", "ok", "degraded", "failed", "skipped",
  // P2.12 — an early exit is a real status, not an unknown one. Without it
  // here a cancelled node coerced to "ok" and drew as though it had run.
  "cancelled",
]);
const LLM_TIERS = new Set(["cheap", "mid", "reasoning"]);
const TIER_SET = new Set<ConfidenceTier>(["HIGH", "MEDIUM", "LOW_DATA"]);

function coerceStatus(s: string): AgentStatus {
  return STATUS_SET.has(s as AgentStatus) ? (s as AgentStatus) : "ok";
}

function coerceTier(t: string): ConfidenceTier {
  return TIER_SET.has(t as ConfidenceTier) ? (t as ConfidenceTier) : "LOW_DATA";
}

export function adaptTraceGraph(api: ApiTraceGraph): TraceGraph {
  const nodes: TraceNode[] = api.nodes.map((n) => ({
    id: n.id,
    agent_name: AGENT_LABEL[n.id] ?? n.agent_name,
    depth: n.depth,
    status: coerceStatus(n.status),
    confidence_tier: coerceTier(n.confidence_tier),
    latency_ms: n.latency_ms ?? 0,
    reasoning_summary: n.reasoning_summary,
    source_count: n.source_count,
    used_llm: n.used_llm,
    model: n.model ?? null,
    tier: LLM_TIERS.has(n.tier ?? "") ? (n.tier as "cheap" | "mid" | "reasoning") : null,
    engine: n.engine,
    skip_reason: n.skip_reason ?? null,
    run_count: n.run_count ?? 1,
  }));

  const edges: TraceEdge[] = api.edges.map((e) => ({ from: e.from, to: e.to, kind: e.kind, label: e.label }));
  const groups: TraceGroup[] = api.groups.map((g) => ({ id: g.id, node_ids: g.node_ids, reason: "parallel_fanout" }));

  return { query_id: api.query_id, nodes, edges, groups };
}
