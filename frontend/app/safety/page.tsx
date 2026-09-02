"use client";

import { useRef, useState } from "react";
import { Badge, confidenceTone, verdictTone } from "../components/Badge";
import { Card } from "../components/Card";
import { Field } from "../components/Field";
import { SourceChip } from "../components/SourceChip";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type VesselClass = "small_fishing" | "mechanized_trawler" | "cargo_vessel";
const VESSEL_LABELS: Record<VesselClass, string> = {
  small_fishing: "Small Fishing Boat",
  mechanized_trawler: "Mechanized Trawler",
  cargo_vessel: "Cargo Vessel",
};

type AgentSpan = { agent_name: string; status: string };
type Citation = { agent_name: string; dataset: string; acquisition_timestamp: string; freshness_minutes: number };
type SafetyResponse = {
  final_vernacular_response: string;
  confidence_tier: "HIGH" | "MEDIUM" | "LOW_DATA";
  risk_assessment: { status: string; go_no_go: "GO" | "CAUTION" | "NO_GO"; reason: string } | null;
  citations: Citation[];
  distress_flag: boolean;
  weather_summary: {
    wave_height_m: number | null;
    wind_speed_ms: number | null;
    lightning_active: boolean;
    cyclone_alert: string | null;
  };
  hazard_breakdown: {
    imbl_distance_nm: number | null;
    imbl_alert_level: string | null;
    mpa_violation: boolean;
    mpa_alert_level: string | null;
  };
};

// Vessel-class threshold deltas (Architecture §3.1 Agent 7) — shown here so
// the selector explains itself rather than the number just silently
// changing the verdict with no visible reason.
const VESSEL_DELTAS: Record<VesselClass, string> = {
  small_fishing: "Most conservative — base thresholds",
  mechanized_trawler: "+9.3 km/h wind, +0.5 m wave tolerance",
  cargo_vessel: "+27.8 km/h wind, +1.5 m wave tolerance",
};

// Safety (§4.2 `/safety`): verdict, vessel-class selector, weather gauges,
// active hazard breakdown (plan §4 S2). Every number carries a source —
// exit criterion 4 — via SourceChip, not just the verdict badge.
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

    const url = `${API_BASE}/query?q=${encodeURIComponent(query)}&vessel_class=${vesselClass}`;
    const es = new EventSource(url);
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

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold mb-4">Safety</h1>

      <form onSubmit={check} className="mb-6 flex flex-col gap-3">
        <Field label="Question">
          {(id) => (
            <input
              id={id}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full rounded border border-black/20 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2"
            />
          )}
        </Field>

        <Field label="Vessel class" hint={VESSEL_DELTAS[vesselClass]}>
          {(id) => (
            <select
              id={id}
              value={vesselClass}
              onChange={(e) => setVesselClass(e.target.value as VesselClass)}
              className="w-full rounded border border-black/20 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2"
            >
              {(Object.keys(VESSEL_LABELS) as VesselClass[]).map((v) => (
                <option key={v} value={v}>
                  {VESSEL_LABELS[v]}
                </option>
              ))}
            </select>
          )}
        </Field>

        <button
          type="submit"
          disabled={streaming}
          className="self-start rounded bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          {streaming ? "Checking…" : "Check safety"}
        </button>
      </form>

      {spans.length > 0 && (
        <ul aria-live="polite" className="mb-4 flex flex-wrap gap-2">
          {spans.map((s, i) => (
            <li key={i} className="rounded-full bg-black/5 px-3 py-1 text-xs">
              {s.agent_name}
            </li>
          ))}
        </ul>
      )}

      {answer && (
        <div aria-live="polite" className="flex flex-col gap-4">
          {/* Verdict — leads with a text token, colour only reinforces it
              (parent plan §4.11 — severity is never carried by colour alone). */}
          <Card>
            <div className="flex items-center gap-2 mb-2">
              {answer.risk_assessment && (
                <Badge tone={verdictTone(answer.risk_assessment.go_no_go)}>{answer.risk_assessment.go_no_go}</Badge>
              )}
              <Badge tone={confidenceTone(answer.confidence_tier)}>{answer.confidence_tier.replace("_", "-")}</Badge>
            </div>
            <p className="text-sm">{answer.risk_assessment?.reason ?? answer.final_vernacular_response}</p>
            <p className="mt-2 text-sm text-black/70">{answer.final_vernacular_response}</p>
          </Card>

          <Card title="Weather">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-black/50">Wave height</dt>
              <dd>{answer.weather_summary.wave_height_m != null ? `${answer.weather_summary.wave_height_m} m` : "—"}</dd>
              <dt className="text-black/50">Wind speed</dt>
              <dd>
                {answer.weather_summary.wind_speed_ms != null
                  ? `${(answer.weather_summary.wind_speed_ms * 3.6).toFixed(1)} km/h`
                  : "—"}
              </dd>
              <dt className="text-black/50">Lightning</dt>
              <dd>
                <Badge tone={answer.weather_summary.lightning_active ? "danger" : "go"}>
                  {answer.weather_summary.lightning_active ? "ACTIVE" : "CLEAR"}
                </Badge>
              </dd>
              <dt className="text-black/50">Cyclone alert</dt>
              <dd>
                <Badge tone={answer.weather_summary.cyclone_alert ? "danger" : "go"}>
                  {answer.weather_summary.cyclone_alert ?? "NONE"}
                </Badge>
              </dd>
            </dl>
            {answer.citations
              .filter((c) => c.agent_name === "weather_intelligence")
              .map((c, i) => (
                <div key={i} className="mt-3">
                  <SourceChip dataset={c.dataset} acquisitionTimestamp={c.acquisition_timestamp} />
                </div>
              ))}
          </Card>

          <Card title="Active hazard breakdown">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-black/50">IMBL distance</dt>
              <dd>
                {answer.hazard_breakdown.imbl_distance_nm != null
                  ? `${answer.hazard_breakdown.imbl_distance_nm.toFixed(2)} nm (${answer.hazard_breakdown.imbl_alert_level})`
                  : "—"}
              </dd>
              <dt className="text-black/50">Marine Protected Area</dt>
              <dd>
                <Badge tone={answer.hazard_breakdown.mpa_violation ? "danger" : "go"}>
                  {answer.hazard_breakdown.mpa_violation ? "INSIDE — VIOLATION" : "CLEAR"}
                </Badge>
              </dd>
            </dl>
            <p className="mt-2 text-xs text-black/50">
              IMBL distance uses the Sri Lanka EEZ boundary as a practical proxy — there is no separately
              digitized IMBL treaty-line geometry in this build. Verify against an independent source before
              treating it as authoritative.
            </p>
            {answer.citations
              .filter((c) => c.agent_name === "geospatial")
              .map((c, i) => (
                <div key={i} className="mt-3">
                  <SourceChip dataset={c.dataset} acquisitionTimestamp={c.acquisition_timestamp} />
                </div>
              ))}
          </Card>
        </div>
      )}
    </div>
  );
}
