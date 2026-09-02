"use client";

import { useEffect, useState } from "react";
import { Badge } from "../components/Badge";
import { Card } from "../components/Card";
import { SourceChip } from "../components/SourceChip";

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

// Fishing Zones (§4.2 `/zones`): nearest PFZ, distance + bearing from home
// port (plan §4 S4 Day 6 — "rendering PFZ from cached advisories").
export default function ZonesPage() {
  const [data, setData] = useState<ZonesResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/zones`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <div>
        <h1 className="text-xl font-semibold mb-4">Fishing Zones</h1>
        <p className="text-sm text-black/50">Could not reach the ORCA API — is the backend running?</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold mb-4">Fishing Zones</h1>

      {data && (
        <Card className="mb-4 bg-safety-caution-bg/40" title="About this data">
          <div className="mb-2">
            <Badge tone="caution">LOW-DATA</Badge>
          </div>
          <p className="text-sm">{data.orca_metadata.not_an_advisory}</p>
        </Card>
      )}

      {!data && <p className="text-sm text-black/50">Loading…</p>}

      <ul className="flex flex-col gap-3">
        {data?.features.map((f, i) => (
          <li key={i}>
            <Card title={`Zone ${i + 1} — ${f.properties.cell_count} cells, ~${f.properties.approx_area_km2} km²`}>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <dt className="text-black/50">Mean SST</dt>
                <dd>{f.properties.mean_sst_c} °C</dd>
                <dt className="text-black/50">Mean depth</dt>
                <dd>{f.properties.mean_depth_m} m</dd>
              </dl>
              <ul className="mt-2 text-sm text-black/70">
                {Object.entries(f.properties.bearings_from_ports).map(([port, b]) => (
                  <li key={port}>
                    {port}: {b.distance_km} km, {b.compass} ({b.bearing_deg}°)
                  </li>
                ))}
              </ul>
              {data && (
                <div className="mt-3">
                  <SourceChip
                    dataset={`ORCA thermal-front proxy — ${data.orca_metadata.applies_to_sector}`}
                    acquisitionTimestamp={data.orca_metadata.generated_at}
                    confidenceTier="LOW_DATA"
                  />
                </div>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
