// Adapts the real `GET /trace/{query_id}` response (backend/orca/api/trace_routes.py)
// into the same `TraceGraph` shape fixture.ts already defines, so `layoutTrace`,
// `AgentNode` and the inspector drawer render live and replayed data identically —
// exactly the "one-line swap, not a rebuild" the D3 plan called for.
//
// Two fields the backend never sends (`model`, `tier` — that's D1's per-node LLM
// detail, not yet on the wire) are set to `null` here; the inspector drawer
// already has a null-safe branch for them.
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
  weather_intelligence: "Weather Intelligence",
  geospatial: "Geospatial",
  ocean_analytics: "Ocean Analytics",
  risk_assessment: "Risk Assessment",
  visualization: "Visualization",
  reporting: "Reporting",
  critic: "Critic",
  language_egress: "Language Egress",
};

const STATUS_SET = new Set<AgentStatus>(["pending", "running", "ok", "degraded", "failed", "skipped"]);
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
    model: null,
    tier: null,
  }));

  const edges: TraceEdge[] = api.edges.map((e) => ({ from: e.from, to: e.to, kind: e.kind, label: e.label }));
  const groups: TraceGroup[] = api.groups.map((g) => ({ id: g.id, node_ids: g.node_ids, reason: "parallel_fanout" }));

  return { query_id: api.query_id, nodes, edges, groups };
}
