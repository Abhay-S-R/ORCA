"use client";

// Data (§4.2 `/data`) — the catalogue of everything ORCA is allowed to cite.
// Its job is to make "where did that number come from" answerable without
// asking anyone, which is the whole provenance argument made browsable.
import { useEffect, useState } from "react";
import { Badge } from "../components/Badge";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { ErrorState, Skeleton } from "../components/States";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type DataSource = {
  id: string;
  dataset: string;
  authority_tier: "TIER1" | "TIER2" | "TIER3";
  typical_freshness_minutes: number;
  covers: string[];
};

// Tier is an authority ranking, so it renders as a rank, not as a severity —
// using the safety triad here would imply a Tier 3 source is dangerous.
const TIER_LABEL: Record<DataSource["authority_tier"], string> = {
  TIER1: "Tier 1 · official",
  TIER2: "Tier 2 · institutional",
  TIER3: "Tier 3 · derived",
};

export default function DataPage() {
  const [sources, setSources] = useState<DataSource[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/sources`)
      .then((r) => r.json())
      .then((d) => setSources(d.sources))
      .catch(() => setError(true));
  }, []);

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="Data sources"
        lede="Every dataset ORCA can cite, its authority tier, and how fresh it typically is. Export and per-query drill-down land in Phase 2."
      />

      {error && (
        <ErrorState
          title="Could not reach the ORCA API"
          body="The catalogue service did not respond. Start the backend, then reload this page."
        />
      )}

      {!sources && !error && (
        <div className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      <ul className="flex flex-col gap-2">
        {sources?.map((s) => (
          <li key={s.id}>
            <Panel dense>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-medium text-ink">{s.dataset}</span>
                <Badge tone="neutral">{TIER_LABEL[s.authority_tier]}</Badge>
              </div>
              <p className="mt-1.5 text-xs text-ink-dim">
                Covers {s.covers.join(", ")} ·{" "}
                {/* Zero does not mean "refreshed every 0 minutes" — GEBCO, WDPA
                    and the VLIZ EEZ set are static reference geometry. */}
                {s.typical_freshness_minutes === 0 ? (
                  "static reference dataset"
                ) : (
                  <>
                    refreshed roughly every <span data-readout>{s.typical_freshness_minutes}</span> min
                  </>
                )}
              </p>
            </Panel>
          </li>
        ))}
      </ul>
    </PageBody>
  );
}
