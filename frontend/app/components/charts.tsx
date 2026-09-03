"use client";

// The four §5.9 chart wrappers (Phase 2 plan §4 D2): TimeSeries, Bar, Radar,
// WindRose. Every one takes a ChartSpec and nothing else — the surface
// decides what to plot, the wrapper only knows how ORCA charts look.
//
// Shared rules, enforced here once:
//   - dark instrument palette, cool categorical ramp, never the safety triad
//   - axis/grid in hairline tones so the data line is the loudest thing
//   - a ChartFrame with the title + a provenance chip, because a chart is a
//     number too and exit criterion 4 applies to it
//   - responsive: the container scrolls its parent, never the page body
import {
  Bar,
  BarChart as RBarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart as RRadarChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AXIS_COLOR, BAND_COLOR, GRID_COLOR, SERIES_COLORS, type ChartSpec } from "../lib/chartSpec";
import { SourceChip } from "./SourceChip";

const TOOLTIP_STYLE = {
  background: "var(--color-shelf-1)",
  border: "1px solid var(--color-hairline-strong)",
  borderRadius: "6px",
  fontSize: "12px",
  color: "var(--color-ink)",
} as const;

function colorFor(spec: ChartSpec, i: number): string {
  return spec.series[i]?.color ?? SERIES_COLORS[i % SERIES_COLORS.length];
}

function ChartFrame({ spec, children }: { spec: ChartSpec; children: React.ReactNode }) {
  return (
    <figure className="glass rounded-md p-4">
      <figcaption className="mb-3 flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold text-ink">{spec.title}</span>
        {spec.y_label && <span className="text-[11px] text-ink-dim">{spec.y_label}</span>}
      </figcaption>
      <div className="h-64 w-full overflow-x-auto">
        <ResponsiveContainer width="100%" height="100%" minWidth={280}>
          {children}
        </ResponsiveContainer>
      </div>
      {spec.provenance && (
        <div className="mt-3">
          <SourceChip
            dataset={spec.provenance.dataset}
            acquisitionTimestamp={spec.provenance.acquisition_timestamp}
            freshnessMinutes={spec.provenance.freshness_minutes}
            confidenceTier={spec.provenance.confidence_tier}
          />
        </div>
      )}
    </figure>
  );
}

const AXIS_PROPS = {
  stroke: AXIS_COLOR,
  tick: { fill: AXIS_COLOR, fontSize: 11 },
  tickLine: { stroke: GRID_COLOR },
  axisLine: { stroke: GRID_COLOR },
} as const;

export function TimeSeriesChart({ spec }: { spec: ChartSpec }) {
  return (
    <ChartFrame spec={spec}>
      <LineChart data={spec.data} margin={{ top: 6, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID_COLOR} strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey={spec.x_key} {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} width={40} />
        {spec.anomaly_band && (
          <ReferenceArea
            y1={spec.anomaly_band.from}
            y2={spec.anomaly_band.to}
            fill={BAND_COLOR}
            fillOpacity={0.35}
            ifOverflow="extendDomain"
          />
        )}
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: AXIS_COLOR }} />
        {spec.series.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: AXIS_COLOR }} />}
        {spec.series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={colorFor(spec, i)}
            strokeWidth={1.75}
            dot={false}
            activeDot={{ r: 3 }}
            connectNulls={false}
          />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

export function BarChart({ spec }: { spec: ChartSpec }) {
  return (
    <ChartFrame spec={spec}>
      <RBarChart data={spec.data} margin={{ top: 6, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID_COLOR} strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey={spec.x_key} {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} width={40} />
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: AXIS_COLOR }} cursor={{ fill: GRID_COLOR, fillOpacity: 0.3 }} />
        {spec.series.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: AXIS_COLOR }} />}
        {spec.series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={colorFor(spec, i)} radius={[2, 2, 0, 0]} />
        ))}
      </RBarChart>
    </ChartFrame>
  );
}

export function RadarChart({ spec }: { spec: ChartSpec }) {
  return (
    <ChartFrame spec={spec}>
      <RRadarChart data={spec.data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <PolarGrid stroke={GRID_COLOR} />
        <PolarAngleAxis dataKey={spec.x_key} tick={{ fill: AXIS_COLOR, fontSize: 11 }} />
        <PolarRadiusAxis tick={{ fill: AXIS_COLOR, fontSize: 10 }} stroke={GRID_COLOR} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        {spec.series.map((s, i) => (
          <Radar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            stroke={colorFor(spec, i)}
            fill={colorFor(spec, i)}
            fillOpacity={0.25}
          />
        ))}
      </RRadarChart>
    </ChartFrame>
  );
}

// Wind rose — a radar over 16 compass points, one ring per speed bin. The
// spec's series are the speed bins; x_key is the compass column.
export function WindRoseChart({ spec }: { spec: ChartSpec }) {
  return (
    <ChartFrame spec={spec}>
      <RRadarChart data={spec.data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <PolarGrid stroke={GRID_COLOR} />
        <PolarAngleAxis dataKey={spec.x_key} tick={{ fill: AXIS_COLOR, fontSize: 10 }} />
        <PolarRadiusAxis angle={90} tick={{ fill: AXIS_COLOR, fontSize: 10 }} stroke={GRID_COLOR} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 11, color: AXIS_COLOR }} />
        {spec.series.map((s, i) => (
          <Radar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            stroke={colorFor(spec, i)}
            fill={colorFor(spec, i)}
            fillOpacity={0.3}
          />
        ))}
      </RRadarChart>
    </ChartFrame>
  );
}

export function Chart({ spec }: { spec: ChartSpec }) {
  switch (spec.kind) {
    case "bar":
      return <BarChart spec={spec} />;
    case "radar":
      return <RadarChart spec={spec} />;
    case "wind_rose":
      return <WindRoseChart spec={spec} />;
    default:
      return <TimeSeriesChart spec={spec} />;
  }
}
