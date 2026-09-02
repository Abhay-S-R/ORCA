"use client";

// Fishing Zones (§4.2 `/zones`) — nearest potential fishing zones with the
// distance and bearing from each home port, because "which way and how far"
// is the only form of this answer that is usable from a boat.
import { useEffect, useState } from "react";
import { Compass, Fish } from "lucide-react";
import { Badge } from "../components/Badge";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceChip } from "../components/SourceChip";
import { EmptyState, ErrorState, Skeleton } from "../components/States";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type PortBearing = { distance_km: number; bearing_deg: number; compass: string };
type ZoneFeature = {
  geometry: { coordinates: [number, number] };
  properties: {
    cell_count: number;
    approx_area_km2: number;
    mean_sst_c: number;
    mean_depth_m: number;
    bearings_from_ports: Record<string, PortBearing>;
  };
};
type ZonesResponse = {
  features: ZoneFeature[];
  orca_metadata: { generated_at: string; not_an_advisory: string; applies_to_sector: string };
};

export default function ZonesPage() {
  const [data, setData] = useState<ZonesResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/zones`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError(true));
  }, []);

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="Fishing zones"
        lede="Thermal-front zones near the pilot sector, with the heading and distance to each one from your port."
      />

      {error && (
        <ErrorState
          title="Could not reach the ORCA API"
          body="The zones service did not respond. Start the backend, then reload this page."
        />
      )}

      {/* The caveat leads, because this data is a proxy and a user who reads
          only the first panel must still come away knowing that. */}
      {data && (
        <Panel className="mb-4 border-caution/30" title="What this is">
          <div className="mb-2">
            <Badge tone="caution">Not an official advisory</Badge>
          </div>
          <p className="text-sm text-ink-muted">{data.orca_metadata.not_an_advisory}</p>
        </Panel>
      )}

      {!data && !error && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {data?.features.length === 0 && (
        <EmptyState
          icon={<Fish className="size-6" />}
          title="No zones in this sector right now"
          body="Thermal fronts come and go. ORCA reports none rather than showing a stale one."
        />
      )}

      <ul className="flex flex-col gap-3">
        {data?.features.map((f, i) => (
          <li key={i}>
            <Panel
              title={`Zone ${i + 1}`}
              action={
                <span className="text-[11px] text-ink-dim">
                  ~{f.properties.approx_area_km2} km² · {f.properties.cell_count} cells
                </span>
              }
            >
              <ReadoutGrid cols={3}>
                <Readout label="Sea surface temp" value={f.properties.mean_sst_c} unit="°C" />
                <Readout label="Mean depth" value={f.properties.mean_depth_m} unit="m" />
                <Readout
                  label="Centre"
                  value={`${f.geometry.coordinates[1].toFixed(2)}, ${f.geometry.coordinates[0].toFixed(2)}`}
                />
              </ReadoutGrid>

              <div className="mt-4 border-t border-hairline pt-3">
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-medium text-ink-dim">
                  <Compass className="size-3.5" aria-hidden="true" />
                  From your ports
                </p>
                <ul className="flex flex-col gap-1">
                  {Object.entries(f.properties.bearings_from_ports).map(([port, b]) => (
                    <li key={port} className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="text-ink-muted">{port}</span>
                      <span data-readout className="text-ink">
                        {b.compass} {b.bearing_deg}° · {b.distance_km} km
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              {data && (
                <div className="mt-3">
                  <SourceChip
                    dataset={`Thermal-front proxy · ${data.orca_metadata.applies_to_sector}`}
                    acquisitionTimestamp={data.orca_metadata.generated_at}
                    confidenceTier="LOW_DATA"
                    detail={data.orca_metadata.not_an_advisory}
                  />
                </div>
              )}
            </Panel>
          </li>
        ))}
      </ul>
    </PageBody>
  );
}
