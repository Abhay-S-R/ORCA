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
import { useState } from "react";
import { Download } from "lucide-react";
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

function fmt(value: unknown): string {
  if (value === null || value === undefined) return "—";
  // Full float precision (e.g. 4.305555555555556 m/s) is a display concern,
  // not extra precision — the underlying value is untouched, only rounded
  // for legibility, consistent with the toFixed(1) already used for
  // hazard.imbl_distance_nm below.
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
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
            <ReadoutGrid cols={4}>
              <Readout label="Wave height" value={fmt(weather.wave_height_m)} unit="m" />
              <Readout label="Wind speed" value={fmt(weather.wind_speed_ms)} unit="m/s" />
              <Readout label="IMBL distance" value={fmt(hazard.imbl_distance_nm)} unit="nm" hint={hazard.imbl_alert_level ?? undefined} />
              <Readout label="MPA status" value={hazard.mpa_violation ? "Inside" : "Clear"} />
            </ReadoutGrid>
          )}
        </>
      )}

      {persona === "commercial_navigator" && (
        <ReadoutGrid cols={4}>
          <Readout label="Boundary distance" value={fmt(hazard.imbl_distance_nm)} unit="nm" hint={hazard.imbl_alert_level ?? undefined} />
          <Readout label="MPA status" value={hazard.mpa_violation ? "Inside boundary" : "Clear"} hint={hazard.mpa_alert_level ?? undefined} />
          <Readout label="Tide" value={fmt(ocean.tide)} />
          <Readout label="Wave height" value={fmt(weather.wave_height_m)} unit="m" hint="bathymetry/route detail: see /voyage" />
        </ReadoutGrid>
      )}

      {persona === "researcher" && (
        <>
          <ReadoutGrid cols={3}>
            <Readout label="Wave height" value={fmt(weather.wave_height_m)} unit="m" />
            <Readout label="Wind speed" value={fmt(weather.wind_speed_ms)} unit="m/s" />
            <Readout label="Lightning" value={weather.lightning_active ? "Active" : "None"} />
            <Readout label="IMBL distance" value={fmt(hazard.imbl_distance_nm)} unit="nm" hint={hazard.imbl_alert_level ?? undefined} />
            <Readout label="MPA violation" value={hazard.mpa_violation ? "Yes" : "No"} hint={hazard.mpa_alert_level ?? undefined} />
            <Readout label="Tide" value={fmt(ocean.tide)} />
            <Readout label="Nearest PFZ" value={fmt(ocean.nearest_pfz)} />
            <Readout label="Sector status" value={fmt(ocean.sector_status)} />
            <Readout label="Productivity" value={fmt(ocean.productivity_diagnosis)} />
          </ReadoutGrid>
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
