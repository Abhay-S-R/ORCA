// Provisional ChartSpec — D2's local shape for the four §5.9 chart types.
//
// The FROZEN ChartSpec contract is D3's to publish (Phase 2 plan §4.1:
// "MapLayer + ChartSpec — exactly the §5.9 field lists ... Owner D3"). Until
// that lands on `main`, the D2 chart wrappers and the /trends surface speak
// this local type. When D3 ships the real one, this file is deleted and the
// import path swings over — the wrapper props were chosen to match the §5.9
// field names so that swap is mechanical.

export type ChartKind = "time_series" | "bar" | "radar" | "wind_rose";

export type ChartSeries = {
  key: string;
  label: string;
  color?: string;
};

export type ChartSpec = {
  kind: ChartKind;
  title: string;
  x_key: string;
  x_label?: string;
  y_label?: string;
  series: ChartSeries[];
  data: Array<Record<string, number | string | null>>;
  // time_series only: shaded ±2σ anomaly band, [low, high] in y units
  anomaly_band?: { from: number; to: number } | null;
  provenance?: {
    dataset: string;
    acquisition_timestamp: string;
    freshness_minutes?: number;
    confidence_tier?: "HIGH" | "MEDIUM" | "LOW_DATA";
  };
};

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
