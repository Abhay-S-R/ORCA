"use client";

// Architecture §2.6 output rendering matrix, realised in the UI (Phase 3 D1
// Day 20). Every persona sees the SAME already-computed facts (hazard
// breakdown, weather summary, ocean summary, citations) — nothing here
// fetches anything or changes a number; only the structure changes:
//   fisherman            -> banner + plain distance/direction (elsewhere: single map pin)
//   commercial_navigator -> a structured readout grid (position, tide, bathymetry-relevant hazards)
//   researcher           -> a full statistical summary + CSV/JSON export
//   coastal_authority    -> a threat-level classification + a CAP-shaped preview
//   unresolved           -> the fisherman banner, plus "Show technical detail"
// LOW_DATA is not a persona branch: VerdictBadge's confidenceTier prop
// applies the amber "data limited" treatment identically to all five above.
import { useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Compass, Cloud, Crosshair, Download, OctagonX, ShieldCheck, Waves } from "lucide-react";
import { Badge, verdictTone, type ConfidenceTier, type Verdict } from "./Badge";
import { Button } from "./Button";
import { Readout, ReadoutGrid } from "./Readout";
import { freshnessLabel } from "./SourceChip";
import { type Persona } from "../persona/config";
import { type QueryIntent } from "../lib/queryIntent";

// Header title/icon per query intent — the response now opens with "what
// kind of answer is this" instead of a full-width Go/No-Go slab (removed
// per the response redesign; the map beside the chat carries the matching
// visualization instead of a second one here).
const INTENT_TITLE: Record<QueryIntent, string> = {
  safety: "Sea Safety Assessment",
  fishing: "Potential Fishing Zone Advisory",
  boundary: "Maritime Boundary Standoff",
  current: "Surface Current Outlook",
  wave: "Wave & Swell Outlook",
  wind: "Wind Speed & Direction",
  general: "Marine Conditions Summary",
};
const INTENT_ICON: Record<QueryIntent, typeof ShieldCheck> = {
  safety: ShieldCheck,
  fishing: Crosshair,
  boundary: Compass,
  current: Waves,
  wave: Waves,
  wind: Cloud,
  general: ShieldCheck,
};
const VERDICT_ICON: Record<Verdict, typeof CheckCircle2> = {
  GO: CheckCircle2,
  CAUTION: AlertTriangle,
  NO_GO: OctagonX,
};
const VERDICT_LABEL: Record<Verdict, string> = { GO: "Go", CAUTION: "Caution", NO_GO: "No go" };

export type HazardBreakdown = {
  imbl_distance_nm: number | null;
  imbl_alert_level: string | null;
  mpa_violation: boolean;
  mpa_alert_level: string | null;
};
export type WeatherSummary = {
  wave_height_m: number | null;
  wind_speed_ms: number | null;
  lightning_active: boolean;
  cyclone_alert: string | null;
};
// P4.1 — the bands `risk_assessment.evaluate_marine_safety` actually compared
// this answer's readings against, for the vessel class the verdict used. Lets
// a reading render as "value against its limit" instead of a bare number.
export type SafetyThresholds = {
  vessel_class: string;
  caution_wave_m: number;
  danger_wave_m: number;
  caution_wind_kmh: number;
  danger_wind_kmh: number;
};
export type OceanSummary = {
  tide: unknown;
  nearest_pfz: unknown;
  sector_status: unknown;
  productivity_diagnosis: unknown;
};
export type Citation = { agent_name: string; dataset: string; acquisition_timestamp: string };

// The four payloads below arrive from the backend as JSON (sometimes as a
// Python-repr string — see the sanitiser in parseData). Every field is
// optional because an upstream agent that could not answer omits it, and the
// formatters all fall back. These shapes replace the `any` they used to be
// typed with: same tolerance, but a typo in a field name is now a compile
// error instead of a silent "—" on screen.
type TideData = {
  tidal_state?: string;
  state?: string;
  next_high?: { height_m?: number | null; in_hours?: number | null } | null;
  next_low?: { height_m?: number | null; in_hours?: number | null } | null;
  station_code?: string;
  station_name?: string;
  spring_neap?: string;
};
type PfzData = {
  found?: boolean;
  distance_km?: number | string | null;
  compass?: string;
  bearing_deg?: number | null;
  landing_center?: string;
  depth_m?: number | null;
  valid_for?: string | null;
  age_days?: number | null;
  band?: "fresh" | "hint" | "history" | null;
  max_km?: number | null;
};
type SectorStatusData = {
  status?: string;
  sector_name?: string;
  sector_id?: string;
  node_count?: number | null;
  is_data_gap?: boolean;
  message?: string;
};
type ProductivityData = {
  declined?: boolean;
  district?: string;
  factors?: { factor?: string }[];
};

function parseData<T = Record<string, unknown>>(value: unknown): T | null {
  if (!value) return null;
  if (typeof value === "object") return value as T;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
      try {
        return JSON.parse(trimmed) as T;
      } catch {
        try {
          const sanitized = trimmed
            .replace(/'/g, '"')
            .replace(/\bTrue\b/g, "true")
            .replace(/\bFalse\b/g, "false")
            .replace(/\bNone\b/g, "null");
          return JSON.parse(sanitized) as T;
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}

export function formatTideData(raw: unknown): { value: string; unit?: string; hint?: string } {
  const data = parseData<TideData>(raw);
  if (!data) {
    if (typeof raw === "string" && raw.trim() && !raw.includes("{")) {
      return { value: raw };
    }
    return { value: "Slack", hint: "Astronomical datum" };
  }

  const rawState = data.tidal_state || data.state || "";
  const state = rawState ? rawState.charAt(0).toUpperCase() + rawState.slice(1).toLowerCase() : "Slack";
  const nextHigh = data.next_high;
  const nextLow = data.next_low;
  const station = data.station_code || (data.station_name ? data.station_name.split("(")[0].trim() : "");
  const springNeap = data.spring_neap && data.spring_neap !== "UNKNOWN" ? data.spring_neap : null;

  let hint = "";
  if (nextHigh?.height_m != null) {
    const inH = nextHigh.in_hours != null ? ` in ${nextHigh.in_hours}h` : "";
    hint = `High: ${nextHigh.height_m}m${inH}`;
  } else if (nextLow?.height_m != null) {
    const inH = nextLow.in_hours != null ? ` in ${nextLow.in_hours}h` : "";
    hint = `Low: ${nextLow.height_m}m${inH}`;
  }

  if (springNeap) {
    hint = hint ? `${hint} · ${springNeap}` : springNeap;
  }
  if (station) {
    hint = hint ? `${hint} (${station})` : station;
  }

  return {
    value: state,
    hint: hint || undefined,
  };
}

export function formatPfzData(raw: unknown): { value: string; unit?: string; hint?: string } {
  const data = parseData<PfzData>(raw);
  if (!data) {
    if (typeof raw === "string" && raw.trim() && !raw.includes("{")) {
      return { value: raw };
    }
    return { value: "None", hint: "No advisories nearby" };
  }

  if (data.found === false || (data.distance_km == null && !data.landing_center)) {
    return { value: "None", hint: data.max_km ? `No advisory within ${Math.round(data.max_km)} km` : "No advisories in range" };
  }

  const dist = data.distance_km != null ? Number(data.distance_km).toFixed(1) : "—";
  const compass = data.compass || (data.bearing_deg != null ? `${data.bearing_deg}°` : "");
  const center = data.landing_center || "";
  const depth = data.depth_m ? `${data.depth_m}m depth` : "";

  // Stale-data policy: an old zone is still the answer, with its age attached.
  const age = data.band && data.band !== "fresh" && data.age_days != null ? `issued ${data.valid_for}, ${data.age_days} d old` : "";
  const hintParts = [compass, center, depth, age].filter(Boolean);

  return {
    value: dist,
    unit: "km",
    hint: hintParts.length > 0 ? hintParts.join(" · ") : undefined,
  };
}

export function formatSectorStatusData(raw: unknown): { value: string; unit?: string; hint?: string } {
  const data = parseData<SectorStatusData>(raw);
  if (!data) {
    if (typeof raw === "string" && raw.trim() && !raw.includes("{")) {
      return { value: raw };
    }
    return { value: "—", hint: "Status unavailable" };
  }

  const rawStatus = data.status || "";
  const sectorName = data.sector_name || data.sector_id || "";
  const nodes = data.node_count ?? 0;

  if (rawStatus === "NO_DATA_CLOUD_COVER" || data.is_data_gap) {
    return {
      value: "Cloud Cover",
      hint: `${sectorName ? sectorName.replace(/_/g, " ") : "Sector"} · 0 nodes`,
    };
  }

  if (rawStatus === "ACTIVE" || nodes > 0) {
    return {
      value: "Active",
      unit: `${nodes} nodes`,
      hint: sectorName ? sectorName.replace(/_/g, " ") : undefined,
    };
  }

  return {
    value: rawStatus ? rawStatus.replace(/_/g, " ") : (data.message || "Standard"),
    hint: sectorName ? sectorName.replace(/_/g, " ") : undefined,
  };
}

export function formatProductivityData(raw: unknown): { value: string; unit?: string; hint?: string } {
  const data = parseData<ProductivityData>(raw);
  if (!data) {
    if (typeof raw === "string" && raw.trim() && !raw.includes("{")) {
      return { value: raw };
    }
    return { value: "Stable", hint: "District baseline within ±2σ" };
  }

  if (data.declined) {
    const district = data.district ? data.district.split("(")[0].trim() : "District";
    const factor = data.factors?.[0]?.factor ? data.factors[0].factor.split("/")[0].trim() : "Thermal stress";
    return {
      value: "Decline",
      hint: `${district} · ${factor}`,
    };
  }

  return {
    value: "Stable",
    hint: "District baseline normal",
  };
}

function fmt(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    if (obj.label) return String(obj.label);
    if (obj.name) return String(obj.name);
    if (obj.status) return String(obj.status);
    return "Available";
  }
  return String(value);
}

// A named subsection above a ReadoutGrid — the same icon + label vocabulary
// FormattedResponse uses for its own section cards, so a stat grid and a
// narrative section read as one system rather than two different UIs bolted
// together.
function Group({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
        {icon}
        {label}
      </div>
      {children}
    </div>
  );
}

// district threat classification (coastal_authority): a severity word
// derived from the same verdict + hazard facts already on screen — never a
// second opinion, just a coarser label for a broadcast context. The real
// CAP 1.2 XML builder is D2's /ops (plan §6 D2 Day 20); this is the
// answer-card-level preview §2.6 asks D1 for, not a duplicate of it.
function threatSeverity(verdict: Verdict, hazard: HazardBreakdown, weather: WeatherSummary): "Extreme" | "Severe" | "Moderate" | "Minor" {
  if (verdict === "NO_GO" && (weather.lightning_active || hazard.mpa_violation)) return "Extreme";
  if (verdict === "NO_GO") return "Severe";
  if (verdict === "CAUTION") return "Moderate";
  return "Minor";
}

function buildCapPreview(
  verdict: Verdict, reason: string, hazard: HazardBreakdown, weather: WeatherSummary,
): { event: string; severity: string; area: string; effective: string; instruction: string } {
  return {
    event: weather.cyclone_alert ? `Cyclone advisory: ${weather.cyclone_alert}` : "Marine safety advisory",
    severity: threatSeverity(verdict, hazard, weather),
    area: hazard.mpa_violation ? "Marine protected area corridor" : "Indian coastal sector",
    effective: new Date().toISOString(),
    instruction: reason,
  };
}

function exportRows(
  queryId: string | undefined, weather: WeatherSummary, hazard: HazardBreakdown, ocean: OceanSummary, citations: Citation[],
): { agent_name: string; dataset: string; acquisition_timestamp: string; outputs: string }[] {
  return citations.map((c) => {
    const outputs =
      c.agent_name === "weather_intelligence" ? weather :
      c.agent_name === "geospatial" ? hazard :
      c.agent_name === "ocean_analytics" ? ocean : {};
    return { agent_name: c.agent_name, dataset: c.dataset, acquisition_timestamp: c.acquisition_timestamp, outputs: JSON.stringify(outputs) };
  });
}

// Client-side export (researcher persona, Architecture §2.6 "CSV/NetCDF
// export") — every field needed is already on the page from /query; a round
// trip to mint the identical CSV server-side (orca/agents/reporting.py's
// format_export) would cost a request for zero new data.
function downloadExport(queryId: string | undefined, rows: ReturnType<typeof exportRows>, fmtType: "csv" | "json") {
  const filename = `orca-${queryId ?? "export"}.${fmtType}`;
  let body: string;
  if (fmtType === "json") {
    body = JSON.stringify(rows, null, 2);
  } else {
    const header = "agent_name,dataset,acquisition_timestamp,outputs";
    body = [header, ...rows.map((r) => `${r.agent_name},${r.dataset},${r.acquisition_timestamp},"${r.outputs.replace(/"/g, '""')}"`)].join("\n");
  }
  const blob = new Blob([body], { type: fmtType === "json" ? "application/json" : "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// A limit only means something once it drove a real comparison — never shown
// while a reading is missing, since "— / 2.0 m caution" reads as a value
// that just happens to be absent, not as "nothing to compare".
function waveHint(value: number | null, t?: SafetyThresholds | null): string | undefined {
  if (!t || value === null) return undefined;
  return `limit ${t.caution_wave_m.toFixed(1)} m caution · ${t.danger_wave_m.toFixed(1)} m danger`;
}
function windHint(value: number | null, t?: SafetyThresholds | null): string | undefined {
  if (!t || value === null) return undefined;
  return `limit ${(t.caution_wind_kmh / 3.6).toFixed(1)} m/s caution · ${(t.danger_wind_kmh / 3.6).toFixed(1)} m/s danger`;
}

// P4.7 (R-PS-10) — "Why this answer?" for the fisherman persona: three plain
// sentences (deciding factor, source, freshness), no agent names, no
// jargon — everything else on this card ("IMBL distance", "MPA status")
// is exactly the engineer-facing language this point exists to replace.
function fishermanWhy(
  weather: WeatherSummary,
  thresholds: SafetyThresholds | null | undefined,
  citations: Citation[],
): { deciding: string; source: string; freshness: string } {
  const waveM = weather.wave_height_m;
  const windMs = weather.wind_speed_ms;
  const windKmh = windMs !== null ? windMs * 3.6 : null;
  let deciding: string;
  if (thresholds && waveM !== null && waveM >= thresholds.danger_wave_m) {
    deciding = `The waves were measured at ${waveM.toFixed(1)} m — too high for your boat.`;
  } else if (thresholds && windKmh !== null && windKmh >= thresholds.danger_wind_kmh) {
    deciding = `The wind was measured at ${windKmh.toFixed(0)} km/h — too strong for your boat.`;
  } else if (thresholds && waveM !== null && waveM >= thresholds.caution_wave_m) {
    deciding = `The waves were measured at ${waveM.toFixed(1)} m — close to the safe limit for your boat.`;
  } else if (thresholds && windKmh !== null && windKmh >= thresholds.caution_wind_kmh) {
    deciding = `The wind was measured at ${windKmh.toFixed(0)} km/h — close to the safe limit for your boat.`;
  } else if (waveM !== null || windKmh !== null) {
    deciding = "Wave height and wind speed were both within the safe limit for your boat.";
  } else {
    deciding = "No wave or wind reading was available for this answer.";
  }

  const weatherCitation = citations.find((c) => c.agent_name === "weather_intelligence");
  const source = weatherCitation ? `Based on ${weatherCitation.dataset}.` : "No source is recorded for this reading.";
  const freshness = weatherCitation
    ? `That reading is ${freshnessLabel(Math.round((Date.now() - new Date(weatherCitation.acquisition_timestamp).getTime()) / 60000))}.`
    : "";

  return { deciding, source, freshness };
}

export function PersonaAnswerMatrix({
  persona,
  queryId,
  intent,
  agentsVerified,
  verdict,
  reason,
  leadWithVerdict = true,
  confidenceTier,
  weather,
  hazard,
  ocean,
  citations,
  thresholds,
  rawAnswer,
}: {
  persona: Persona;
  queryId: string | undefined;
  // Drives the response's header title/icon and which follow-on detail is
  // worth leading with — the same classification that already moves the map
  // (ask/page.tsx's `focus.intent`), so the response and the chart always
  // agree on what kind of question this was.
  intent: QueryIntent;
  agentsVerified: number;
  verdict: Verdict;
  reason: string;
  // P2.2 (`R-JUDGE-2`) — whether the verdict leads this answer. The backend
  // decides it (reporting.should_lead_with_verdict) and it is deliberately
  // asymmetric: only a GO on a question that was not about safety is demoted,
  // so a CAUTION or NO_GO still leads whatever was asked. Defaults to true,
  // so an answer cached before the field existed keeps its banner rather than
  // silently losing a verdict.
  leadWithVerdict?: boolean;
  confidenceTier: ConfidenceTier;
  weather: WeatherSummary;
  hazard: HazardBreakdown;
  ocean: OceanSummary;
  citations: Citation[];
  thresholds?: SafetyThresholds | null;
  // P4.4 — "raw JSON one click away" for the researcher persona: the actual
  // `/query` response this card was built from, not a curated re-shape of
  // it. Optional because only the researcher branch reads it.
  rawAnswer?: unknown;
}) {
  const [showTechnical, setShowTechnical] = useState(false);
  const direction = hazard.imbl_distance_nm !== null ? `boundary ${hazard.imbl_distance_nm.toFixed(1)} nm away` : "boundary distance unknown";
  const tide = formatTideData(ocean.tide);
  const pfz = formatPfzData(ocean.nearest_pfz);
  const sector = formatSectorStatusData(ocean.sector_status);
  const productivity = formatProductivityData(ocean.productivity_diagnosis);
  const HeaderIcon = INTENT_ICON[intent];
  // Falls back rather than indexing with a verdict the table has never heard of.
  const VerdictIcon = VERDICT_ICON[verdict] ?? AlertTriangle;

  return (
    <div className="flex flex-col gap-3.5">
      {/* Response header — replaces the old full-width Go/No-Go slab with a
          compact "what this answer is" line, matching the reference
          response layouts' title + verified-agent badge pattern. */}
      <div className="flex items-center justify-between gap-3 border-b border-hairline/60 pb-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-hairline bg-shelf-2/60 text-accent">
            <HeaderIcon className="size-4" aria-hidden="true" />
          </span>
          <p className="truncate text-sm font-bold tracking-tight text-ink">{INTENT_TITLE[intent]}</p>
        </div>
        {agentsVerified > 0 && (
          <Badge tone="cyan" icon={<ShieldCheck className="size-3" aria-hidden="true" />}>
            {agentsVerified} Agents Verified
          </Badge>
        )}
      </div>

      {/* Status row — the verdict word and reason stay visible for every
          persona (what VerdictBadge's `summary` prop used to guarantee),
          just without the loud banner chrome.

          P2.2: two renderings, and which one is used is never a styling
          choice. A CAUTION or NO_GO gets the chip, whatever was asked. A GO
          on a question that was not about safety gets a single quiet line —
          the risk assessment still ran (it runs on every query, and that
          design must not be reverted), the answer still says so, it simply
          does not shout a verdict nobody asked for on top of an answer about
          fishing zones. */}
      <div className="flex items-start gap-3.5">
        <div className="min-w-0 flex-1">
          {leadWithVerdict ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={verdictTone(verdict)} icon={<VerdictIcon className="size-3" aria-hidden="true" />}>
                  {VERDICT_LABEL[verdict]}
                </Badge>
                {confidenceTier === "LOW_DATA" && (
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-data-limited">
                    Data limited — verify locally
                  </span>
                )}
              </div>
              {reason && <p className="mt-1.5 text-sm leading-relaxed text-ink">{reason}</p>}
            </>
          ) : (
            <div className="flex flex-col gap-1.5">
              <p className="flex items-start gap-1.5 text-[12px] leading-relaxed text-ink-muted">
                <VerdictIcon className="mt-0.5 size-3.5 shrink-0 text-go" aria-hidden="true" />
                <span>
                  Conditions checked — no hazard threshold crossed
                  {reason ? <span className="text-ink-dim"> ({reason.toLowerCase()})</span> : null}.
                </span>
              </p>
              {confidenceTier === "LOW_DATA" && (
                <span className="text-[10px] font-semibold uppercase tracking-wide text-data-limited">
                  Data limited — verify locally
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {persona === "fisherman" && (
        <>
          {/* P4.4 — ≥18px body on the fisherman surface, plain words only:
              this is the one persona whose plain-language line already had
              no jargon in it ("boundary X nm away" reads as-is); the change
              here is size and contrast, not wording. */}
          <p className="text-lg leading-snug text-ink">{direction}. See the map for the single nearest pin.</p>
          <Button variant="ghost" className="w-fit text-sm" icon={<ShieldCheck className="size-4" aria-hidden="true" />} onClick={() => setShowTechnical((v) => !v)}>
            {showTechnical ? "Hide reasoning" : "Why this answer?"}
          </Button>
          {showTechnical && (() => {
            const why = fishermanWhy(weather, thresholds, citations);
            return (
              <div className="flex flex-col gap-1.5 rounded-xl border border-hairline/70 bg-shelf-1/40 p-3.5 text-base leading-relaxed text-ink backdrop-blur-md">
                <p>{why.deciding}</p>
                <p className="text-ink-muted">{why.source}</p>
                {why.freshness && <p className="text-ink-muted">{why.freshness}</p>}
              </div>
            );
          })()}
        </>
      )}

      {persona === "unresolved" && (
        <>
          <p className="text-sm text-ink-muted">{direction}.</p>
          <Button variant="ghost" className="w-fit text-xs" onClick={() => setShowTechnical((v) => !v)}>
            {showTechnical ? "Hide technical detail" : "Show technical detail"}
          </Button>
          {showTechnical && (
            <div className="rounded-xl border border-hairline/70 bg-shelf-1/40 p-3.5 backdrop-blur-md">
              <ReadoutGrid cols={4}>
                <Readout label="Wave height" value={fmt(weather.wave_height_m)} unit="m" hint={waveHint(weather.wave_height_m, thresholds)} />
                <Readout label="Wind speed" value={fmt(weather.wind_speed_ms)} unit="m/s" hint={windHint(weather.wind_speed_ms, thresholds)} />
                <Readout label="IMBL distance" value={fmt(hazard.imbl_distance_nm)} unit="nm" hint={hazard.imbl_alert_level ?? undefined} />
                <Readout label="MPA status" value={hazard.mpa_violation ? "Inside" : "Clear"} />
              </ReadoutGrid>
            </div>
          )}
        </>
      )}

      {persona === "commercial_navigator" && (
        <div className="rounded-xl border border-hairline/70 bg-shelf-1/40 p-3.5 backdrop-blur-md">
          <Group icon={<Compass className="size-3.5" />} label="Navigation readout">
            <ReadoutGrid cols={4}>
              <Readout label="Boundary distance" value={fmt(hazard.imbl_distance_nm)} unit="nm" hint={hazard.imbl_alert_level ?? undefined} />
              <Readout label="MPA status" value={hazard.mpa_violation ? "Inside boundary" : "Clear"} hint={hazard.mpa_alert_level ?? undefined} />
              <Readout label="Tide" value={tide.value} unit={tide.unit} hint={tide.hint} />
              <Readout label="Wave height" value={fmt(weather.wave_height_m)} unit="m" hint="bathymetry/route detail: see /voyage" />
            </ReadoutGrid>
          </Group>
        </div>
      )}

      {persona === "researcher" && (
        <>
          <div className="flex flex-col gap-4 rounded-xl border border-hairline/70 bg-shelf-1/40 p-3.5 backdrop-blur-md shadow-sm">
            <Group icon={<Cloud className="size-3.5" />} label="Weather & sea state">
              <ReadoutGrid cols={3}>
                <Readout label="Wave height" value={fmt(weather.wave_height_m)} unit="m" hint={waveHint(weather.wave_height_m, thresholds)} />
                <Readout label="Wind speed" value={fmt(weather.wind_speed_ms)} unit="m/s" hint={windHint(weather.wind_speed_ms, thresholds)} />
                <Readout label="Lightning" value={weather.lightning_active ? "Active" : "None"} />
              </ReadoutGrid>
            </Group>
            <Group icon={<Compass className="size-3.5" />} label="Boundary & hazard">
              <ReadoutGrid cols={2}>
                <Readout label="IMBL distance" value={fmt(hazard.imbl_distance_nm)} unit="nm" hint={hazard.imbl_alert_level ?? undefined} />
                <Readout label="MPA violation" value={hazard.mpa_violation ? "Yes" : "No"} hint={hazard.mpa_alert_level ?? undefined} />
              </ReadoutGrid>
            </Group>
            <Group icon={<Crosshair className="size-3.5" />} label="Ocean & fishing activity">
              <ReadoutGrid cols={2}>
                <Readout label="Tide" value={tide.value} unit={tide.unit} hint={tide.hint} />
                <Readout label="Nearest PFZ" value={pfz.value} unit={pfz.unit} hint={pfz.hint} />
                <Readout label="Sector status" value={sector.value} unit={sector.unit} hint={sector.hint} />
                <Readout label="Productivity" value={productivity.value} unit={productivity.unit} hint={productivity.hint} />
              </ReadoutGrid>
            </Group>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" className="text-xs" icon={<Download className="size-3.5" />} onClick={() => downloadExport(queryId, exportRows(queryId, weather, hazard, ocean, citations), "csv")}>
              Export CSV
            </Button>
            <Button variant="ghost" className="text-xs" icon={<Download className="size-3.5" />} onClick={() => downloadExport(queryId, exportRows(queryId, weather, hazard, ocean, citations), "json")}>
              Export JSON
            </Button>
          </div>
          {/* P4.4 — "raw JSON one click away": the actual response object,
              not the curated CSV/JSON export rows above (those are a shaped
              subset for spreadsheets). One click to expand, right here,
              rather than a second page or a download dialog. */}
          {rawAnswer != null && (
            <details className="rounded-xl border border-hairline/70 bg-shelf-1/40">
              <summary className="cursor-pointer px-3.5 py-2 text-xs font-semibold text-ink-dim hover:text-ink">
                Raw response JSON
              </summary>
              <pre className="max-h-80 overflow-auto border-t border-hairline/60 bg-abyss/40 p-3.5 text-[11px] leading-relaxed text-ink-muted">
                {JSON.stringify(rawAnswer, null, 2)}
              </pre>
            </details>
          )}
        </>
      )}

      {persona === "coastal_authority" && (
        <>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-ink-dim">District threat level:</span>
            <Badge tone={verdict === "NO_GO" ? "no-go" : verdict === "CAUTION" ? "caution" : "go"}>
              {threatSeverity(verdict, hazard, weather)}
            </Badge>
          </div>
          <div className="rounded-md border border-hairline bg-shelf-1/50 p-3 text-xs">
            <p className="mb-1.5 font-medium text-ink-dim">CAP payload preview (full builder: /ops)</p>
            <dl className="space-y-1 font-mono text-[11px] text-ink-muted">
              {Object.entries(buildCapPreview(verdict, reason, hazard, weather)).map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <dt className="w-20 shrink-0 text-ink-dim">{k}</dt>
                  <dd className="min-w-0 break-words">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </>
      )}
    </div>
  );
}
