"use client";

// Trends (§4.2 `/trends`) — PS #3 (the tide axis) and PS #7 (why has catch
// declined). Driven by Agent 5 (Ocean Analytics). Charts arrive as
// frozen-contract ChartSpec objects; the catch-decline workspace is the
// point — it shows the recorded series, the ±2σ band, the year-on-year move,
// and the factors it can and cannot corroborate ("correlated with", never
// "caused by", "insufficient data" where ORCA has no independent measurement).
import { useEffect, useState } from "react";
import { LineChart, Wind } from "lucide-react";
import { Badge } from "../components/Badge";
import { Chart } from "../components/charts";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { type SourceSelection } from "../components/SourceNarration";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import type { ChartSpec } from "../lib/chartSpec";
import { ageLabel, type Recency } from "../lib/recency";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Confidence = { score: "HIGH" | "MEDIUM" | "LOW_DATA"; rationale: string };
type Factor = { factor: string; year: number | null; relationship: string; evidence: string };

type TrendsResponse = {
  chart_specs: ChartSpec[];
  catch_baseline: {
    label: string;
    mean_tonnes: number;
    std_tonnes: number;
    band_low: number;
    band_high: number;
  } | null;
  catch_decline: {
    district: string;
    verdict: string;
    year_on_year_pct?: number;
    declined?: boolean;
    factors?: Factor[];
    confidence: Confidence;
    detail?: string;
    // Present only on the CMFRI state-estimate fallback, when the district
    // itself has fewer than 3 years on record.
    state?: string;
    landings_tonnes?: number;
    year?: string | number;
    cmfri_note?: string;
    citation?: string;
  };
  // Which Census-2011 district the position falls in — null offshore, which
  // is a real answer, not a lookup failure.
  district_context: {
    district: string | null; state?: string; censuscode?: number;
    dataset: string; source_file: string; note?: string;
  } | null;
  sst_chlorophyll_correlation: {
    available: boolean;
    note?: string;
    pearson_r?: number;
    relationship?: string;
    n_samples?: number;
    acquisition_gap?: string | null;
    chl_provenance?: ({ dataset?: string; acquisition_timestamp?: string } & Recency) | null;
    sst_provenance?: ({ dataset?: string; acquisition_timestamp?: string } & Recency) | null;
    confidence: Confidence;
  };
  // PS #7's word "anomaly" needs a reference period. `available: false`
  // means ORCA holds no ERA5 baseline for this coast — a stated gap, never
  // a silent "nothing unusual".
  wind_anomaly: {
    available: boolean;
    note?: string;
    nearest_port?: string;
    variable?: string;
    units?: string;
    observed_peak?: number;
    baseline_mean?: number;
    baseline_std?: number;
    baseline_label?: string;
    z?: number;
    anomalous?: boolean;
    direction?: string;
    confidence: Confidence;
  };
  source_selection: SourceSelection | null;
};

const CHART_TITLES: Record<string, string> = {
  tide_height: "Predicted tide height",
  catch_landings: "Marine fish landings",
  wind_rose: "Wind rose",
};

// One granule's age caveat, or nothing while it is within its fresh band.
function GranuleAge({
  label,
  prov,
}: {
  label: string;
  prov: ({ acquisition_timestamp?: string } & Recency) | null | undefined;
}) {
  if (!prov) return null;
  const text = ageLabel(prov.acquisition_timestamp?.slice(0, 10), prov);
  if (!text) return null;
  return (
    <p className="text-[11px] text-caution">
      {label} {text}
      {prov.band === "history" ? " — reference only, not a current reading" : ""}
    </p>
  );
}

export default function TrendsPage() {
  const [data, setData] = useState<TrendsResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/trends`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError(true));
  }, []);

  const band = data?.catch_baseline
    ? { from: data.catch_baseline.band_low, to: data.catch_baseline.band_high, label: data.catch_baseline.label }
    : null;

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="Trends"
        lede="Tide over the coming days, the wind rose for the pilot port, and the catch-decline analysis for the pilot district."
      />

      {error && (
        <ErrorState
          title="Could not reach the Sagar Sarathi API"
          body="The trends service did not respond. Start the backend, then reload this page."
        />
      )}

      {!data && !error && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {data && (
        <div className="flex flex-col gap-4">
          {data.chart_specs.map((spec) => (
            <Chart
              key={spec.chart_id}
              spec={spec}
              title={CHART_TITLES[spec.chart_id] ?? spec.chart_id}
              band={spec.chart_id === "catch_landings" ? band : null}
            />
          ))}

          {/* Catch-decline workspace */}
          <Panel
            title={`Catch decline — ${data.catch_decline.district}`}
            action={
              typeof data.catch_decline.year_on_year_pct === "number" ? (
                <Badge tone={data.catch_decline.declined ? "caution" : "neutral"}>
                  {data.catch_decline.year_on_year_pct > 0 ? "+" : ""}
                  {data.catch_decline.year_on_year_pct}% YoY
                </Badge>
              ) : null
            }
          >
            {/* How a lat/lon became this district — Census 2011 polygons. */}
            {data.district_context && (
              <p className="mb-2 text-[11px] text-ink-dim">
                {data.district_context.district
                  ? `Position falls in ${data.district_context.district}, ${data.district_context.state} ` +
                    `(census code ${data.district_context.censuscode}) — ${data.district_context.dataset}`
                  : `${data.district_context.note} — ${data.district_context.dataset}`}
              </p>
            )}
            <p className="text-sm text-ink-muted">{data.catch_decline.verdict}</p>
            {data.catch_decline.detail && (
              <p className="mt-1 text-xs text-ink-dim">{data.catch_decline.detail}</p>
            )}
            <div className="mt-3">
              <ConfidenceMeter tier={data.catch_decline.confidence.score} />
            </div>

            {data.catch_decline.factors && data.catch_decline.factors.length > 0 && (
              <ul className="mt-4 flex flex-col gap-2 border-t border-hairline pt-3">
                {data.catch_decline.factors.map((f, i) => (
                  <li key={i} className="text-sm">
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="text-ink">{f.factor}</span>
                      <Badge tone={f.relationship === "insufficient data" ? "caution" : "neutral"}>
                        {f.relationship}
                      </Badge>
                    </span>
                    <p className="mt-0.5 text-[11px] text-ink-dim">{f.evidence}</p>
                  </li>
                ))}
              </ul>
            )}

            {/* CMFRI's own caveat on the state estimate, plus the booklet it
                came from — a single-year state number must never read as a
                district trend. */}
            {(data.catch_decline.cmfri_note || data.catch_decline.citation) && (
              <div className="mt-3 border-t border-hairline pt-2 text-[11px] text-ink-dim">
                {data.catch_decline.cmfri_note && <p>{data.catch_decline.cmfri_note}</p>}
                {data.catch_decline.citation && (
                  <p className="mt-1">Source: {data.catch_decline.citation}</p>
                )}
              </div>
            )}
          </Panel>

          {/* SST / chlorophyll correlation — the D3 seam */}
          <Panel title="SST × chlorophyll correlation">
            {data.sst_chlorophyll_correlation.available ? (
              <>
                <ReadoutGrid cols={3}>
                  <Readout label="Pearson r" value={data.sst_chlorophyll_correlation.pearson_r ?? "—"} />
                  <Readout label="Relationship" value={data.sst_chlorophyll_correlation.relationship ?? "—"} />
                  <Readout
                    label="Co-located cells"
                    value={data.sst_chlorophyll_correlation.n_samples ?? "—"}
                    hint="0.25° grid"
                  />
                </ReadoutGrid>
                {/* The two granules need not be simultaneous; saying so is the
                    difference between an association and an implied cause. */}
                {data.sst_chlorophyll_correlation.acquisition_gap && (
                  <p className="mt-2 text-[11px] text-ink-dim">
                    {data.sst_chlorophyll_correlation.acquisition_gap}
                  </p>
                )}
                <p className="mt-2 border-t border-hairline pt-2 text-[11px] text-ink-dim">
                  SST: {data.sst_chlorophyll_correlation.sst_provenance?.dataset ?? "—"} · Chlorophyll:{" "}
                  {data.sst_chlorophyll_correlation.chl_provenance?.dataset ?? "—"}
                </p>
                {/* Stale-data policy: each granule keeps its own age — the SST
                    archive and the chlorophyll archive do not always lag by
                    the same amount, so one combined caveat would hide which
                    side is actually old. */}
                <GranuleAge label="SST" prov={data.sst_chlorophyll_correlation.sst_provenance} />
                <GranuleAge label="Chlorophyll" prov={data.sst_chlorophyll_correlation.chl_provenance} />
              </>
            ) : (
              <EmptyState
                icon={<LineChart className="size-5" />}
                title="Awaiting the gridded ocean series"
                body={
                  data.sst_chlorophyll_correlation.note ??
                  "The SST and chlorophyll grids this analysis needs are not available yet."
                }
              />
            )}
            <div className="mt-3">
              <ConfidenceMeter tier={data.sst_chlorophyll_correlation.confidence.score} />
            </div>
          </Panel>
          {/* Wind anomaly — observed peak against the ERA5 reference period */}
          <Panel title="Wind anomaly vs reference period">
            {data.wind_anomaly.available ? (
              <>
                <ReadoutGrid cols={3}>
                  <Readout
                    label="Observed peak"
                    value={data.wind_anomaly.observed_peak ?? "—"}
                    unit={data.wind_anomaly.units}
                  />
                  <Readout
                    label="Baseline mean"
                    value={data.wind_anomaly.baseline_mean ?? "—"}
                    unit={data.wind_anomaly.units}
                    hint={`σ ${data.wind_anomaly.baseline_std ?? "—"}`}
                  />
                  <Readout label="z-score" value={data.wind_anomaly.z ?? "—"} />
                </ReadoutGrid>
                <p className="mt-3 flex items-baseline justify-between gap-3 text-sm">
                  <span className="text-ink">
                    {data.wind_anomaly.anomalous
                      ? `Unusual — ${data.wind_anomaly.direction} the reference period`
                      : "Within the reference period"}
                  </span>
                  <Badge tone={data.wind_anomaly.anomalous ? "caution" : "neutral"}>
                    {data.wind_anomaly.anomalous ? "anomalous" : "normal"}
                  </Badge>
                </p>
                {/* The baseline is a month, not a climatology. Saying which
                    is the difference between "unusual for the last month"
                    and "unusual for this time of year". */}
                <p className="mt-1 text-[11px] text-ink-dim">
                  {data.wind_anomaly.baseline_label}
                  {data.wind_anomaly.nearest_port ? ` · ${data.wind_anomaly.nearest_port}` : ""}
                </p>
              </>
            ) : (
              <EmptyState
                icon={<Wind className="size-5" />}
                title="No reference period for this coast"
                body={
                  data.wind_anomaly.note ??
                  "Sagar Sarathi holds no ERA5 baseline here, so it will not call anything anomalous."
                }
              />
            )}
            <div className="mt-3">
              <ConfidenceMeter tier={data.wind_anomaly.confidence.score} />
            </div>
          </Panel>

          {/* uncomment this for the footnote lol 
          {data.source_selection && <SourceNarration selection={data.source_selection} />} */}

        </div>
      )}
    </PageBody>
  );
}
