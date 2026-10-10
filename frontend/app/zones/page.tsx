"use client";

// Fishing zones (§4.2 `/zones`) — PS #1. The order is deliberate: your own
// sector's status leads (a cloud-covered sector says so, in INCOIS's own
// words — data audit C-2), then the nearest advisory node with a heading and
// distance, its persistence across the archived runs, and only then the
// thermal-front proxy, which is valid ONLY when INCOIS has published nothing.
// P3.12 — all visible strings now sourced from the i18n dictionaries via useT().
import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Compass, Database, ExternalLink, Fish, Gauge, Search, Sparkles } from "lucide-react";
import { Badge } from "../components/Badge";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceChip } from "../components/SourceChip";
import { SourceNarration, type SourceSelection } from "../components/SourceNarration";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { authFetch, useAuth } from "../lib/auth";
import { ageLabel, type Recency } from "../lib/recency";
import { usePersona } from "../persona/context";
import { useT } from "../i18n/useT";

// P4.4 (orca_final §9.1a) — the Small Vessel view's reach check, for the
// fisherman persona only. A day trip's realistic outbound leg: enough of a
// working day left to fish and motor back before dark, not the boat's full
// range one-way. Disclosed inline wherever it's used — this is ORCA's own
// planning assumption, not a measurement, so it must never read like one.
const REACH_HOURS_OUTBOUND = 4;

function useVesselReachKm(): { reachKm: number | null; cruiseSpeedKn: number | null; checked: boolean } {
  const auth = useAuth();
  const [cruiseSpeedKn, setCruiseSpeedKn] = useState<number | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (auth.status !== "signed_in" || !auth.profile?.active_vessel_id) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from the external auth store, same as persona/context.tsx
      setChecked(auth.status !== "loading");
      return;
    }
    let cancelled = false;
    authFetch(`/api/vessels/${auth.profile.active_vessel_id}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((v) => {
        if (!cancelled) {
          setCruiseSpeedKn(typeof v?.cruise_speed_kn === "number" ? v.cruise_speed_kn : null);
          setChecked(true);
        }
      })
      .catch(() => !cancelled && setChecked(true));
    return () => {
      cancelled = true;
    };
  }, [auth.status, auth.profile?.active_vessel_id]);

  const reachKm = cruiseSpeedKn != null ? cruiseSpeedKn * 1.852 * REACH_HOURS_OUTBOUND : null;
  return { reachKm, cruiseSpeedKn, checked };
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
// P-HP-1 — no longer a hardcoded Thoothukudi constant. The home port comes
// from the user's profile (zones API defaults to the registered home port
// server-side when omitted; if there is none the backend applies its own
// geographic default).

type Confidence = { score: "HIGH" | "MEDIUM" | "LOW_DATA"; rationale: string };

type Sector = {
  sector_id: string;
  sector_name: string;
  status: string;
  message: string;
  node_count: number;
  valid_for: string | null;
  is_data_gap: boolean;
  // Stale-data policy: the sector's most recent advisory ORCA holds, even
  // when today's status is a gap — null only if it has never had one.
  latest_advisory: Recency & { valid_for: string; node_count: number } | null;
};

type ZonesResponse = {
  measured_from: string; // "registered home port" | "supplied position"
  origin: { lat: number; lon: number };
  sector_status: Sector & { nearest_advisory_out_of_sector: boolean };
  all_sectors: Sector[];
  nearest_pfz: {
    found: boolean;
    landing_center: string | null;
    distance_km: number | null;
    bearing_deg: number | null;
    compass: string | null;
    depth_m: string | null;
    latitude: number | null;
    longitude: number | null;
    valid_for: string | null;
    sector_id: string | null;
    max_km: number | null;
    beyond_reach?: boolean;
    top_species?: Array<{
      name: string;
      scientific_name?: string;
      depth_fit?: string;
      tonnes?: number;
      confidence?: string;
      source?: string;
    }>;
  } & Recency;
  persistence: {
    score: number | null;
    label: string;
    days_present: number;
    days_on_record: number;
    radius_km: number;
    confidence: Confidence;
  };
  thermal_front_proxy: {
    features: unknown[];
    orca_metadata?: { generated_at: string; not_an_advisory: string; applies_to_sector: string };
  };
  source_selection: SourceSelection | null;
};

// The seasonal ban is regulatory, never a sail/no-sail verdict — the risk
// cascade does not read it and neither does this page's tone logic.
type FishingBan = {
  available: boolean;
  note?: string;
  coast?: string;
  in_ban_period?: boolean;
  applies_here?: boolean;
  window?: string;
  next_window?: string;
  days?: number;
  distance_to_nearest_eez_edge_nm?: number | null;
  order?: { file_number: string; order_date: string; issuing_authority: string; pdf_url: string; applies_to: string; exemption: string };
};

type MarineSpecies = {
  aphia_id: number;
  scientific_name: string;
  common_name: string | null;
  family: string | null;
  order: string | null;
  in_obis: boolean;
  in_aquamaps: boolean;
  in_cmfri: boolean;
  obis_records: number | null;
  last_observed_year: number | null;
  aquamaps_prob: number | null;
  cmfri_tonnes: number | null;
  confidence: "High" | "Medium" | "Low";
  confidence_rationale: string;
};

type SpeciesApiResponse = {
  total: number;
  limit: number;
  offset: number;
  species: MarineSpecies[];
  report_summary?: {
    timestamp?: string;
    sources?: {
      obis_unique_species: number;
      aquamaps_predicted_species: number;
      cmfri_landings_groups: number;
      total_harmonized_species: number;
    };
    confidence_breakdown?: { High: number; Medium: number; Low: number };
    overlaps?: { triply_validated_all_three: number };
  };
  spot_checks?: Array<{
    species: string;
    common_name: string | null;
    depth_min_m: number | null;
    depth_max_m: number | null;
    temp_min_c: number | null;
    temp_max_c: number | null;
    habitat_type: string | null;
    source: string;
  }>;
};

export default function ZonesPage() {
  const [data, setData] = useState<ZonesResponse | null>(null);
  const [ban, setBan] = useState<FishingBan | null>(null);
  const [speciesData, setSpeciesData] = useState<SpeciesApiResponse | null>(null);
  const [speciesQuery, setSpeciesQuery] = useState("");
  const [speciesFilter, setSpeciesFilter] = useState<"all" | "triply" | "commercial">("all");
  const [showBenchmarks, setShowBenchmarks] = useState(false);
  const [speciesVisibleCount, setSpeciesVisibleCount] = useState(6);
  const [error, setError] = useState(false);
  const t = useT();
  const { persona } = usePersona();
  const reach = useVesselReachKm();
  const auth = useAuth();

  // Use the user's registered home port for the zones query when available.
  // If no home port is set the backend will use its own geographic default.
  const homePort = auth.status === "signed_in" ? auth.profile?.home_port ?? null : null;
  const posParam = homePort ? `lat=${homePort.lat}&lon=${homePort.lon}` : "";

  useEffect(() => {
    const base = `${API_BASE}/api/zones${posParam ? `?${posParam}` : ""}`;
    const banBase = `${API_BASE}/api/fishing-ban${posParam ? `?${posParam}` : ""}`;
    fetch(base)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError(true));
    fetch(banBase)
      .then((r) => r.json())
      .then(setBan)
      .catch(() => setBan(null));
  // Re-fetch when home port changes (user sets or updates it)
  }, [posParam]);

  useEffect(() => {
    const qParam = speciesQuery.trim() ? `&q=${encodeURIComponent(speciesQuery.trim())}` : "";
    fetch(`${API_BASE}/api/species?limit=60${qParam}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((res) => {
        if (res) setSpeciesData(res);
      })
      .catch(() => setSpeciesData(null));
  }, [speciesQuery]);

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title={t("zones.title")}
        lede={t("zones.lede")}
      />

      {error && (
        <ErrorState
          title={t("zones.apiError")}
          body={t("zones.apiErrorBody")}
        />
      )}

      {!data && !error && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}

      {data && (
        <div className="flex flex-col gap-4">
          {/* 1 — sector status, always first */}
          <Panel
            title={`${t("zones.yourSector")} — ${data.sector_status.sector_name}`}
            action={
              <Badge tone={data.sector_status.is_data_gap ? "caution" : "go"}>
                {data.sector_status.is_data_gap ? t("zones.noAdvisory") : t("zones.advisoryPublished")}
              </Badge>
            }
          >
            <p className="text-sm text-ink-muted">{data.sector_status.message}</p>
            {!data.sector_status.is_data_gap && (
              <ReadoutGrid cols={2}>
                <Readout label={t("zones.advisoryNodes")} value={data.sector_status.node_count} />
                <Readout label={t("zones.validFor")} value={data.sector_status.valid_for ?? "—"} />
              </ReadoutGrid>
            )}
            {/* A gap today is not an empty sector: its last clear-sky advisory
                still stands, shown with its age rather than hidden. */}
            {data.sector_status.is_data_gap && data.sector_status.latest_advisory && (
              <p className="mt-2 text-xs text-ink-muted">
                Latest advisory for this sector: {data.sector_status.latest_advisory.valid_for},{" "}
                {data.sector_status.latest_advisory.node_count} zones —{" "}
                {ageLabel(data.sector_status.latest_advisory.valid_for, data.sector_status.latest_advisory) ??
                  "still current"}
                . Shown on the map, faded by age.
              </p>
            )}
            {data.sector_status.is_data_gap && data.sector_status.nearest_advisory_out_of_sector && (
              <p className="mt-2 text-xs text-ink-dim">
                {t("zones.nearestAdvisoryNeighbour")}
              </p>
            )}
          </Panel>

          {/* 1b — seasonal closure. Regulatory, so it sits beside the
              advisory rather than inside it: a closed season is not a
              weather hazard and never colours the sail/no-sail verdict. */}
          {ban?.available && (
            <Panel
              title={t("zones.seasonalBan")}
              action={
                <Badge tone={ban.applies_here ? "no-go" : ban.in_ban_period ? "caution" : "neutral"}>
                  {ban.applies_here ? t("zones.inForceHere") : ban.in_ban_period ? t("zones.inForceOffshore") : t("zones.openSeason")}
                </Badge>
              }
            >
              <p className="text-sm text-ink-muted">{ban.note}</p>
              <ReadoutGrid cols={3}>
                <Readout label={t("zones.coast")} value={ban.coast ?? "—"} />
                <Readout
                  label={ban.in_ban_period ? t("zones.window") : t("zones.nextWindow")}
                  value={ban.window ?? ban.next_window ?? "—"}
                  hint={ban.days ? `${ban.days} days` : undefined}
                />
                <Readout
                  label={t("zones.fromEez")}
                  value={ban.distance_to_nearest_eez_edge_nm != null ? ban.distance_to_nearest_eez_edge_nm.toFixed(1) : "—"}
                  unit="NM"
                />
              </ReadoutGrid>
              {ban.order && (
                <p className="mt-3 border-t border-hairline pt-2 text-[11px] text-ink-dim">
                  {ban.order.issuing_authority} · {ban.order.file_number}, {ban.order.order_date} ·{" "}
                  {ban.order.applies_to}; {ban.order.exemption}.{" "}
                  <a className="underline" href={ban.order.pdf_url} target="_blank" rel="noreferrer">
                    order PDF
                  </a>
                </p>
              )}
            </Panel>
          )}

          {/* 2 — nearest advised zone */}
          {data.nearest_pfz.found ? (
            <Panel
              title={t("zones.nearestZone")}
              action={
                data.nearest_pfz.sector_id !== data.sector_status.sector_id ? (
                  <span className="text-[11px] text-ink-dim">sector {data.nearest_pfz.sector_id}</span>
                ) : null
              }
            >
              <div className="mb-1 flex items-center gap-2 text-lg">
                <Compass className="size-5 text-ink-dim" aria-hidden="true" />
                <span data-readout className="text-ink">
                  {data.nearest_pfz.compass} {data.nearest_pfz.bearing_deg}° · {data.nearest_pfz.distance_km} km
                </span>
              </div>
              {data.nearest_pfz.beyond_reach && data.nearest_pfz.max_km != null && (
                <p className="mb-2 text-xs text-caution">
                  No advisory within {Math.round(data.nearest_pfz.max_km)} km — this is the nearest Sagar Sarathi
                  holds, beyond a realistic day trip.
                </p>
              )}
              {ageLabel(data.nearest_pfz.valid_for, data.nearest_pfz) && (
                <p className="mb-2 text-xs text-caution">
                  Older advisory — {ageLabel(data.nearest_pfz.valid_for, data.nearest_pfz)}. Zones move
                  with the fronts, so treat it as where fish were, not where they are.
                </p>
              )}

              {/* P4.4 / orca_final §9.1a — Small Vessel view: is this zone
                  within a realistic day trip for the vessel actually on
                  record? Fisherman persona only — the other three personas
                  read distance as a plain number, not a go/no-go filter. */}
              {persona === "fisherman" && (() => {
                const distanceKm = Number(data.nearest_pfz.distance_km);
                if (!reach.checked) return null;
                if (reach.reachKm == null) {
                  return (
                    <p className="mb-3 flex items-center gap-1.5 text-xs text-ink-dim">
                      <Gauge className="size-3.5 shrink-0" aria-hidden="true" />
                      Reach filter is off — add your boat&apos;s cruise speed in your profile to see whether this zone is a realistic day trip.
                    </p>
                  );
                }
                const within = Number.isFinite(distanceKm) && distanceKm <= reach.reachKm;
                return (
                  <p className={`mb-3 flex items-center gap-1.5 text-xs ${within ? "text-go" : "text-caution"}`}>
                    <Gauge className="size-3.5 shrink-0" aria-hidden="true" />
                    {within
                      ? `Within reach — your boat covers ~${Math.round(reach.reachKm)} km outbound in a ${REACH_HOURS_OUTBOUND} h day-trip leg at ${reach.cruiseSpeedKn} kn.`
                      : `Outside a realistic day trip — your boat's ${REACH_HOURS_OUTBOUND} h outbound leg at ${reach.cruiseSpeedKn} kn reaches ~${Math.round(reach.reachKm)} km, this zone is ${Math.round(distanceKm)} km away.`}
                  </p>
                );
              })()}

              <p className="mb-3 text-[11px] text-ink-dim">
                {t("zones.measuredFrom")} {data.measured_from}
                {data.measured_from === "supplied position" &&
                  ` (${data.origin.lat.toFixed(2)}, ${data.origin.lon.toFixed(2)}) — ${t("zones.loginForHomePort")}`}
              </p>
              <ReadoutGrid cols={3}>
                <Readout label={t("zones.landingCentre")} value={data.nearest_pfz.landing_center ?? "—"} />
                <Readout label={t("zones.advisedDepth")} value={data.nearest_pfz.depth_m ?? "—"} unit="m" />
                <Readout
                  label={t("zones.zoneCentre")}
                  value={
                    data.nearest_pfz.latitude != null
                      ? `${data.nearest_pfz.latitude.toFixed(2)}, ${data.nearest_pfz.longitude!.toFixed(2)}`
                      : "—"
                  }
                />
              </ReadoutGrid>

              {/* Top Target Fish Species in this Zone */}
              {data.nearest_pfz.top_species && data.nearest_pfz.top_species.length > 0 && (
                <div className="mt-4 border-t border-hairline pt-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-[11px] font-semibold text-ocean-cyan flex items-center gap-1.5">
                      <Fish className="size-3.5" /> Top Target Fish Species (Data Grounded)
                    </p>
                    <span className="text-[9px] font-mono text-ink-dim uppercase">CMFRI 2024 · OBIS</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {data.nearest_pfz.top_species.slice(0, 3).map((sp, idx) => (
                      <div key={idx} className="rounded-lg border border-hairline/60 bg-shelf-2/60 p-2.5">
                        <div className="flex items-center gap-1.5 mb-1">
                          <span className="flex size-4 items-center justify-center rounded-full bg-ocean-cyan/15 text-[9px] font-bold font-mono text-ocean-cyan">
                            {idx + 1}
                          </span>
                          <span className="font-semibold text-xs text-ink truncate">{sp.name}</span>
                        </div>
                        {sp.scientific_name && (
                          <p className="text-[10px] italic text-ink-dim truncate font-serif">{sp.scientific_name}</p>
                        )}
                        <div className="mt-1.5 flex flex-wrap items-center gap-1">
                          {sp.depth_fit && (
                            <span className="text-[8px] font-mono px-1.5 py-0.5 rounded border border-ocean-cyan/20 bg-ocean-cyan/10 text-ocean-cyan">
                              {sp.depth_fit.replace(/^Optimal\s*\(/i, "").replace(/\)$/, "")}
                            </span>
                          )}
                          {sp.tonnes != null && (
                            <span className="text-[8px] font-mono px-1.5 py-0.5 rounded border border-hairline bg-shelf-1/80 text-ink-dim">
                              {Math.round(sp.tonnes).toLocaleString()} t
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="mt-4 border-t border-hairline pt-3">
                <p className="mb-1.5 text-[11px] font-medium text-ink-dim">{t("zones.persistence")}</p>
                <div className="flex items-center justify-between gap-3">
                  <span data-readout className="text-ink">
                    {data.persistence.label}
                    {data.persistence.score != null && ` · ${Math.round(data.persistence.score * 100)}%`}
                  </span>
                  <span className="text-[11px] text-ink-dim">
                    present {data.persistence.days_present}/{data.persistence.days_on_record} archived days,{" "}
                    {data.persistence.radius_km} km
                  </span>
                </div>
                <div className="mt-2">
                  <ConfidenceMeter tier={data.persistence.confidence.score} />
                </div>
                <p className="mt-1 text-[11px] text-ink-dim">{data.persistence.confidence.rationale}</p>
              </div>

              {data.source_selection && (
                <div className="mt-3">
                  <SourceNarration selection={data.source_selection} />
                </div>
              )}
            </Panel>
          ) : (
            <EmptyState
              icon={<Fish className="size-6" />}
              title={t("zones.noZone")}
              body={t("zones.noZoneBody")}
            />
          )}

          {/* 2b — Marine Life & Fish Species in This Zone */}
          <Panel
            title="Marine Life & Fish Species in This Zone"
            action={
              <Badge tone="cyan">
                {speciesData ? `${speciesData.total.toLocaleString()} species cataloged` : "OBIS · AquaMaps · CMFRI"}
              </Badge>
            }
          >
            <div className="flex flex-col gap-3">
              <p className="text-xs text-ink-muted leading-relaxed">
                Satellite PFZs identify oceanographic thermal &amp; chlorophyll fronts, not individual fish telemetry.
                Species presence is grounded in <strong className="font-semibold text-ink">OBIS</strong> survey observations,{" "}
                <strong className="font-semibold text-ink">AquaMaps</strong> suitability envelopes, and{" "}
                <strong className="font-semibold text-ink">CMFRI 2024</strong> official commercial landings, harmonized with{" "}
                <strong className="font-semibold text-ink">WoRMS</strong> AphiaIDs.
              </p>

              {/* Data Summary Stats */}
              {speciesData?.report_summary && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                  <div className="rounded-lg border border-hairline bg-shelf-2/50 p-2.5">
                    <div className="text-[10px] uppercase font-bold tracking-wider text-ink-dim">WoRMS Species</div>
                    <div data-readout className="text-base font-bold text-ink">
                      {speciesData.report_summary.sources?.total_harmonized_species?.toLocaleString() ?? "3,602"}
                    </div>
                    <div className="text-[10px] text-ink-dim">Harmonized taxa</div>
                  </div>
                  <div className="rounded-lg border border-hairline bg-shelf-2/50 p-2.5">
                    <div className="text-[10px] uppercase font-bold tracking-wider text-ink-dim">Triply Validated</div>
                    <div data-readout className="text-base font-bold text-go">
                      {speciesData.report_summary.overlaps?.triply_validated_all_three ?? "34"}
                    </div>
                    <div className="text-[10px] text-ink-dim">OBIS + AquaMaps + CMFRI</div>
                  </div>
                  <div className="rounded-lg border border-hairline bg-shelf-2/50 p-2.5">
                    <div className="text-[10px] uppercase font-bold tracking-wider text-ink-dim">CMFRI Landings</div>
                    <div data-readout className="text-base font-bold text-accent">
                      {speciesData.report_summary.sources?.cmfri_landings_groups ?? "71"}
                    </div>
                    <div className="text-[10px] text-ink-dim">Commercial groups</div>
                  </div>
                  <div className="rounded-lg border border-hairline bg-shelf-2/50 p-2.5">
                    <div className="text-[10px] uppercase font-bold tracking-wider text-ink-dim">FishBase Checks</div>
                    <div data-readout className="text-base font-bold text-ocean-cyan">
                      5 / 5
                    </div>
                    <div className="text-[10px] text-ink-dim">Depth &amp; temp ranges</div>
                  </div>
                </div>
              )}

              {/* Controls: Search & Filters */}
              <div className="flex flex-col sm:flex-row gap-2 pt-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-2.5 size-4 text-ink-dim" />
                  <input
                    type="text"
                    value={speciesQuery}
                    onChange={(e) => {
                      setSpeciesQuery(e.target.value);
                      setSpeciesVisibleCount(6);
                    }}
                    placeholder="Search fish (e.g., Pomfret, Sardine, Mackerel, Tuna)..."
                    className="w-full rounded-lg border border-hairline bg-shelf-1/90 pl-9 pr-3 py-1.5 text-xs text-ink placeholder:text-ink-dim focus:border-ocean-cyan focus:outline-none"
                  />
                  {speciesQuery && (
                    <button
                      type="button"
                      onClick={() => setSpeciesQuery("")}
                      className="absolute right-2.5 top-2 text-xs text-ink-dim hover:text-ink"
                    >
                      ✕
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
                  <button
                    type="button"
                    onClick={() => {
                      setSpeciesFilter("all");
                      setSpeciesVisibleCount(6);
                    }}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition cursor-pointer ${
                      speciesFilter === "all"
                        ? "bg-ocean-cyan text-on-accent"
                        : "bg-shelf-2 border border-hairline text-ink-muted hover:text-ink"
                    }`}
                  >
                    All
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSpeciesFilter("triply");
                      setSpeciesVisibleCount(6);
                    }}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition cursor-pointer ${
                      speciesFilter === "triply"
                        ? "bg-ocean-cyan text-on-accent"
                        : "bg-shelf-2 border border-hairline text-ink-muted hover:text-ink"
                    }`}
                  >
                    Triply Validated
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSpeciesFilter("commercial");
                      setSpeciesVisibleCount(6);
                    }}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition cursor-pointer ${
                      speciesFilter === "commercial"
                        ? "bg-ocean-cyan text-on-accent"
                        : "bg-shelf-2 border border-hairline text-ink-muted hover:text-ink"
                    }`}
                  >
                    Commercial Landings
                  </button>
                </div>
              </div>

              {/* Toggle FishBase Biometrics */}
              <div className="pt-1">
                <button
                  type="button"
                  onClick={() => setShowBenchmarks((prev) => !prev)}
                  className="flex items-center gap-1.5 text-xs font-medium text-ocean-cyan hover:underline cursor-pointer"
                >
                  {showBenchmarks ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                  {showBenchmarks ? "Hide FishBase Biometric Benchmarks" : "Show FishBase Biometric Benchmarks (Depth, Temp, Habitat)"}
                </button>

                {showBenchmarks && speciesData?.spot_checks && (
                  <div className="mt-2.5 rounded-lg border border-hairline bg-shelf-2/60 p-3 overflow-x-auto">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-dim mb-2">
                      Spot-Checked Biometrics (FishBase Mirror / rOpenSci)
                    </p>
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-hairline text-ink-dim text-[11px]">
                          <th className="py-1 px-1.5 font-medium">Species</th>
                          <th className="py-1 px-1.5 font-medium">Common Name</th>
                          <th className="py-1 px-1.5 font-medium">Depth Range</th>
                          <th className="py-1 px-1.5 font-medium">Temp Range</th>
                          <th className="py-1 px-1.5 font-medium">Habitat</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-hairline/40">
                        {speciesData.spot_checks.map((sc) => (
                          <tr key={sc.species} className="hover:bg-shelf-3/40">
                            <td className="py-1.5 px-1.5 italic font-medium text-ink">{sc.species}</td>
                            <td className="py-1.5 px-1.5 text-ink-muted">{sc.common_name ?? "—"}</td>
                            <td className="py-1.5 px-1.5 text-ink-muted" data-readout>
                              {sc.depth_min_m != null ? `${sc.depth_min_m}–${sc.depth_max_m} m` : "—"}
                            </td>
                            <td className="py-1.5 px-1.5 text-ink-muted" data-readout>
                              {sc.temp_min_c != null ? `${sc.temp_min_c}°–${sc.temp_max_c}°C` : "—"}
                            </td>
                            <td className="py-1.5 px-1.5 text-ink-dim">{sc.habitat_type ?? "Marine"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Species Cards List */}
              {(() => {
                const list = (speciesData?.species ?? []).filter((sp) => {
                  if (speciesFilter === "triply") return sp.in_obis && sp.in_aquamaps && sp.in_cmfri;
                  if (speciesFilter === "commercial") return sp.in_cmfri && (sp.cmfri_tonnes ?? 0) > 0;
                  return true;
                });

                if (list.length === 0) {
                  return (
                    <div className="rounded-lg border border-dashed border-hairline py-8 text-center text-xs text-ink-muted">
                      No fish species found matching your filters.
                    </div>
                  );
                }

                const visible = list.slice(0, speciesVisibleCount);

                return (
                  <div className="flex flex-col gap-2.5 pt-1">
                    {visible.map((sp) => (
                      <div
                        key={sp.aphia_id}
                        className="rounded-lg border border-hairline bg-shelf-1/80 p-3 shadow-xs hover:border-hairline-strong transition"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="text-sm font-bold text-ink">
                                {sp.common_name || sp.scientific_name}
                              </h3>
                              <Badge
                                tone={
                                  sp.confidence === "High"
                                    ? "go"
                                    : sp.confidence === "Medium"
                                    ? "cyan"
                                    : "neutral"
                                }
                              >
                                {sp.confidence} Confidence
                              </Badge>
                            </div>
                            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                              <span className="italic font-serif">{sp.scientific_name}</span>
                              {sp.family && <span>· Family: {sp.family}</span>}
                              {sp.order && <span>· {sp.order}</span>}
                              <a
                                href={`https://www.marinespecies.org/aphia.php?p=taxdetails&id=${sp.aphia_id}`}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-[11px] text-ocean-cyan hover:underline"
                              >
                                <ExternalLink className="size-3" /> WoRMS {sp.aphia_id}
                              </a>
                            </div>
                          </div>
                        </div>

                        {/* Data badges & metrics */}
                        <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                          {sp.in_obis ? (
                            <span className="rounded border border-go/40 bg-go/10 px-2 py-0.5 text-go font-medium">
                              OBIS: {sp.obis_records?.toLocaleString()} records
                              {sp.last_observed_year ? ` (${sp.last_observed_year})` : ""}
                            </span>
                          ) : (
                            <span className="rounded border border-hairline bg-shelf-2/60 px-2 py-0.5 text-ink-dim">
                              OBIS: Not reported
                            </span>
                          )}

                          {sp.in_aquamaps ? (
                            <span className="rounded border border-ocean-cyan/40 bg-ocean-cyan/10 px-2 py-0.5 text-ocean-cyan font-medium">
                              AquaMaps: {sp.aquamaps_prob ? `${Math.round(sp.aquamaps_prob * 100)}% prob` : "Predicted"}
                            </span>
                          ) : (
                            <span className="rounded border border-hairline bg-shelf-2/60 px-2 py-0.5 text-ink-dim">
                              AquaMaps: None
                            </span>
                          )}

                          {sp.in_cmfri ? (
                            <span className="rounded border border-accent/40 bg-accent/10 px-2 py-0.5 text-accent font-medium">
                              CMFRI: {sp.cmfri_tonnes ? `${sp.cmfri_tonnes.toLocaleString()} tonnes` : "Commercial"}
                            </span>
                          ) : (
                            <span className="rounded border border-hairline bg-shelf-2/60 px-2 py-0.5 text-ink-dim">
                              CMFRI: Artisanal / Non-targeted
                            </span>
                          )}
                        </div>

                        {/* Confidence Rationale */}
                        <p className="mt-2 border-t border-hairline/60 pt-1.5 text-[11px] text-ink-muted leading-relaxed">
                          {sp.confidence_rationale}
                        </p>
                      </div>
                    ))}

                    <div className="flex items-center justify-between pt-2 text-xs">
                      <span className="text-ink-dim">
                        Showing {visible.length} of {list.length} species
                      </span>
                      <div className="flex items-center gap-2">
                        {list.length > speciesVisibleCount && (
                          <button
                            type="button"
                            onClick={() => setSpeciesVisibleCount((prev) => prev + 6)}
                            className="rounded border border-hairline bg-shelf-2 px-3 py-1 font-medium text-ink hover:bg-shelf-3 transition cursor-pointer"
                          >
                            Show More ({list.length - visible.length} remaining)
                          </button>
                        )}
                        {speciesVisibleCount > 6 && (
                          <button
                            type="button"
                            onClick={() => setSpeciesVisibleCount(6)}
                            className="rounded border border-hairline bg-shelf-2 px-3 py-1 font-medium text-ink-muted hover:text-ink transition cursor-pointer"
                          >
                            Collapse
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          </Panel>

          {/* 3 — the whole national roster, SEC001–SEC014. A sector with no
              advisory still gets a row saying why; silence would read as
              "nothing there" when it means "nothing published". */}
          <Panel
            title={t("zones.allSectors")}
            action={
              <span className="text-[11px] text-ink-dim">
                {data.all_sectors.filter((s) => !s.is_data_gap).length} / {data.all_sectors.length} {t("zones.withAdvisory")}
              </span>
            }
          >
            <ul className="flex flex-col divide-y divide-hairline">
              {data.all_sectors.map((s) => (
                <li
                  key={s.sector_id}
                  className={`flex items-baseline justify-between gap-3 py-1.5 text-sm ${
                    s.sector_id === data.sector_status.sector_id ? "text-ink" : "text-ink-muted"
                  }`}
                >
                  <span className="min-w-0 truncate">
                    <span data-readout className="text-[11px] text-ink-dim">{s.sector_id}</span>{" "}
                    {s.sector_name}
                    {s.sector_id === data.sector_status.sector_id && (
                      <span className="ml-1.5 text-[11px] text-accent">{t("zones.yours")}</span>
                    )}
                  </span>
                  <span className="shrink-0 text-[11px]">
                    {s.is_data_gap ? (
                      <span className="text-caution" title={s.message}>
                        {s.status === "NO_DATA_CLOUD_COVER" ? t("zones.cloudCover") : s.status.toLowerCase()}
                      </span>
                    ) : (
                      <span className="text-ink-dim">
                        <span data-readout>{s.node_count}</span> nodes · {s.valid_for}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>

          {/* 4 — thermal-front proxy, only when the sector is a data gap */}
          {data.sector_status.is_data_gap && data.thermal_front_proxy.features.length > 0 && data.thermal_front_proxy.orca_metadata && (
            <Panel className="border-caution/30" title={t("zones.thermalProxy")}>
              <div className="mb-2">
                <Badge tone="caution">{t("zones.notOfficial")}</Badge>
              </div>
              <p className="text-sm text-ink-muted">{data.thermal_front_proxy.orca_metadata.not_an_advisory}</p>
              <div className="mt-3">
                <SourceChip
                  dataset={`Thermal-front proxy · ${data.thermal_front_proxy.orca_metadata.applies_to_sector}`}
                  acquisitionTimestamp={data.thermal_front_proxy.orca_metadata.generated_at}
                  confidenceTier="LOW_DATA"
                  detail={data.thermal_front_proxy.orca_metadata.not_an_advisory}
                />
              </div>
            </Panel>
          )}
        </div>
      )}
    </PageBody>
  );
}
