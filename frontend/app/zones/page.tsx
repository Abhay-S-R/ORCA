"use client";

// Fishing zones (§4.2 `/zones`) — PS #1.
// Modular dashboard layout with unified ZonesToolbar, KpiStrip, ZoneDashboard,
// and official satellite advisory + species catalog.
import { useEffect, useMemo, useState } from "react";
import { Compass, Fish } from "lucide-react";
import { Badge } from "../components/Badge";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceChip } from "../components/SourceChip";
import { ErrorState } from "../components/States";
import { authFetch, invalidateProfile, useAuth } from "../lib/auth";
import { type Recency } from "../lib/recency";
import { usePersona } from "../persona/context";
import { useT } from "../i18n/useT";
import { KpiStrip, ZoneDashboard, ZonesToolbar, useFishingProfit, calculateBearing } from "./zones-dashboard";
import { useZonesT } from "./translations";

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

// ─── AVAILABLE COASTAL PORTS ──────────────────────────────────────────────────
const AVAILABLE_PORTS = [
  // Kerala
  { id: "kochi", name: "Kochi", state: "Kerala", lat: 9.9312, lon: 76.2673 },
  { id: "kozhikode", name: "Kozhikode", state: "Kerala", lat: 11.2588, lon: 75.7804 },
  { id: "thiruvananthapuram", name: "Thiruvananthapuram", state: "Kerala", lat: 8.5241, lon: 76.9366 },
  { id: "kollam", name: "Kollam", state: "Kerala", lat: 8.8800, lon: 76.5900 },
  { id: "beypore", name: "Beypore", state: "Kerala", lat: 11.1600, lon: 75.8000 },

  // Karnataka
  { id: "mangaluru", name: "Mangaluru", state: "Karnataka", lat: 12.8698, lon: 74.8430 },
  { id: "karwar", name: "Karwar", state: "Karnataka", lat: 14.8137, lon: 74.1303 },
  { id: "malpe", name: "Malpe", state: "Karnataka", lat: 13.3510, lon: 74.7040 },

  // Goa
  { id: "mormugao", name: "Mormugao", state: "Goa", lat: 15.4100, lon: 73.8000 },

  // Maharashtra
  { id: "mumbai", name: "Mumbai", state: "Maharashtra", lat: 18.9388, lon: 72.8354 },
  { id: "ratnagiri", name: "Ratnagiri", state: "Maharashtra", lat: 16.9900, lon: 73.2900 },
  { id: "jnpt", name: "JNPT", state: "Maharashtra", lat: 18.9500, lon: 72.9500 },

  // Gujarat
  { id: "veraval", name: "Veraval", state: "Gujarat", lat: 20.9072, lon: 70.3673 },
  { id: "porbandar", name: "Porbandar", state: "Gujarat", lat: 21.6420, lon: 69.6090 },
  { id: "okha", name: "Okha", state: "Gujarat", lat: 22.4670, lon: 69.0710 },
  { id: "kandla", name: "Kandla", state: "Gujarat", lat: 22.9800, lon: 70.2200 },
  { id: "mundra", name: "Mundra", state: "Gujarat", lat: 22.8400, lon: 69.7000 },

  // Tamil Nadu
  { id: "chennai", name: "Chennai", state: "Tamil Nadu", lat: 13.0827, lon: 80.2707 },
  { id: "tuticorin", name: "Tuticorin", state: "Tamil Nadu", lat: 8.7642, lon: 78.1348 },
  { id: "rameswaram", name: "Rameswaram", state: "Tamil Nadu", lat: 9.2876, lon: 79.3129 },
  { id: "kanyakumari", name: "Kanyakumari", state: "Tamil Nadu", lat: 8.0883, lon: 77.5385 },
  { id: "nagapattinam", name: "Nagapattinam", state: "Tamil Nadu", lat: 10.7600, lon: 79.8400 },
  { id: "cuddalore", name: "Cuddalore", state: "Tamil Nadu", lat: 11.7500, lon: 79.7700 },

  // Puducherry
  { id: "puducherry", name: "Puducherry", state: "Puducherry", lat: 11.9330, lon: 79.8300 },

  // Andhra Pradesh
  { id: "visakhapatnam", name: "Visakhapatnam", state: "Andhra Pradesh", lat: 17.6868, lon: 83.2185 },
  { id: "kakinada", name: "Kakinada", state: "Andhra Pradesh", lat: 16.9891, lon: 82.2475 },
  { id: "machilipatnam", name: "Machilipatnam", state: "Andhra Pradesh", lat: 16.1800, lon: 81.1400 },
  { id: "krishnapatnam", name: "Krishnapatnam", state: "Andhra Pradesh", lat: 14.2500, lon: 80.1200 },

  // Odisha
  { id: "paradip", name: "Paradip", state: "Odisha", lat: 20.3170, lon: 86.6093 },
  { id: "gopalpur", name: "Gopalpur", state: "Odisha", lat: 19.2600, lon: 84.9100 },
  { id: "dhamra", name: "Dhamra", state: "Odisha", lat: 20.8000, lon: 86.9700 },

  // West Bengal
  { id: "kolkata", name: "Kolkata", state: "West Bengal", lat: 22.5726, lon: 88.3639 },
  { id: "haldia", name: "Haldia", state: "West Bengal", lat: 22.0500, lon: 88.0700 },

  // Lakshadweep
  { id: "kavaratti", name: "Kavaratti", state: "Lakshadweep", lat: 10.5700, lon: 72.6400 },

  // Andaman & Nicobar
  { id: "port_blair", name: "Port Blair", state: "Andaman & Nicobar", lat: 11.6700, lon: 92.7300 },
];

export default function ZonesPage() {
  const [data, setData] = useState<ZonesResponse | null>(null);
  const [ban, setBan] = useState<FishingBan | null>(null);
  const [activeVessel, setActiveVessel] = useState<string>("small_fishing");
  const [profileVessel, setProfileVessel] = useState<{
    name: string | null;
    vesselClass: string;
    zoneKey: string;
  } | null>(null);
  const [error, setError] = useState(false);
  const t = useT();
  const { t: zT, zoneName, zoneDesc, species: tSpecies, bearing: tBearing } = useZonesT();
  const { persona } = usePersona();
  const reach = useVesselReachKm();
  const auth = useAuth();

  // User's registered home port from home page / profile (or null if not logged in)
  const userHomePort = auth.status === "signed_in" ? auth.profile?.home_port : null;
  const userHomePortName = auth.status === "signed_in" ? auth.profile?.home_port_name : null;
  const registeredHomePort = useMemo(() => {
    if (!userHomePort) return null;
    let portState = "Maharashtra";
    if (userHomePortName) {
      const q = userHomePortName.toLowerCase();
      const match = AVAILABLE_PORTS.find(
        (p) => p.name.toLowerCase().includes(q) || q.includes(p.name.toLowerCase())
      );
      if (match) portState = match.state;
    }
    if (userHomePort) {
      let minDist = Infinity;
      let closestState = portState;
      for (const p of AVAILABLE_PORTS) {
        const d = (p.lat - userHomePort.lat) ** 2 + (p.lon - userHomePort.lon) ** 2;
        if (d < minDist) {
          minDist = d;
          closestState = p.state;
        }
      }
      portState = closestState;
    }
    return {
      id: "default_home",
      name: userHomePortName ?? "Mumbai",
      state: portState,
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

  const profit = useFishingProfit(currentPort.lat, currentPort.lon, activeVessel, reach.cruiseSpeedKn);

  const reachWithin =
    persona === "fisherman" && reach.reachKm != null && data?.nearest_pfz.distance_km != null
      ? Number(data.nearest_pfz.distance_km) <= reach.reachKm
      : null;

  // Immediate sector name from the selected port (0ms delay)
  const resolvedState =
    currentPort.state && currentPort.state !== "Home Port"
      ? currentPort.state
      : data?.sector_status?.sector_name || "Maharashtra";
  const currentSectorName = (resolvedState || "Coast").toUpperCase();
  const isSectorDataCurrent =
    data?.sector_status &&
    data.sector_status.sector_name.toLowerCase() === resolvedState.toLowerCase();
  const sectorGap = isSectorDataCurrent ? data.sector_status.is_data_gap : false;
  const sectorMessage = isSectorDataCurrent
    ? data.sector_status.message
    : `Active coastal coverage charted for ${currentPort.name}`;

  // Closest charted zone for the selected port
  const nearestChartedZone = useMemo(() => {
    const zones = profit.data?.zones;
    if (!zones || zones.length === 0) return null;
    return [...zones].sort((a, b) => a.distance_km - b.distance_km)[0];
  }, [profit.data?.zones]);

  // Nearest advised zone info with exact bearing & km
  const nearestInfo = useMemo(() => {
    if (nearestChartedZone) {
      const bearing = calculateBearing(
        currentPort.lat,
        currentPort.lon,
        nearestChartedZone.lat,
        nearestChartedZone.lon
      ).compass;
      const dist = nearestChartedZone.distance_km;
      const isWithinReach = reach.reachKm != null ? dist <= reach.reachKm : dist <= 120;
      return {
        found: true,
        label: `${bearing} ${dist.toFixed(1)} km`,
        zoneName: nearestChartedZone.zone_name,
        within: isWithinReach,
        beyondReach: !isWithinReach,
      };
    }
    const pfz = data?.nearest_pfz;
    if (pfz?.found) {
      return {
        found: true,
        label: `${pfz.compass} ${pfz.distance_km} km`,
        zoneName: "Advisory zone",
        within: reachWithin,
        beyondReach: !!pfz.beyond_reach,
      };
    }
    return {
      found: false,
      label: null,
      zoneName: null,
      within: null,
      beyondReach: false,
    };
  }, [nearestChartedZone, currentPort.lat, currentPort.lon, reach.reachKm, data, reachWithin]);

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

      <KpiStrip
        sector={{
          gap: sectorGap,
          name: currentSectorName,
          message: sectorMessage,
        }}
        nearest={nearestInfo}
        bestZone={profit.data?.zones.find((z) => z.is_best_zone && z.show_profit) ?? profit.data?.zones[0] ?? null}
      />

      <ZoneDashboard profit={profit} onSelectPort={setSelectedPortKey} />

      {/* Downside container: Nearest Advised Zone matched to selected port */}
      {(nearestChartedZone || showProxy || (ban?.available && ban.in_ban_period)) && (
        <div className="flex flex-col gap-4">
          <div className={`grid gap-4 ${showProxy ? "lg:grid-cols-2" : ""}`}>
            {/* Nearest advised fishing zone */}
            {nearestChartedZone && (() => {
              const b = calculateBearing(currentPort.lat, currentPort.lon, nearestChartedZone.lat, nearestChartedZone.lon);
              return (
              <Panel
                title={zT("Highest Advised Fishing Zone")}
                action={
                  <span className="rounded bg-go/15 px-2 py-0.5 text-[11px] font-bold text-go">
                    {zT("Active Ground")}
                  </span>
                }
              >
                <div className="mb-2 flex items-center gap-2 text-lg">
                  <Compass className="size-5 text-ocean-cyan" aria-hidden="true" />
                  <span data-readout className="font-bold text-ink">
                    {tBearing(b.compass)}{" "}
                    {b.deg}° ·{" "}
                    {nearestChartedZone.distance_km.toFixed(1)} km
                  </span>
                  <span className="text-xs font-semibold text-ink-muted">
                    ({zoneName(nearestChartedZone.zone_name)})
                  </span>
                </div>

                <p className="mb-3 text-xs text-ink-muted leading-relaxed">
                  {zoneDesc(nearestChartedZone.zone_description, nearestChartedZone.zone_name)} · {currentPort.name} ({currentPort.lat.toFixed(2)}°N, {currentPort.lon.toFixed(2)}°E).
                </p>

                <ReadoutGrid cols={3}>
                  <Readout label={zT("Departure Port")} value={currentPort.name} />
                  <Readout
                    label={zT("Advised Depth")}
                    value={
                      nearestChartedZone.zone_type === "nearshore"
                        ? "15 – 35"
                        : nearestChartedZone.zone_type === "offshore"
                        ? "40 – 75"
                        : "75 – 180"
                    }
                    unit="m"
                  />
                  <Readout
                    label={zT("Zone Coordinates")}
                    value={`${nearestChartedZone.lat.toFixed(2)}, ${nearestChartedZone.lon.toFixed(2)}`}
                  />
                </ReadoutGrid>

                {/* Top Target Fish Species */}
                {nearestChartedZone.priced_species && nearestChartedZone.priced_species.length > 0 && (
                  <div className="mt-4 border-t border-hairline pt-3">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-[11px] font-semibold text-ocean-cyan flex items-center gap-1.5">
                        <Fish className="size-3.5" /> {zT("Top Target Fish Species")}
                      </p>
                      <span className="text-[9px] font-mono text-ink-dim uppercase">{zT("Official Landings Mix")}</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      {nearestChartedZone.priced_species.slice(0, 3).map((sp, idx) => (
                        <div key={idx} className="rounded-lg border border-hairline/60 bg-shelf-2/60 p-2.5">
                          <div className="flex items-center gap-1.5 mb-1">
                            <span className="flex size-4 items-center justify-center rounded-full bg-ocean-cyan/15 text-[9px] font-bold font-mono text-ocean-cyan">
                              {idx + 1}
                            </span>
                            <span className="font-semibold text-xs text-ink truncate">{tSpecies(sp.common_name)}</span>
                          </div>
                          {sp.scientific_name && (
                            <p className="text-[10px] italic text-ink-dim truncate font-serif">{sp.scientific_name}</p>
                          )}
                          <div className="mt-1.5 flex items-center justify-between text-[10px] font-mono text-ink-muted">
                            <span>{sp.share_pct}% {zT("catch")}</span>
                            <span className="font-semibold text-ink">~{sp.est_kg} kg</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Panel>
            );})()}

            {/* Thermal-front proxy */}
            {showProxy && data?.thermal_front_proxy?.orca_metadata && (
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



        </div>
      )}
    </PageBody>
  );
}
