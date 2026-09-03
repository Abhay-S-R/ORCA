"use client";

// Reasoning (D3 plan §5.10, §7) — the graph is drawn from a real execution
// trace, not invented. D1's `GET /trace/{query_id}` (orca/api/trace_routes.py)
// now ships the real `TraceGraph` payload — this page shows a self-authored
// fixture (fixture.ts, matching that contract shape exactly) by default,
// labelled "Example trace — replay, not live", and swaps to the real trace
// the moment a live run through the panel above finishes, via
// trace-adapter.ts. The critic-loop dashed edge and its styling
// (dagre-layout.ts) render for real once a trace that actually looped
// through the Critic is loaded — nothing here fakes one.
//
// The AgentPill status strip below the header is fed by the real `/query`
// SSE stream and is live in real time regardless of which trace the graph
// below is currently showing.
import "@xyflow/react/dist/style.css";
import { ReactFlow, Background, Controls, type Node } from "@xyflow/react";
import { useMemo, useRef, useState } from "react";
import { Workflow, X } from "lucide-react";
import { AgentNode, FanoutGroupNode } from "./AgentNode";
import { EXAMPLE_TRACE, type TraceGraph, type TraceNode } from "./fixture";
import { layoutTrace, type AgentNodeData } from "./dagre-layout";
import { adaptTraceGraph } from "./trace-adapter";
import { AgentPill, AgentStrip, type AgentStatus } from "../components/AgentPill";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { Field, inputClass } from "../components/Field";
import { PageHeader, PageBody } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Stable identity across renders — React Flow warns (and re-mounts nodes) if
// nodeTypes is a fresh object every render.
const nodeTypes = { agent: AgentNode, fanoutGroup: FanoutGroupNode };

type AgentSpan = { agent_name: string; status: AgentStatus };

export default function ReasoningPage() {
  // `liveTrace` is null until a live run's real GET /trace/{query_id} lands —
  // until then the graph shows the labelled example fixture. Swapping one for
  // the other is exactly the "one-line change, not a rebuild" the plan called
  // for once D1 shipped the real TraceGraph endpoint.
  const [liveTrace, setLiveTrace] = useState<TraceGraph | null>(null);
  const [traceLoadError, setTraceLoadError] = useState<string | null>(null);
  const activeTrace = liveTrace ?? EXAMPLE_TRACE;
  // Computed once per trace, not per frame/render — plan §5.10 Day 15's
  // explicit requirement.
  const { nodes, edges } = useMemo(() => layoutTrace(activeTrace), [activeTrace]);
  const [selected, setSelected] = useState<TraceNode | null>(null);

  const [liveQuery, setLiveQuery] = useState("Is it safe to go to sea tomorrow morning?");
  const [spans, setSpans] = useState<AgentSpan[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loadingTrace, setLoadingTrace] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  function runLive(e: React.FormEvent) {
    e.preventDefault();
    sourceRef.current?.close();
    setSpans([]);
    setStreaming(true);
    setTraceLoadError(null);
    const es = new EventSource(`${API_BASE}/query?q=${encodeURIComponent(liveQuery)}`);
    sourceRef.current = es;
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type === "agent_span") {
        setSpans((prev) => [...prev, { agent_name: data.agent_name, status: data.status }]);
      } else if (data.type === "final_response") {
        setStreaming(false);
        es.close();
        if (data.query_id) void loadLiveTrace(data.query_id);
      }
    };
    es.onerror = () => {
      setStreaming(false);
      es.close();
    };
  }

  async function loadLiveTrace(queryId: string) {
    setLoadingTrace(true);
    setSelected(null);
    try {
      const res = await fetch(`${API_BASE}/trace/${queryId}`);
      if (!res.ok) throw new Error(`trace fetch failed: ${res.status}`);
      setLiveTrace(adaptTraceGraph(await res.json()));
    } catch {
      // The graph stays on whatever it was already showing — a missing
      // trace is a degraded state, never a broken page (Ground Rule 3).
      setTraceLoadError("Could not load this query's trace — showing the example trace instead.");
    } finally {
      setLoadingTrace(false);
    }
  }

  return (
    <PageBody className="mx-auto max-w-6xl">
      <PageHeader
        title="Reasoning"
        lede="One node per agent, drawn from a real execution trace — what it did, how confident it was, and what it handed to next."
      />

      <Panel dense title="Live pipeline" className="mb-5">
        <form onSubmit={runLive} className="mb-3 flex items-end gap-2">
          <div className="flex-1">
            <Field label="Ask ORCA">
              {(id) => (
                <input id={id} value={liveQuery} onChange={(e) => setLiveQuery(e.target.value)} className={inputClass} />
              )}
            </Field>
          </div>
          <Button type="submit" variant="primary" disabled={streaming} icon={<Workflow className="size-4" />}>
            {streaming ? "Running" : "Run"}
          </Button>
        </form>
        {spans.length > 0 ? (
          <AgentStrip>
            {spans.map((s, i) => (
              <AgentPill key={`${s.agent_name}-${i}`} name={s.agent_name} status={s.status} />
            ))}
            {streaming && <AgentPill name="working" status="running" />}
          </AgentStrip>
        ) : (
          <p className="text-[11px] text-ink-dim">
            Run a real query to see which agents actually fire, in real time — the strip above is live. Once it
            finishes, the graph below swaps to that query&apos;s own real trace, replayed from what actually ran.
          </p>
        )}
      </Panel>

      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {liveTrace ? (
            <>
              <Badge tone="accent">Live trace — your last query</Badge>
              <button
                type="button"
                onClick={() => setLiveTrace(null)}
                className="text-[11px] text-ink-dim underline decoration-dotted hover:text-ink"
              >
                back to example trace
              </button>
            </>
          ) : (
            <Badge tone="neutral">{loadingTrace ? "Loading your trace…" : "Example trace — replay, not live"}</Badge>
          )}
          {traceLoadError && <span className="text-[11px] text-caution">{traceLoadError}</span>}
        </div>
        <p className="text-[11px] text-ink-dim">Click a node for its full reasoning and sources.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div
          className="h-[560px] overflow-hidden rounded-md border border-hairline bg-shelf-1/40"
          // React Flow's built-in Enter/Space-to-select keyboard handling
          // (and its onSelectionChange callback) doesn't reliably reach a
          // freshly Tab-focused node in this graph, so the inspector was
          // mouse-only despite every node advertising "press enter or space
          // to select" (plan §7 a11y: node-to-node keyboard navigation).
          // Handling it ourselves at the container level, from the same
          // data-id every node already carries, sidesteps that and keeps
          // keyboard selection working the same way the mouse path does.
          onKeyDown={(e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            const id = (e.target as HTMLElement).closest<HTMLElement>("[data-id]")?.getAttribute("data-id");
            const node = id ? activeTrace.nodes.find((n) => n.id === id) : undefined;
            if (node) setSelected(node);
          }}
        >
          <ReactFlow
            nodes={nodes as Node[]}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={(_, n) => {
              const data = n.data as AgentNodeData | undefined;
              if (data?.node) setSelected(data.node);
            }}
            onPaneClick={() => setSelected(null)}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            // Default minZoom (0.5) can't zoom out far enough to fit a wide
            // trace (this graph's ~9 ranks), so fitView clips the leftmost
            // and rightmost nodes outside the visible/interactive container
            // instead of shrinking further to fit them.
            minZoom={0.1}
            proOptions={{ hideAttribution: true }}
            colorMode="dark"
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
          >
            <Background gap={22} color="#17384c" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        <div>
          {!selected ? (
            <Panel title="Inspector">
              <p className="text-xs text-ink-muted">Select a node to see its full reasoning, sources and hand-off.</p>
            </Panel>
          ) : (
            <Panel
              title={selected.agent_name}
              action={
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  onKeyDown={(e) => e.key === "Escape" && setSelected(null)}
                  aria-label="Close inspector"
                  className="text-ink-dim hover:text-ink"
                >
                  <X className="size-4" />
                </button>
              }
            >
              <ConfidenceMeter tier={selected.confidence_tier} />
              <p className="mt-3 text-[13px] leading-relaxed text-ink">{selected.reasoning_summary}</p>
              <ReadoutGrid cols={2}>
                <Readout label="Latency" value={selected.latency_ms} unit="ms" />
                <Readout label="Sources" value={selected.source_count} />
              </ReadoutGrid>
              <p className="mt-3 border-t border-hairline pt-3 text-[11px] text-ink-dim">
                {selected.used_llm
                  ? selected.tier && selected.model
                    ? `Used the ${selected.tier} LLM tier (${selected.model}).`
                    : "Used an LLM (tier and model aren't recorded on this trace)."
                  : "Deterministic — no LLM call (Ground Rule: specialist agents shape data, they don't reason over it with an LLM)."}
              </p>
            </Panel>
          )}
        </div>
      </div>
    </PageBody>
  );
}
