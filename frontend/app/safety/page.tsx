"use client";

// Safety (§4.2 `/safety`) — the go/no-go surface. The verdict is the loudest
// object on this page by a wide margin, and everything beneath it is the
// evidence, rendered plainly. Every number carries its source (criterion 4).
import { useRef, useState } from "react";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import { AgentPill, AgentStrip, nextRunningAgent, type AgentStatus } from "../components/AgentPill";
import { Badge, type ConfidenceTier, type Verdict } from "../components/Badge";
import { Button } from "../components/Button";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { Field, inputClass } from "../components/Field";
import { PageHeader, PageBody } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceChip } from "../components/SourceChip";
import { EmptyState, Skeleton } from "../components/States";
import { VerdictBadge } from "../components/VerdictBadge";
import { FormattedResponse } from "../components/FormattedResponse";
import { API_BASE } from "../lib/apiBase";

type VesselClass = "small_fishing" | "mechanized_trawler" | "cargo_vessel";
const VESSEL_LABELS: Record<VesselClass, string> = {
  small_fishing: "Small fishing boat",
  mechanized_trawler: "Mechanized trawler",
  cargo_vessel: "Cargo vessel",
};

// Vessel-class threshold deltas (Architecture §3.1 Agent 7) — shown so the
// selector explains itself, rather than silently moving the verdict with no
// visible reason.
const VESSEL_DELTAS: Record<VesselClass, string> = {
  small_fishing: "Most conservative — base thresholds",
  mechanized_trawler: "Tolerates +9.3 km/h wind, +0.5 m wave",
  cargo_vessel: "Tolerates +27.8 km/h wind, +1.5 m wave",
};

type AgentSpan = { agent_name: string; status: AgentStatus };
type Citation = { agent_name: string; dataset: string; acquisition_timestamp: string; freshness_minutes: number };
type SafetyResponse = {
  final_vernacular_response: string;
  confidence_tier: ConfidenceTier;
  risk_assessment: { status: string; go_no_go: Verdict; reason: string } | null;
  citations: Citation[];
  distress_flag: boolean;
  weather_summary: {
    wave_height_m: number | null;
    wind_speed_ms: number | null;
    lightning_active: boolean;
    cyclone_alert: string | null;
    // Cross-source agreement between Open-Meteo's CAPE proxy and IMD's own
    // district nowcast. "single_source" means the IMD snapshot is empty here
    // or past its validity window — not that the two agree.
    lightning_source_agreement?: "agree" | "disagree" | "single_source";
    imd_nowcast?: {
      alert_count: number;
      lightning_flagged: boolean;
      expired: boolean;
      radius_km: number;
      alerts: { district: string; event_category: string; severity: string; distance_km: number; events: string }[];
    } | null;
  };
  hazard_breakdown: {
    imbl_distance_nm: number | null;
    imbl_alert_level: string | null;
    mpa_violation: boolean;
    mpa_alert_level: string | null;
  };
};

export default function SafetyPage() {
  const [query, setQuery] = useState("Is it safe to go to sea tomorrow morning?");
  const [vesselClass, setVesselClass] = useState<VesselClass>("small_fishing");
  const [spans, setSpans] = useState<AgentSpan[]>([]);
  const [answer, setAnswer] = useState<SafetyResponse | null>(null);
  const [streaming, setStreaming] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  function check(e: React.FormEvent) {
    e.preventDefault();
    sourceRef.current?.close();
    setSpans([]);
    setAnswer(null);
    setStreaming(true);

    const es = new EventSource(
      `${API_BASE}/query?q=${encodeURIComponent(query)}&vessel_class=${vesselClass}`,
    );
    sourceRef.current = es;
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type === "agent_span") {
        setSpans((prev) => [...prev, { agent_name: data.agent_name, status: data.status }]);
      } else if (data.type === "final_response") {
        setAnswer(data);
        setStreaming(false);
        es.close();
      }
    };
    es.onerror = () => {
      setStreaming(false);
      es.close();
    };
  }

  const weatherCite = answer?.citations.find((c) => c.agent_name === "weather_intelligence");
  const geoCite = answer?.citations.find((c) => c.agent_name === "geospatial");

  const displaySpans =
    spans.length > 0
      ? spans
      : answer
      ? AGENT_ORDER.map((name) => ({ agent_name: name, status: "ok" as AgentStatus }))
      : [];

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="Can I go out?"
        lede="Pick your vessel and ask. The verdict accounts for wave height, wind, lightning, cyclone alerts and how close you are to a boundary you must not cross."
      />

      <div className="mb-6 rounded-2xl border border-hairline bg-shelf-1/80 p-5 shadow-xl backdrop-blur-md">
        <form onSubmit={check}>
          <div className="grid gap-x-5 sm:grid-cols-2">
            <Field label="Question">
              {(id) => (
                <input id={id} value={query} onChange={(e) => setQuery(e.target.value)} className={inputClass} />
              )}
            </Field>
            <Field label="Vessel class" hint={VESSEL_DELTAS[vesselClass]}>
              {(id) => (
                <select
                  id={id}
                  value={vesselClass}
                  onChange={(e) => setVesselClass(e.target.value as VesselClass)}
                  className={inputClass}
                >
                  {(Object.keys(VESSEL_LABELS) as VesselClass[]).map((v) => (
                    <option key={v} value={v} className="bg-shelf-2">
                      {VESSEL_LABELS[v]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <div className="mt-2 flex items-center justify-between pt-2 border-t border-hairline/50">
            <span className="font-mono text-[10px] text-ink-dim uppercase">
              THRESHOLD SAFETY GATE // AGENT 7
            </span>
            <Button type="submit" variant="primary" disabled={streaming} icon={<ShieldCheck className="size-4" />}>
              {streaming ? "Evaluating Telemetry..." : "Check Safety Verdict"}
            </Button>
          </div>
        </form>
      </div>

      {displaySpans.length > 0 && (
        <div className="mb-5 min-w-0 max-w-full">
          <AgentStrip>
            {displaySpans.map((s, i) => (
              <AgentPill key={`${s.agent_name}-${i}`} name={s.agent_name} status={s.status} />
            ))}
            {streaming &&
              (() => {
                const next = nextRunningAgent(spans);
                return next && <AgentPill name={next} status="running" />;
              })()}
          </AgentStrip>
        </div>
      )}

      {streaming && !answer && (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {!answer && !streaming && (
        <EmptyState
          title="No verdict yet"
          body="Ask, and ORCA returns a go / caution / no-go with the hazard that drove it. A verdict is never given without the numbers behind it."
        />
      )}

      {answer && (
        <div aria-live="polite" className="flex flex-col gap-4">
          {answer.risk_assessment && (
            <VerdictBadge verdict={answer.risk_assessment.go_no_go} summary={answer.risk_assessment.reason} confidenceTier={answer.confidence_tier}>
              <div className="mt-3">
                <ConfidenceMeter tier={answer.confidence_tier} />
              </div>
            </VerdictBadge>
          )}

          <Panel title="What ORCA is telling you">
            <FormattedResponse text={answer.final_vernacular_response} />
          </Panel>

          <Panel title="Weather" action={weatherCite && <SourceChip dataset={weatherCite.dataset} acquisitionTimestamp={weatherCite.acquisition_timestamp} />}>
            <ReadoutGrid cols={4}>
              <Readout label="Wave height" value={answer.weather_summary.wave_height_m ?? "—"} unit="m" />
              <Readout
                label="Wind speed"
                value={
                  answer.weather_summary.wind_speed_ms != null
                    ? (answer.weather_summary.wind_speed_ms * 3.6).toFixed(1)
                    : "—"
                }
                unit="km/h"
              />
              <Readout
                label="Lightning"
                value={
                  <Badge tone={answer.weather_summary.lightning_active ? "no-go" : "go"}>
                    {answer.weather_summary.lightning_active ? "Active" : "Clear"}
                  </Badge>
                }
              />
              <Readout
                label="IMD nowcast"
                value={
                  answer.weather_summary.imd_nowcast?.alert_count
                    ? `${answer.weather_summary.imd_nowcast.alert_count} district${answer.weather_summary.imd_nowcast.alert_count === 1 ? "" : "s"}`
                    : "None in range"
                }
                hint={
                  answer.weather_summary.imd_nowcast?.expired
                    ? "snapshot window closed"
                    : answer.weather_summary.imd_nowcast?.alert_count
                      ? `within ${answer.weather_summary.imd_nowcast.radius_km} km`
                      : undefined
                }
              />
              <Readout
                label="Cyclone alert"
                value={
                  <Badge tone={answer.weather_summary.cyclone_alert ? "no-go" : "go"}>
                    {answer.weather_summary.cyclone_alert ?? "None"}
                  </Badge>
                }
              />
            </ReadoutGrid>

            {/* Two sources disagreeing is information, not a conflict to
                resolve silently. Only shown when they genuinely disagree —
                an expired IMD snapshot is "single_source", and a banner for
                that would be noise on every offline demo. */}
            {answer.weather_summary.lightning_source_agreement === "disagree" && (
              <p className="mt-3 flex items-baseline gap-2 border-t border-hairline pt-3 text-xs">
                <Badge tone="caution">sources disagree</Badge>
                <span className="text-ink-dim">
                  IMD&apos;s district nowcast and the Open-Meteo CAPE proxy do not agree on
                  convective risk here. The verdict above is computed from the Open-Meteo
                  proxy alone; IMD is shown beside it, not folded into it.
                </span>
              </p>
            )}
          </Panel>

          <Panel title="Boundaries and protected areas" action={geoCite && <SourceChip dataset={geoCite.dataset} acquisitionTimestamp={geoCite.acquisition_timestamp} />}>
            <ReadoutGrid cols={2}>
              <Readout
                label="Distance to maritime boundary"
                value={answer.hazard_breakdown.imbl_distance_nm?.toFixed(2) ?? "—"}
                unit="nm"
                hint={answer.hazard_breakdown.imbl_alert_level ?? undefined}
              />
              <Readout
                label="Marine protected area"
                value={
                  <Badge tone={answer.hazard_breakdown.mpa_violation ? "no-go" : "go"}>
                    {answer.hazard_breakdown.mpa_violation ? "Inside — violation" : "Clear"}
                  </Badge>
                }
              />
            </ReadoutGrid>
            {/* A caveat this specific belongs next to the number it qualifies,
                not in a footnote nobody reads. */}
            <p className="mt-3 flex gap-2 border-t border-hairline pt-3 text-xs text-ink-dim">
              <AlertTriangle className="size-3.5 shrink-0 text-caution" aria-hidden="true" />
              <span>
                Boundary distance uses the Sri Lanka EEZ line as a practical proxy — this build has no
                separately digitised IMBL treaty geometry. Verify independently before treating it as
                authoritative.
              </span>
            </p>
          </Panel>
        </div>
      )}
    </PageBody>
  );
}
