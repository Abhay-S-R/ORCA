"use client";

// Trends (§4.2 `/trends`) — PS #3 (the tide axis) and PS #7 (why has catch
// declined). Driven by Agent 5 (Ocean Analytics). The catch-decline workspace
// is the point: it shows the recorded series, the year-on-year move, and the
// factors it can and cannot corroborate — "correlated with", never "caused
// by", and "insufficient data" where ORCA has no independent measurement.
import { useEffect, useState } from "react";
import { LineChart } from "lucide-react";
import { Badge } from "../components/Badge";
import { Chart } from "../components/charts";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceNarration, type SourceSelection } from "../components/SourceNarration";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import type { ChartSpec } from "../lib/chartSpec";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Confidence = { score: "HIGH" | "MEDIUM" | "LOW_DATA"; rationale: string };
type Factor = { factor: string; year: number | null; relationship: string; evidence: string };

type TrendsResponse = {
  tide_series: Array<{ t: string; height_m: number; event: string }>;
  catch_decline: {
    district: string;
    verdict: string;
    year_on_year_pct?: number;
    declined?: boolean;
    series?: Array<{ year: number; total_tonnes: number; trend: string; z: number | null; anomalous: boolean }>;
    baseline?: {
      label: string;
      mean_tonnes: number;
      std_tonnes: number;
      band_low: number;
      band_high: number;
    };
    factors?: Factor[];
    confidence: Confidence;
    detail?: string;
  };
  sst_chlorophyll_correlation: {
    available: boolean;
    note?: string;
    pearson_r?: number;
    relationship?: string;
    confidence: Confidence;
  };
  wind_rose: {
    available: boolean;
    note?: string;
    port?: string;
    hours_counted?: number;
    bins?: string[];
    petals?: Array<Record<string, string | number>>;
    dataset?: string;
    confidence: Confidence;
  };
  source_selection: SourceSelection | null;
};

const WIND_BIN_LABEL: Record<string, string> = {
  calm_0_5: "0–5 m/s",
  moderate_5_10: "5–10 m/s",
  strong_10_plus: "10+ m/s",
};

function shortDay(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
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

  const tideSpec: ChartSpec | null = data
    ? {
        kind: "time_series",
        title: "Predicted tide height",
        x_key: "day",
        y_label: "m above chart datum",
        series: [{ key: "height_m", label: "Tide height" }],
        data: data.tide_series.map((e) => ({ day: shortDay(e.t), height_m: e.height_m })),
      }
    : null;

  // Landings as a time series so the ±2σ anomaly band can be drawn behind it
  // — a band is a statement about a trend, and a bar chart has no trend line
  // to state it against.
  const catchSpec: ChartSpec | null =
    data?.catch_decline.series && data.catch_decline.series.length > 0
      ? {
          kind: "time_series",
          title: `Marine fish landings — ${data.catch_decline.district}`,
          x_key: "year",
          y_label: `tonnes · band = ${data.catch_decline.baseline?.label ?? "baseline"}`,
          series: [{ key: "total_tonnes", label: "Total landings" }],
          data: data.catch_decline.series.map((r) => ({ year: String(r.year), total_tonnes: r.total_tonnes })),
          anomaly_band: data.catch_decline.baseline
            ? { from: data.catch_decline.baseline.band_low, to: data.catch_decline.baseline.band_high }
            : null,
        }
      : null;

  const windSpec: ChartSpec | null =
    data?.wind_rose.available && data.wind_rose.petals
      ? {
          kind: "wind_rose",
          title: `Wind rose — ${data.wind_rose.port ?? "pilot port"}`,
          x_key: "compass",
          y_label: `${data.wind_rose.hours_counted} forecast hours`,
          series: (data.wind_rose.bins ?? []).map((b) => ({ key: b, label: WIND_BIN_LABEL[b] ?? b })),
          data: data.wind_rose.petals,
          provenance: data.wind_rose.dataset
            ? {
                dataset: data.wind_rose.dataset,
                acquisition_timestamp: "",
                confidence_tier: data.wind_rose.confidence.score,
              }
            : undefined,
        }
      : null;

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="Trends"
        lede="Tide over the coming days, and the catch-decline analysis for the pilot district."
      />

      {error && (
        <ErrorState
          title="Could not reach the ORCA API"
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
          {tideSpec && tideSpec.data.length > 0 && <Chart spec={tideSpec} />}

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
          </Panel>

          {catchSpec && <Chart spec={catchSpec} />}

          {windSpec && <Chart spec={windSpec} />}

          {/* SST / chlorophyll correlation — the D3 seam */}
          <Panel title="SST × chlorophyll correlation">
            {data.sst_chlorophyll_correlation.available ? (
              <ReadoutGrid cols={2}>
                <Readout label="Pearson r" value={data.sst_chlorophyll_correlation.pearson_r ?? "—"} />
                <Readout label="Relationship" value={data.sst_chlorophyll_correlation.relationship ?? "—"} />
              </ReadoutGrid>
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

          {data.source_selection && <SourceNarration selection={data.source_selection} />}
        </div>
      )}
    </PageBody>
  );
}
