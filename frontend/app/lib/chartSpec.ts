// TypeScript mirror of the frozen `ChartSpec` contract — D3 owns it in
// `backend/orca/contracts.py` (plan §5.9 / §4.1), this is the read-only
// shadow the frontend charts consume. Keep the field names identical to the
// dataclass so a payload from Agent 8's `generate_chart_specs` and one hand-
// built by the `/trends` surface are the same shape.
//
// `SourceProvenance` is mirrored here too rather than pulled from a shared
// file — the codebase keeps contract types inline per component (see
// MapView.tsx), and this is the one place charts need it.

export type SourceProvenance = {
  dataset: string;
  acquisition_timestamp: string;
  freshness_minutes: number;
};

export type ChartType = "TimeSeries" | "BarChart" | "RadarChart" | "WindRose";

export type ChartSpec = {
  chart_id: string;
  chart_type: ChartType;
  series: Array<Record<string, number | string | null>>; // recharts-ready rows
  x_key: string;
  y_keys: string[];
  unit: string;
  persona_visibility: string[]; // empty = all personas
  source_provenance: SourceProvenance[];
};

// The ±2σ anomaly band the `/trends` surface draws behind a TimeSeries
// (plan §4 D2 Day 12). Deliberately NOT a ChartSpec field: the frozen
// contract has no slot for it and it is D2's surface concern, passed to the
// wrapper alongside the spec.
export type AnomalyBand = { from: number; to: number; label?: string };

// One shared categorical ramp so every chart in the product reads as one
// system. Cool instrument tones — never the safety triad, which is reserved
// for hazard state (Ground Rule 3).
export const SERIES_COLORS = [
  "#7fd4e8", // confidence-high cyan
  "#9aa8d8", // periwinkle
  "#b08cc4", // muted plum
  "#22617f", // shoal
] as const;

export const AXIS_COLOR = "#64879a"; // --color-ink-dim
export const GRID_COLOR = "#17384c"; // --color-hairline
export const BAND_COLOR = "#164861"; // --color-shelf-3

// Human labels for the raw y_keys the backend emits.
export const Y_KEY_LABELS: Record<string, string> = {
  height_m: "Tide height",
  total_tonnes: "Total landings",
  wave_height_m: "Wave height",
  wind_speed_ms: "Wind speed",
  calm_0_5: "0–5 m/s",
  moderate_5_10: "5–10 m/s",
  strong_10_plus: "10+ m/s",
};
