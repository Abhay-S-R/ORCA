"use client";

// The design system gallery (§4.1). Every primitive in every state, on one
// page, so the Friday UI-consistency check is mechanical rather than a
// judgement call — and so the axe-core pass has one place to run first.
//
// Deliberately not in NAV_ROUTES: it is a team tool, not a product surface.
import "@xyflow/react/dist/style.css";
import { ReactFlow, Background, type Node } from "@xyflow/react";
import { useMemo, useState } from "react";
import { Anchor } from "lucide-react";
import { AgentPill, AgentStrip, type AgentStatus } from "../components/AgentPill";
import { Badge, type BadgeTone, type ConfidenceTier, type Verdict } from "../components/Badge";
import { Button } from "../components/Button";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { Field, inputClass } from "../components/Field";
import { LayerToggle } from "../components/LayerToggle";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Card, Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { AgentNode, FanoutGroupNode } from "../reasoning/AgentNode";
import { layoutTrace } from "../reasoning/dagre-layout";
import type { TraceGraph } from "../reasoning/fixture";
import { SourceChip } from "../components/SourceChip";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { TimeSlider } from "../components/TimeSlider";
import { VerdictBadge } from "../components/VerdictBadge";
import { FeedbackControl } from "../components/FeedbackControl";
import { WatchCard } from "../components/WatchCard";

// Stable identity — same reason /reasoning/page.tsx defines this at module
// scope: a fresh object per render makes React Flow warn and remount nodes.
const nodeTypes = { agent: AgentNode, fanoutGroup: FanoutGroupNode };

// One node per AgentStatus, one confidence tier not otherwise covered by
// the "Agent activity" AgentPill row above, and a real parallel-fanout pair
// — not the /reasoning trace, so nothing here implies a query actually ran.
const GALLERY_TRACE: TraceGraph = {
  query_id: "design-gallery",
  nodes: [
    {
      id: "weather_intelligence", agent_name: "Weather Intelligence", depth: 0, status: "pending",
      confidence_tier: "HIGH", latency_ms: 0, reasoning_summary: "Queued — waiting on planning's fan-out.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
    {
      id: "geospatial", agent_name: "Geospatial", depth: 1, status: "running",
      confidence_tier: "HIGH", latency_ms: 0, reasoning_summary: "Computing distance to the IMBL proxy…",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
    {
      id: "ocean_analytics", agent_name: "Ocean Analytics", depth: 2, status: "ok",
      confidence_tier: "HIGH", latency_ms: 260, reasoning_summary: "Falling tide, nearest PFZ 4.2 km.",
      source_count: 2, used_llm: false, model: null, tier: null,
    },
    {
      id: "risk_assessment", agent_name: "Risk Assessment", depth: 2, status: "ok",
      confidence_tier: "MEDIUM", latency_ms: 40, reasoning_summary: "Worst-tier rollup — one input stale beyond 6h.",
      source_count: 3, used_llm: false, model: null, tier: null,
    },
    {
      id: "visualization", agent_name: "Visualization", depth: 3, status: "ok",
      confidence_tier: "LOW_DATA", latency_ms: 75, reasoning_summary: "Built map layers from a partial input set.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
    {
      id: "reporting", agent_name: "Reporting", depth: 4, status: "failed",
      confidence_tier: "MEDIUM", latency_ms: 900, reasoning_summary: "LLM call timed out after 3 retries.",
      source_count: 4, used_llm: true, model: "gemini-3.5-flash-lite", tier: "mid",
    },
    {
      id: "language_egress", agent_name: "Language Egress", depth: 5, status: "skipped",
      confidence_tier: "LOW_DATA", latency_ms: 0, reasoning_summary: "Skipped — upstream reporting failed.",
      source_count: 0, used_llm: false, model: null, tier: null,
    },
  ],
  edges: [
    { from: "weather_intelligence", to: "geospatial", kind: "handoff" },
    { from: "geospatial", to: "ocean_analytics", kind: "handoff" },
    { from: "geospatial", to: "risk_assessment", kind: "handoff" },
    { from: "ocean_analytics", to: "visualization", kind: "handoff" },
    { from: "risk_assessment", to: "visualization", kind: "handoff" },
    { from: "visualization", to: "reporting", kind: "handoff" },
    { from: "reporting", to: "language_egress", kind: "handoff" },
  ],
  groups: [{ id: "fanout-demo", node_ids: ["ocean_analytics", "risk_assessment"], reason: "parallel_fanout" }],
};

const TONES: BadgeTone[] = ["go", "caution", "no-go", "neutral", "accent"];
const VERDICTS: Verdict[] = ["GO", "CAUTION", "NO_GO"];
const TIERS: ConfidenceTier[] = ["HIGH", "MEDIUM", "LOW_DATA"];
const STATUSES: AgentStatus[] = ["pending", "running", "ok", "failed", "skipped"];

const FRAMES = Array.from({ length: 8 }, (_, i) => ({
  t: new Date(Date.UTC(2026, 8, 3, 6 + i * 3)).toISOString(),
}));

// Class names are written out in full — Tailwind scans source text, so a
// `bg-${name}` template would compile to nothing.
const TOKENS: [string, string, string][] = [
  ["abyss", "bg-abyss", "Page base"],
  ["shelf-1", "bg-shelf-1", "Panel"],
  ["shelf-2", "bg-shelf-2", "Raised"],
  ["shelf-3", "bg-shelf-3", "Active"],
  ["shoal", "bg-shoal", "Highlight"],
  ["go", "bg-go", "Verdict only"],
  ["caution", "bg-caution", "Verdict only"],
  ["no-go", "bg-no-go", "Verdict only"],
  ["accent", "bg-accent", "Interactive only"],
];

export default function DesignPage() {
  const [layer, setLayer] = useState(true);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const { nodes: galleryNodes, edges: galleryEdges } = useMemo(() => layoutTrace(GALLERY_TRACE), []);

  return (
    <PageBody className="mx-auto max-w-4xl">
      <PageHeader
        title="Design system"
        lede="Every ORCA primitive in every state. If a surface needs something that is not on this page, it belongs on this page first."
      />

      <div className="flex flex-col gap-4">
        <Section title="Colour tokens">
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
            {TOKENS.map(([name, cls, use]) => (
              <div key={name}>
                <div className={`h-12 rounded-sm border border-hairline ${cls}`} />
                <p className="mt-1 text-[11px] text-ink">{name}</p>
                <p className="text-[10px] text-ink-dim">{use}</p>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Type">
          <p className="text-2xl font-semibold tracking-tight text-ink">Barlow — headings and interface</p>
          <p className="mt-1 max-w-[60ch] text-sm text-ink-muted">
            Body copy sits at 60 characters or fewer per line. Barlow is condensed enough to keep bilingual
            labels on one line and legible enough to read at an angle in bright sun.
          </p>
          <p className="mt-1 font-tamil text-sm text-ink-muted">
            தமிழ் — நோட்டோ சான்ஸ் தமிழ், முதன்மைப் பயனருக்கானது.
          </p>
          <p data-readout className="mt-2 text-lg text-ink">
            1 234.56 · 087° · 08.800, 078.140 — IBM Plex Mono, numbers only
          </p>
        </Section>

        <Section title="Verdict">
          <div className="flex flex-col gap-3">
            {VERDICTS.map((v) => (
              <VerdictBadge key={v} verdict={v} summary="Wave height 2.8 m exceeds the small-boat threshold." />
            ))}
          </div>
        </Section>

        <Section title="Badges and confidence">
          <div className="mb-4 flex flex-wrap gap-2">
            {TONES.map((t) => (
              <Badge key={t} tone={t}>
                {t}
              </Badge>
            ))}
          </div>
          <div className="flex flex-col gap-2">
            {TIERS.map((t) => (
              <ConfidenceMeter key={t} tier={t} />
            ))}
          </div>
        </Section>

        <Section title="Readouts">
          <ReadoutGrid cols={4}>
            <Readout label="Wave height" value="2.8" unit="m" />
            <Readout label="Wind speed" value="41.2" unit="km/h" />
            <Readout label="Depth" value="—" hint="No reading" />
            <Readout label="Bearing" value="087°" hint="12.4 nm" />
          </ReadoutGrid>
        </Section>

        <Section title="Provenance">
          <div className="flex flex-wrap gap-2">
            {TIERS.map((t) => (
              <SourceChip
                key={t}
                dataset="INCOIS Ocean State Forecast"
                acquisitionTimestamp="2026-09-03T04:30:00Z"
                confidenceTier={t}
                detail="Click a chip to expand the full provenance record."
              />
            ))}
          </div>
        </Section>

        <Section title="Agent activity">
          <AgentStrip>
            {STATUSES.map((s) => (
              <AgentPill key={s} name={s} status={s} latencyMs={s === "ok" ? 412 : undefined} />
            ))}
          </AgentStrip>
        </Section>

        <Section title="Reasoning graph — AgentNode & FanoutGroupNode">
          <p className="mb-3 text-[11px] text-ink-dim">
            Border is confidence tier, fill is execution status — every AgentStatus, plus a confidence tier the
            AgentPill row above doesn&apos;t cover, and a real parallel-fanout group. Not a query result: see{" "}
            <a href="/reasoning" className="underline">
              /reasoning
            </a>{" "}
            for that.
          </p>
          <div className="h-[300px] overflow-hidden rounded-md border border-hairline bg-shelf-1/40">
            <ReactFlow
              nodes={galleryNodes as Node[]}
              edges={galleryEdges}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.15 }}
              proOptions={{ hideAttribution: true }}
              colorMode="dark"
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
              zoomOnScroll={false}
              panOnDrag={false}
            >
              <Background gap={22} color="#17384c" />
            </ReactFlow>
          </div>
        </Section>

        <Section title="Controls">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <div className="mb-3 flex flex-wrap gap-2">
                <Button variant="primary">Check safety</Button>
                <Button variant="ghost">Cancel</Button>
                <Button variant="danger">Send distress alert</Button>
                <Button variant="primary" disabled>
                  Disabled
                </Button>
              </div>
              <Field label="Home port" hint="Used for distance and bearing.">
                {(id) => <input id={id} className={inputClass} defaultValue="Thoothukudi" />}
              </Field>
            </div>
            <div>
              <LayerToggle label="Boundaries" swatch="#22617f" checked={layer} onChange={setLayer} />
              <LayerToggle label="Depth shading" swatch="#7fd4e8" heavy checked={false} onChange={() => {}} />
              <LayerToggle
                label="Wind field"
                swatch="#f0468c"
                checked={false}
                onChange={() => {}}
                disabled
                disabledReason="Two heavy layers already active on mobile"
              />
              <div className="mt-3">
                <TimeSlider
                  frames={FRAMES}
                  index={frame}
                  onIndexChange={setFrame}
                  playing={playing}
                  onPlayingChange={setPlaying}
                />
              </div>
            </div>
          </div>
        </Section>

        <Section title="Surfaces">
          <div className="grid gap-3 sm:grid-cols-2">
            <Panel title="Panel — glass, over the chart">
              <p className="text-sm text-ink-muted">Blurred so the chart stays readable underneath.</p>
            </Panel>
            <Card title="Card — opaque, in page flow">
              <p className="text-sm text-ink-muted">No backdrop cost where nothing sits behind it.</p>
            </Card>
          </div>
        </Section>

        <Section title="Loading, empty and error">
          <div className="mb-3 flex flex-col gap-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-full" />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <EmptyState
              icon={<Anchor className="size-6" />}
              title="No watches set"
              body="A watch tells you when conditions at a place you care about cross your thresholds."
              action={<Button variant="primary">Set a watch</Button>}
            />
            <ErrorState
              title="Could not reach the ORCA API"
              body="The service did not respond. Start the backend, then try again."
              action={<Button variant="ghost">Try again</Button>}
            />
          </div>
        </Section>

        {/* Phase 3 D2 — Sentinel / alerting / feedback primitives. Built on
            the existing tokens; every state shown so the Day-21 axe pass has
            them. */}
        <Section title="Notification feed (D2)">
          <div className="flex flex-col gap-2">
            {(["info", "advisory", "warning", "danger"] as const).map((sev) => (
              <div key={sev} className="glass rounded-md border-l-2 border-accent p-3 text-sm">
                <p className="flex items-center gap-2 font-semibold text-ink">
                  <Badge tone={{ info: "neutral", advisory: "accent", warning: "caution", danger: "no-go" }[sev] as BadgeTone}>
                    {sev}
                  </Badge>
                  Conditions worsened to CAUTION
                </p>
                <p className="mt-1 text-ink-muted">Forecast wave height 3.1 m at your watch point.</p>
                {sev !== "info" && (
                  <p className="mt-1 text-[11px] text-ink-dim">
                    Channel <span className="text-ink-muted">sms</span> — SIMULATED, no message transmitted.
                  </p>
                )}
              </div>
            ))}
          </div>
        </Section>

        <Section title="Advisory feedback (D2)">
          <FeedbackControl queryId="00000000-0000-0000-0000-000000000000" advisoryRef="demo" />
        </Section>

        <Section title="Watch card (D2)">
          <WatchCard
            watch={{
              id: "demo",
              watch_type: "wave_height",
              lat: 8.8,
              lon: 78.14,
              radius_km: 10,
              vessel_id: null,
              thresholds: { wave_height_m: 2.5 },
              channels: ["in_app"],
              enabled: true,
              last_fired_at: null,
              created_at: new Date().toISOString(),
            }}
            onChange={() => {}}
          />
        </Section>
      </div>
    </PageBody>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-hairline bg-shelf-1/40 p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">{title}</h2>
      {children}
    </section>
  );
}
