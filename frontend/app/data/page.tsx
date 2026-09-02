"use client";

import { useEffect, useState } from "react";
import { Card } from "../components/Card";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type DataSource = {
  id: string;
  dataset: string;
  authority_tier: "TIER1" | "TIER2" | "TIER3";
  typical_freshness_minutes: number;
  covers: string[];
};

// Data (§4.2 `/data`): catalog browser, source metadata (plan §4 S4 Day 3 —
// Agent 3's registry). Export/API-access and the click-through provenance
// popover are Phase 2 (plan §4 S4 Day 4 note); this is the browsing surface.
export default function DataPage() {
  const [sources, setSources] = useState<DataSource[] | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/sources`)
      .then((r) => r.json())
      .then((d) => setSources(d.sources))
      .catch(() => setSources([]));
  }, []);

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold mb-4">Data</h1>
      <p className="mb-4 text-sm text-black/50">
        Every source ORCA can cite, with its authority tier and typical freshness. CSV/NetCDF export and
        per-query provenance drill-down land in Phase 2.
      </p>

      {sources === null && <p className="text-sm text-black/50">Loading…</p>}
      {sources?.length === 0 && <p className="text-sm text-black/50">Could not reach the ORCA API.</p>}

      <ul className="flex flex-col gap-2">
        {sources?.map((s) => (
          <li key={s.id}>
            <Card>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{s.dataset}</span>
                <span className="text-xs text-black/50">{s.authority_tier.replace("TIER", "Tier ")}</span>
              </div>
              <p className="mt-1 text-xs text-black/50">
                Covers: {s.covers.join(", ")} · typical freshness {s.typical_freshness_minutes} min
              </p>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
