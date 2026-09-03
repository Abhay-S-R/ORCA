"use client";

// Reasoning (D3 plan §5.10, §7) — the graph is drawn from a real execution
// trace, not invented. D1 owns the live `TraceGraph` payload and the
// `/trace/{query_id}` replay API (plan §5.1); neither ships in this build,
// so this page replays a self-authored fixture (fixture.ts) that matches
// D1's documented contract shape exactly and is labelled "Example trace —
// replay" everywhere it appears, never "Live". Swapping the fixture for a
// real fetch later is a one-line change, not a rewrite.
//
// The optional live piece below the header — a thin AgentPill status strip
// fed by the real `/query` SSE stream — is the one part of this page that
// IS live. It shows *that* the pipeline is really agentic in real time; the
// rich per-node reasoning graph stays replay-only, per the design call this
// page's plan flagged and the user approved as written.
import "@xyflow/react/dist/style.css";
import { ReactFlow, Background, Controls, type Node } from "@xyflow/react";
import { useMemo, useRef, useState } from "react";
import { Workflow, X } from "lucide-react";
import { AgentNode, FanoutGroupNode } from "./AgentNode";
import { EXAMPLE_TRACE, type TraceNode } from "./fixture";
import { layoutTrace, type AgentNodeData } from "./dagre-layout";
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
  // Computed once for this fixture, not per frame/render — plan §5.10 Day
  // 15's explicit requirement.
  const { nodes, edges } = useMemo(() => layoutTrace(EXAMPLE_TRACE), []);
  const [selected, setSelected] = useState<TraceNode | null>(null);

  const [liveQuery, setLiveQuery] = useState("Is it safe to go to sea tomorrow morning?");
  const [spans, setSpans] = useState<AgentSpan[]>([]);
  const [streaming, setStreaming] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  function runLive(e: React.FormEvent) {
    e.preventDefault();
    sourceRef.current?.close();
    setSpans([]);
    setStreaming(true);
    const es = new EventSource(`${API_BASE}/query?q=${encodeURIComponent(liveQuery)}`);
    sourceRef.current = es;
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type === "agent_span") {
        setSpans((prev) => [...prev, { agent_name: data.agent_name, status: data.status }]);
      } else if (data.type === "final_response") {
        setStreaming(false);
        es.close();
      }
    };
    es.onerror = () => {
      setStreaming(false);
      es.close();
    };
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
            Run a real query to see which agents actually fire, in real time. This strip is live; the graph below is
            not — it replays one recorded trace so every node can show its full reasoning, not just a status glyph.
          </p>
        )}
      </Panel>

      <div className="mb-3 flex items-center justify-between">
        <Badge tone="neutral">Example trace — replay, not live</Badge>
        <p className="text-[11px] text-ink-dim">Click a node for its full reasoning and sources.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="h-[560px] overflow-hidden rounded-md border border-hairline bg-shelf-1/40">
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
                  ? `Used the ${selected.tier} LLM tier (${selected.model}).`
                  : "Deterministic — no LLM call (Ground Rule: specialist agents shape data, they don't reason over it with an LLM)."}
              </p>
            </Panel>
          )}
        </div>
      </div>
    </PageBody>
  );
}
