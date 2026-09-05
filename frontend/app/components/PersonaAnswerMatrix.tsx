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
import { Compass, Cloud, Crosshair, Download } from "lucide-react";
import { Badge, type ConfidenceTier, type Verdict } from "./Badge";
import { Button } from "./Button";
import { Readout, ReadoutGrid } from "./Readout";
import { VerdictBadge } from "./VerdictBadge";
import { type Persona } from "../persona/config";

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
export type OceanSummary = {
  tide: unknown;
  nearest_pfz: unknown;
  sector_status: unknown;
  productivity_diagnosis: unknown;
};
export type Citation = { agent_name: string; dataset: string; acquisition_timestamp: string };

function parseData<T = Record<string, any>>(value: unknown): T | null {
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
  const data = parseData<any>(raw);
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
  const data = parseData<any>(raw);
  if (!data) {
    if (typeof raw === "string" && raw.trim() && !raw.includes("{")) {
      return { value: raw };
    }
    return { value: "None", hint: "No advisories nearby" };
  }

  if (data.found === false || (data.distance_km == null && !data.landing_center)) {
    return { value: "None", hint: "No advisories in range" };
  }

  const dist = data.distance_km != null ? Number(data.distance_km).toFixed(1) : "—";
  const compass = data.compass || (data.bearing_deg != null ? `${data.bearing_deg}°` : "");
  const center = data.landing_center || "";
  const depth = data.depth_m ? `${data.depth_m}m depth` : "";

  const hintParts = [compass, center, depth].filter(Boolean);

  return {
    value: dist,
    unit: "km",
    hint: hintParts.length > 0 ? hintParts.join(" · ") : undefined,
  };
}

export function formatSectorStatusData(raw: unknown): { value: string; unit?: string; hint?: string } {
  const data = parseData<any>(raw);
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
  const data = parseData<any>(raw);
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
    const obj = value as Record<string, any>;
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
    area: hazard.mpa_violation ? "Gulf of Mannar MPA corridor" : "Thoothukudi coastal sector",
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

export function PersonaAnswerMatrix({
  persona,
  queryId,
  verdict,
  reason,
  confidenceTier,
  weather,
  hazard,
  ocean,
  citations,
}: {
  persona: Persona;
  queryId: string | undefined;
  verdict: Verdict;
  reason: string;
  confidenceTier: ConfidenceTier;
  weather: WeatherSummary;
  hazard: HazardBreakdown;
  ocean: OceanSummary;
  citations: Citation[];
}) {
  const [showTechnical, setShowTechnical] = useState(false);
  const direction = hazard.imbl_distance_nm !== null ? `boundary ${hazard.imbl_distance_nm.toFixed(1)} nm away` : "boundary distance unknown";
  const tide = formatTideData(ocean.tide);
  const pfz = formatPfzData(ocean.nearest_pfz);
  const sector = formatSectorStatusData(ocean.sector_status);
  const productivity = formatProductivityData(ocean.productivity_diagnosis);

  return (
    <div className="flex flex-col gap-3">
      <VerdictBadge verdict={verdict} summary={reason} confidenceTier={confidenceTier} />

      {persona === "fisherman" && (
        <p className="text-sm text-ink-muted">{direction}. See the map for the single nearest pin.</p>
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
                <Readout label="Wave height" value={fmt(weather.wave_height_m)} unit="m" />
                <Readout label="Wind speed" value={fmt(weather.wind_speed_ms)} unit="m/s" />
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
                <Readout label="Wave height" value={fmt(weather.wave_height_m)} unit="m" />
                <Readout label="Wind speed" value={fmt(weather.wind_speed_ms)} unit="m/s" />
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
