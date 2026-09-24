"use client";

// P6.6 — one scenario card: a title, a one-click Run, the live agent trace
// strip while it runs, and the result — a verdict for an ordinary scenario,
// a distress panel (MRCC + the DAT-SG handoff payload) for scenario 5. Reuses
// the same primitives `/ask` renders with (VerdictBadge, AgentPill,
// FormattedResponse) rather than a second visual language for this surface.
import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertOctagon, ArrowRight, Loader2, Play, RotateCcw } from "lucide-react";
import { AgentPill, AgentStrip } from "../components/AgentPill";
import { Button } from "../components/Button";
import { FormattedResponse } from "../components/FormattedResponse";
import { Panel } from "../components/Panel";
import { SourceChip } from "../components/SourceChip";
import { VerdictBadge } from "../components/VerdictBadge";
import { API_BASE } from "../lib/apiBase";
import type { Scenario } from "./scenarios";
import { useScenarioRun } from "./useScenarioRun";

type DistressOutputs = {
  mrcc_contact?: { primary?: { name?: string; phone?: string; vhf_channel?: string }; nationwide_fallback?: { phone?: string } };
  handoff?: { status?: string; position?: { lat: number; lon: number } | null; distress_type?: string | null; timestamp?: string };
  nabhmitra_text?: string;
};

function useDistressDetail(queryId: string | undefined) {
  const [detail, setDetail] = useState<DistressOutputs | null>(null);
  useEffect(() => {
    if (!queryId) return;
    let cancelled = false;
    fetch(`${API_BASE}/trace/${queryId}`)
      .then((r) => r.json())
      .then((trace: { nodes?: { agent_name: string; outputs?: DistressOutputs }[] }) => {
        if (cancelled) return;
        const node = trace.nodes?.find((n) => n.agent_name === "distress");
        setDetail(node?.outputs ?? null);
      })
      .catch(() => !cancelled && setDetail(null));
    return () => {
      cancelled = true;
    };
  }, [queryId]);
  return detail;
}

export function ScenarioCard({ scenario }: { scenario: Scenario }) {
  const { spans, answer, streaming, failed, run, reset } = useScenarioRun();
  const isDistress = answer?.outcome === "DISTRESS";
  const distressDetail = useDistressDetail(isDistress ? answer?.query_id : undefined);

  const disabled = scenario.kind !== "live";

  return (
    <Panel
      title={scenario.title}
      action={
        scenario.kind === "link" && scenario.href ? (
          <Link
            href={scenario.href}
            className="flex items-center gap-1.5 rounded-full border border-hairline-strong bg-shelf-2 px-3 py-1.5 text-xs font-semibold text-ink transition-colors hover:border-ocean-cyan/60 hover:text-ocean-cyan"
          >
            Open on /voyage
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        ) : answer || streaming ? (
          <Button icon={<RotateCcw className="size-3.5" />} onClick={reset} disabled={streaming}>
            Reset
          </Button>
        ) : (
          <Button
            variant="primary"
            icon={streaming ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
            disabled={disabled || streaming}
            onClick={() => scenario.buildUrl && run(scenario.buildUrl())}
          >
            {disabled ? "Not yet built" : "Run"}
          </Button>
        )
      }
    >
      <p className="mb-4 text-sm leading-relaxed text-ink-muted">{scenario.summary}</p>

      {(spans.length > 0 || streaming) && (
        <div className="mb-4">
          <AgentStrip>
            {spans.map((s, i) => (
              <AgentPill key={`${s.agent_name}-${i}`} name={s.agent_name} status={s.status} engine={s.engine} confidence={s.confidence_tier} latencyMs={s.latency_ms} skipReason={s.skip_reason} />
            ))}
          </AgentStrip>
        </div>
      )}

      {failed && <p className="text-sm text-no-go">The scenario run failed — check the backend is reachable.</p>}

      {answer && !isDistress && answer.risk_assessment && (
        <div className="space-y-3">
          <VerdictBadge verdict={answer.risk_assessment.go_no_go} confidenceTier={answer.confidence_tier} summary={answer.risk_assessment.reason} />
          <FormattedResponse text={answer.final_english_response} language={answer.detected_language} />
          {/* "full provenance trail" (this scenario's own summary text) means
              this, not just the verdict badge — the same citation chips
              `/ask` renders, so a pinned demo fixture reading is traceable
              exactly like a live one, including which agent read it and when
              the pinned reading was captured. */}
          {answer.citations && answer.citations.length > 0 && (
            <div className="flex flex-col gap-1.5 border-t border-hairline/50 pt-3">
              <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">Provenance trail</span>
              <div className="flex flex-wrap gap-1.5">
                {answer.citations.map((c, i) => (
                  <SourceChip key={i} dataset={c.dataset} acquisitionTimestamp={c.acquisition_timestamp} agentName={c.agent_name} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {answer && isDistress && (
        <div className="space-y-3 rounded-xl border border-no-go/45 bg-no-go/5 p-4">
          <p className="flex items-center gap-2 text-sm font-bold text-no-go">
            <AlertOctagon className="size-4 shrink-0" aria-hidden="true" />
            DISTRESS DETECTED — the graph bypassed every other node
          </p>
          <FormattedResponse text={answer.final_english_response} />
          {distressDetail?.handoff && (
            <div className="rounded-lg border border-hairline/60 bg-shelf-1/60 p-3 font-mono text-[11px] leading-relaxed text-ink-muted">
              <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-ink-dim">DAT-SG handoff payload (SIMULATED — no live transport)</p>
              <p>status: {distressDetail.handoff.status}</p>
              <p>
                position:{" "}
                {distressDetail.handoff.position
                  ? `${distressDetail.handoff.position.lat.toFixed(4)}N ${distressDetail.handoff.position.lon.toFixed(4)}E`
                  : "none given"}
              </p>
              <p>distress_type: {distressDetail.handoff.distress_type}</p>
              {distressDetail.nabhmitra_text && <p className="mt-2 break-all">Nabhmitra line: {distressDetail.nabhmitra_text}</p>}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
