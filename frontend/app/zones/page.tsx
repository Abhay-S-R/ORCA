"use client";

// Fishing zones (§4.2 `/zones`) — PS #1. The order is deliberate: your own
// sector's status leads (a cloud-covered sector says so, in INCOIS's own
// words — data audit C-2), then the nearest advisory node with a heading and
// distance, its persistence across the archived runs, and only then the
// thermal-front proxy, which is valid ONLY when INCOIS has published nothing.
import { useEffect, useState } from "react";
import { Compass, Fish } from "lucide-react";
import { Badge } from "../components/Badge";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceChip } from "../components/SourceChip";
import { SourceNarration, type SourceSelection } from "../components/SourceNarration";
import { EmptyState, ErrorState, Skeleton } from "../components/States";

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

export default function ZonesPage() {
  const [data, setData] = useState<ZonesResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/zones?lat=${POS.lat}&lon=${POS.lon}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError(true));
  }, []);

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="Fishing zones"
        lede="The INCOIS Potential Fishing Zone advisory for your sector, the nearest advised zone with a heading and distance, and how persistent it has been."
      />

      {error && (
        <ErrorState
          title="Could not reach the ORCA API"
          body="The zones service did not respond. Start the backend, then reload this page."
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
            title={`Your sector — ${data.sector_status.sector_name}`}
            action={
              <Badge tone={data.sector_status.is_data_gap ? "caution" : "go"}>
                {data.sector_status.is_data_gap ? "No advisory" : "Advisory published"}
              </Badge>
            }
          >
            <p className="text-sm text-ink-muted">{data.sector_status.message}</p>
            {!data.sector_status.is_data_gap && (
              <ReadoutGrid cols={2}>
                <Readout label="Advisory nodes" value={data.sector_status.node_count} />
                <Readout label="Valid for" value={data.sector_status.valid_for ?? "—"} />
              </ReadoutGrid>
            )}
            {data.sector_status.is_data_gap && data.sector_status.nearest_advisory_out_of_sector && (
              <p className="mt-2 text-xs text-ink-dim">
                The nearest published advisory below is in a neighbouring sector.
              </p>
            )}
          </Panel>

          {/* 2 — nearest advised zone */}
          {data.nearest_pfz.found ? (
            <Panel
              title="Nearest advised zone"
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
              <p className="mb-3 text-[11px] text-ink-dim">
                measured from your {data.measured_from}
                {data.measured_from === "supplied position" &&
                  ` (${data.origin.lat.toFixed(2)}, ${data.origin.lon.toFixed(2)}) — log in to use your home port`}
              </p>
              <ReadoutGrid cols={3}>
                <Readout label="Landing centre ref" value={data.nearest_pfz.landing_center ?? "—"} />
                <Readout label="Advised depth" value={data.nearest_pfz.depth_m ?? "—"} unit="m" />
                <Readout
                  label="Zone centre"
                  value={
                    data.nearest_pfz.latitude != null
                      ? `${data.nearest_pfz.latitude.toFixed(2)}, ${data.nearest_pfz.longitude!.toFixed(2)}`
                      : "—"
                  }
                />
              </ReadoutGrid>

              <div className="mt-4 border-t border-hairline pt-3">
                <p className="mb-1.5 text-[11px] font-medium text-ink-dim">Persistence</p>
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
              title="No advised zone within range"
              body="INCOIS has published no PFZ node near this position. ORCA reports none rather than showing a stale one."
            />
          )}

          {/* 3 — the whole national roster, SEC001–SEC014. A sector with no
              advisory still gets a row saying why; silence would read as
              "nothing there" when it means "nothing published". */}
          <Panel
            title="All sectors"
            action={
              <span className="text-[11px] text-ink-dim">
                {data.all_sectors.filter((s) => !s.is_data_gap).length} of {data.all_sectors.length} with an advisory
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
                      <span className="ml-1.5 text-[11px] text-accent">yours</span>
                    )}
                  </span>
                  <span className="shrink-0 text-[11px]">
                    {s.is_data_gap ? (
                      <span className="text-caution" title={s.message}>
                        {s.status === "NO_DATA_CLOUD_COVER" ? "cloud cover" : s.status.toLowerCase()}
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
            <Panel className="border-caution/30" title="Thermal-front proxy (fallback only)">
              <div className="mb-2">
                <Badge tone="caution">Not an official advisory</Badge>
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
