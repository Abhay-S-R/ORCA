"use client";

// Fishing zones (§4.2 `/zones`) — PS #1. The order is deliberate: your own
// sector's status leads (a cloud-covered sector says so, in INCOIS's own
// words — data audit C-2), then the nearest advisory node with a heading and
// distance, its persistence across the archived runs, and only then the
// thermal-front proxy, which is valid ONLY when INCOIS has published nothing.
// P3.12 — all visible strings now sourced from the i18n dictionaries via useT().
import { useEffect, useState } from "react";
import { Compass, Fish, Gauge } from "lucide-react";
import { Badge } from "../components/Badge";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceChip } from "../components/SourceChip";
import { SourceNarration, type SourceSelection } from "../components/SourceNarration";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { authFetch, useAuth } from "../lib/auth";
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const POS = { lat: 8.8, lon: 78.14 }; // Thoothukudi — pilot reference position

type Confidence = { score: "HIGH" | "MEDIUM" | "LOW_DATA"; rationale: string };

type Sector = {
  sector_id: string;
  sector_name: string;
  status: string;
  message: string;
  node_count: number;
  valid_for: string | null;
  is_data_gap: boolean;
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
  };
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

export default function ZonesPage() {
  const [data, setData] = useState<ZonesResponse | null>(null);
  const [ban, setBan] = useState<FishingBan | null>(null);
  const [error, setError] = useState(false);
  const t = useT();
  const { persona } = usePersona();
  const reach = useVesselReachKm();

  useEffect(() => {
    fetch(`${API_BASE}/api/zones?lat=${POS.lat}&lon=${POS.lon}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError(true));
    fetch(`${API_BASE}/api/fishing-ban?lat=${POS.lat}&lon=${POS.lon}`)
      .then((r) => r.json())
      .then(setBan)
      .catch(() => setBan(null));
  }, []);

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
