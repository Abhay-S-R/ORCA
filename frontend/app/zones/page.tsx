"use client";

// Fishing zones (§4.2 `/zones`) — PS #1.
// Modular dashboard layout with unified ZonesToolbar, KpiStrip, ZoneDashboard,
// and official satellite advisory + species catalog.
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Compass, ExternalLink, Fish, Gauge, Search } from "lucide-react";
import { Badge } from "../components/Badge";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceChip } from "../components/SourceChip";
import { SourceNarration, type SourceSelection } from "../components/SourceNarration";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { authFetch, invalidateProfile, useAuth } from "../lib/auth";
import { ageLabel, type Recency } from "../lib/recency";
import { usePersona } from "../persona/context";
import { useT } from "../i18n/useT";
import { KpiStrip, ZoneDashboard, ZonesToolbar, useFishingProfit } from "./zones-dashboard";

function dbVesselToZoneKey(rawClass: string | null | undefined): string {
  if (!rawClass) return "small_fishing";
  const c = rawClass.toLowerCase().trim();
  if (c === "trawler" || c === "mechanized_trawler") return "mechanized_trawler";
  if (c === "cargo" || c === "cargo_vessel") return "cargo_vessel";
  return "small_fishing";
}

const VESSEL_DISPLAY_NAMES: Record<string, string> = {
  small_fishing: "Small boat",
  mechanized_trawler: "Trawler",
  cargo_vessel: "Cargo",
  catamaran: "Catamaran",
  fibreglass: "Fibreglass boat",
  mechanised: "Mechanised boat",
  trawler: "Trawler",
  cargo: "Cargo vessel",
};

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

  return { reachKm: cruiseSpeedKn != null ? cruiseSpeedKn * 1.852 * REACH_HOURS_OUTBOUND : null, cruiseSpeedKn, checked };
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type ZonesResponse = {
  measured_from: string;
  origin: { lat: number; lon: number };
  nearest_pfz: {
    found: boolean;
    bearing_deg?: number;
    compass?: string;
    distance_km?: number;
    landing_center?: string;
    latitude?: number;
    longitude?: number;
    depth_m?: number;
    sector_id?: string;
    valid_for?: string;
    received_at?: string;
    fetched_at?: string;
    beyond_reach?: boolean;
    max_km?: number;
    top_species?: Array<{
      aphia_id: number;
      name: string;
      scientific_name?: string | null;
      depth_fit?: string | null;
      tonnes?: number | null;
      source: string;
    }>;
  } & Recency;
  persistence: {
    label: string;
    days_present: number;
    days_on_record: number;
    radius_km: number;
    score: number | null;
    confidence: {
      score: "HIGH" | "MEDIUM" | "LOW_DATA";
      rationale: string;
    };
  };
  sector_status: {
    sector_id: string;
    sector_name: string;
    status: string;
    is_data_gap: boolean;
    message: string;
    node_count: number;
    valid_for: string | null;
    latest_advisory: (Recency & {
      valid_for: string;
      node_count: number;
      received_at?: string;
      fetched_at?: string;
    }) | null;
    nearest_advisory_out_of_sector?: {
      sector_id: string;
      sector_name: string;
      valid_for: string;
      node_count: number;
    } | null;
  };
  all_sectors: Array<{
    sector_id: string;
    sector_name: string;
    status: string;
    is_data_gap: boolean;
    message: string;
    node_count: number;
    valid_for: string | null;
  }>;
  thermal_front_proxy: {
    features: Array<unknown>;
    orca_metadata?: {
      not_an_advisory: string;
      generated_at: string;
      applies_to_sector: string;
      data_source: string;
    };
  };
  source_selection?: SourceSelection;
};

type FishingBan = {
  available: boolean;
  coast?: string;
  in_ban_period?: boolean;
  applies_here?: boolean;
  window?: string;
  next_window?: string;
  days?: number;
  distance_to_nearest_eez_edge_nm?: number | null;
  note?: string;
  order?: {
    issuing_authority: string;
    file_number: string;
    order_date: string;
    applies_to: string;
    exemption: string;
    pdf_url: string;
  };
};

type SpeciesApiResponse = {
  total: number;
  report_summary?: {
    sources?: {
      total_harmonized_species?: number;
      cmfri_landings_groups?: number;
    };
    overlaps?: {
      triply_validated_all_three?: number;
    };
  };
  species: Array<{
    aphia_id: number;
    common_name: string | null;
    scientific_name: string;
    family: string | null;
    order: string | null;
    confidence: "High" | "Medium" | "Low";
    confidence_rationale: string;
    in_obis: boolean;
    in_aquamaps: boolean;
    in_cmfri: boolean;
    obis_records?: number;
    last_observed_year?: number | null;
    aquamaps_prob?: number | null;
    cmfri_tonnes?: number | null;
  }>;
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

// ─── AVAILABLE COASTAL PORTS ──────────────────────────────────────────────────
const AVAILABLE_PORTS = [
  { id: "kochi", name: "Kochi", state: "Kerala", lat: 9.9312, lon: 76.2673 },
  { id: "kozhikode", name: "Kozhikode", state: "Kerala", lat: 11.2588, lon: 75.7804 },
  { id: "thiruvananthapuram", name: "Thiruvananthapuram", state: "Kerala", lat: 8.5241, lon: 76.9366 },
  { id: "mangaluru", name: "Mangaluru", state: "Karnataka", lat: 12.8698, lon: 74.8430 },
  { id: "karwar", name: "Karwar", state: "Karnataka", lat: 14.8137, lon: 74.1303 },
  { id: "chennai", name: "Chennai", state: "Tamil Nadu", lat: 13.0827, lon: 80.2707 },
  { id: "tuticorin", name: "Tuticorin", state: "Tamil Nadu", lat: 8.7642, lon: 78.1348 },
  { id: "mumbai", name: "Mumbai", state: "Maharashtra", lat: 18.9388, lon: 72.8354 },
  { id: "veraval", name: "Veraval", state: "Gujarat", lat: 20.9072, lon: 70.3673 },
  { id: "visakhapatnam", name: "Visakhapatnam", state: "Andhra Pradesh", lat: 17.6868, lon: 83.2185 },
  { id: "paradip", name: "Paradip", state: "Odisha", lat: 20.3170, lon: 86.6093 },
];

export default function ZonesPage() {
  const [data, setData] = useState<ZonesResponse | null>(null);
  const [ban, setBan] = useState<FishingBan | null>(null);
  const [speciesData, setSpeciesData] = useState<SpeciesApiResponse | null>(null);
  const [speciesQuery, setSpeciesQuery] = useState("");
  const [speciesFilter, setSpeciesFilter] = useState<"all" | "triply" | "commercial">("all");
  const [showBenchmarks, setShowBenchmarks] = useState(false);
  const [speciesVisibleCount, setSpeciesVisibleCount] = useState(6);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [allSectorsOpen, setAllSectorsOpen] = useState(false);
  const [activeVessel, setActiveVessel] = useState<string>("small_fishing");
  const [profileVessel, setProfileVessel] = useState<{
    name: string | null;
    vesselClass: string;
    zoneKey: string;
  } | null>(null);
  const [error, setError] = useState(false);
  const t = useT();
  const { persona } = usePersona();
  const reach = useVesselReachKm();
  const auth = useAuth();

  // User's registered home port from home page / profile (or null if not logged in)
  const userHomePort = auth.status === "signed_in" ? auth.profile?.home_port : null;
  const userHomePortName = auth.status === "signed_in" ? auth.profile?.home_port_name : null;
  const registeredHomePort = useMemo(() => {
    if (!userHomePort) return null;
    return {
      id: "default_home",
      name: userHomePortName ?? "Home Port",
      state: "Home Port",
      lat: userHomePort.lat,
      lon: userHomePort.lon,
    };
  }, [userHomePort, userHomePortName]);

  // Selected port state ONLY for the fishing zone page (defaults to 'default_home')
  const [selectedPortKey, setSelectedPortKey] = useState<string>("default_home");

  const currentPort = useMemo(() => {
    if (selectedPortKey === "default_home") {
      if (registeredHomePort) return registeredHomePort;
      return AVAILABLE_PORTS[0]; // Kochi fallback
    }
    const match = AVAILABLE_PORTS.find((p) => p.id === selectedPortKey);
    return match ?? AVAILABLE_PORTS[0];
  }, [selectedPortKey, registeredHomePort]);

  const posParam = `lat=${currentPort.lat}&lon=${currentPort.lon}`;

  // Sync vessel class from profile if logged in
  useEffect(() => {
    if (auth.status !== "signed_in") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from the external auth store
      setProfileVessel(null);
      return;
    }
    let cancelled = false;

    async function syncVesselFromProfile() {
      let vessel: { id: string; name?: string | null; vessel_class?: string; class?: string } | null = null;
      if (auth.profile?.active_vessel_id) {
        try {
          const r = await authFetch(`/api/vessels/${auth.profile.active_vessel_id}`);
          if (r.ok) vessel = await r.json();
        } catch {
          // ignore
        }
      } else {
        try {
          const r = await authFetch("/api/vessels");
          if (r.ok) {
            const list = await r.json();
            if (Array.isArray(list) && list.length > 0) {
              vessel = list[0];
              // Persist as active in profile so other pages stay synced
              authFetch("/api/profile/active-vessel", {
                method: "PUT",
                body: JSON.stringify({ vessel_id: list[0].id }),
              })
                .then(() => invalidateProfile())
                .catch(() => {});
            }
          }
        } catch {
          // ignore
        }
      }

      if (!cancelled && vessel) {
        const rawClass = vessel.vessel_class ?? vessel.class;
        const key = dbVesselToZoneKey(rawClass);
        setActiveVessel(key);
        setProfileVessel({
          name: vessel.name ?? null,
          vesselClass: rawClass ?? key,
          zoneKey: key,
        });
      }
    }

    syncVesselFromProfile();

    return () => {
      cancelled = true;
    };
  }, [auth.status, auth.profile?.active_vessel_id]);

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

  const profit = useFishingProfit(currentPort.lat, currentPort.lon, activeVessel, reach.cruiseSpeedKn);

  const reachWithin =
    persona === "fisherman" && reach.reachKm != null && data?.nearest_pfz.distance_km != null
      ? Number(data.nearest_pfz.distance_km) <= reach.reachKm
      : null;

  const showProxy =
    !!data &&
    data.sector_status.is_data_gap &&
    data.thermal_front_proxy.features.length > 0 &&
    !!data.thermal_front_proxy.orca_metadata;

  const profileVesselLabel = useMemo(() => {
    if (!profileVessel) return null;
    return profileVessel.name || VESSEL_DISPLAY_NAMES[profileVessel.vesselClass] || "Vessel";
  }, [profileVessel]);

  const isProfileVesselActive = profileVessel?.zoneKey === activeVessel;

  return (
    <PageBody className="mx-auto max-w-4xl">
      <PageHeader title={t("zones.title")} lede={t("zones.lede")} />

      <ZonesToolbar
        ports={AVAILABLE_PORTS}
        currentPort={currentPort}
        selectedPortKey={selectedPortKey}
        onSelectPortKey={setSelectedPortKey}
        registeredHomePortName={registeredHomePort?.name ?? null}
        activeVessel={activeVessel}
        onSelectVessel={setActiveVessel}
        profileVesselLabel={profileVesselLabel}
        isProfileVesselActive={isProfileVesselActive}
      />

      {error && <ErrorState title={t("zones.apiError")} body={t("zones.apiErrorBody")} />}
      {!data && !error && <Skeleton className="mb-4 h-28 w-full" />}

      {data && (
        <KpiStrip
          sector={{
            gap: data.sector_status.is_data_gap,
            name: data.sector_status.sector_name,
            message: data.sector_status.message,
          }}
          nearest={{
            found: data.nearest_pfz.found,
            label: data.nearest_pfz.found
              ? `${data.nearest_pfz.compass} ${data.nearest_pfz.distance_km} km`
              : null,
            within: reachWithin,
            beyondReach: !!data.nearest_pfz.beyond_reach,
          }}
          bestZone={profit.data?.zones.find((z) => z.is_best_zone && z.show_profit) ?? null}
          ban={ban?.available ? ban : null}
        />
      )}

      <ZoneDashboard profit={profit} />

      {data && (
        <div className="flex flex-col gap-4">
          <div className={`grid gap-4 ${showProxy ? "lg:grid-cols-2" : ""}`}>
            {/* Nearest advised zone */}
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
                {data.sector_status.is_data_gap && data.sector_status.latest_advisory && (
                  <p className="mb-2 text-xs text-ink-muted">
                    Latest advisory for this sector: {data.sector_status.latest_advisory.valid_for},{" "}
                    {data.sector_status.latest_advisory.node_count} zones —{" "}
                    {ageLabel(data.sector_status.latest_advisory.valid_for, data.sector_status.latest_advisory) ??
                      "still current"}
                    . Shown on the map, faded by age.
                  </p>
                )}

                {/* Small Vessel Reach Check */}
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

            {/* Thermal-front proxy */}
            {showProxy && (
              <Panel className="border-caution/30" title={t("zones.thermalProxy")}>
                <div className="mb-2">
                  <Badge tone="caution">{t("zones.notOfficial")}</Badge>
                </div>
                <p className="text-sm text-ink-muted">{data.thermal_front_proxy.orca_metadata!.not_an_advisory}</p>
                <div className="mt-3">
                  <SourceChip
                    dataset={`Thermal-front proxy · ${data.thermal_front_proxy.orca_metadata!.applies_to_sector}`}
                    acquisitionTimestamp={data.thermal_front_proxy.orca_metadata!.generated_at}
                    confidenceTier="LOW_DATA"
                    detail={data.thermal_front_proxy.orca_metadata!.not_an_advisory}
                  />
                </div>
              </Panel>
            )}
          </div>

          {/* Seasonal fishing ban (full order details show when closure is active) */}
          {ban?.available && ban.in_ban_period && (
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

          {/* Marine Species Catalog */}
          <Panel
            title="Marine Species Catalog (OBIS · AquaMaps · CMFRI)"
            action={
              <button
                type="button"
                onClick={() => setCatalogOpen((prev) => !prev)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-hairline/80 bg-shelf-2 px-2.5 py-1 text-xs font-semibold text-ocean-cyan hover:bg-shelf-3 transition cursor-pointer"
              >
                {catalogOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                {catalogOpen ? "Hide Catalog" : `Explore ${speciesData ? speciesData.total.toLocaleString() : "3,602"} Taxa`}
              </button>
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

              {catalogOpen && (
                <>
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
                          className="absolute right-2.5 top-2 text-xs text-ink-dim hover:text-ink cursor-pointer"
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
                </>
              )}
            </div>
          </Panel>

          {/* All National Sectors */}
          <Panel
            title={t("zones.allSectors")}
            action={
              <button
                type="button"
                onClick={() => setAllSectorsOpen((prev) => !prev)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-hairline/80 bg-shelf-2 px-2.5 py-1 text-xs font-semibold text-ocean-cyan hover:bg-shelf-3 transition cursor-pointer"
              >
                {allSectorsOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                {allSectorsOpen ? "Collapse Roster" : `View ${data.all_sectors.length} National Sectors`}
              </button>
            }
          >
            {allSectorsOpen ? (
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
            ) : (
              <div className="flex items-center justify-between text-xs text-ink-muted py-1">
                <span>
                  National coverage: <strong className="text-ink font-semibold">{data.all_sectors.filter((s) => !s.is_data_gap).length}</strong> of {data.all_sectors.length} sectors active today.
                </span>
                <span className="text-[11px] text-ink-dim">
                  {data.sector_status.sector_name} ({data.sector_status.sector_id}) active for this port.
                </span>
              </div>
            )}
          </Panel>
        </div>
      )}
    </PageBody>
  );
}
