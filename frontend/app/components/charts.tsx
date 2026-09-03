"use client";

// The four §5.9 chart wrappers (Phase 2 plan §4 D2): one per `chart_type` in
// the frozen ChartSpec contract — TimeSeries, BarChart, RadarChart, WindRose.
// Each takes a ChartSpec (Agent 8's shape, or one the surface hand-built to
// the same shape) plus a display `title`, and — for TimeSeries — an optional
// ±2σ `band`, which is a D2 surface concern the frozen contract has no slot
// for.
//
// Shared rules, enforced here once:
//   - dark instrument palette, cool categorical ramp, never the safety triad
//   - axis/grid in hairline tones so the data line is the loudest thing
//   - a provenance chip under every chart, because a chart is a number too
//     and exit criterion 4 applies to it
//   - responsive: the container scrolls its own overflow, never the page body
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
import {
  AXIS_COLOR,
  BAND_COLOR,
  GRID_COLOR,
  SERIES_COLORS,
  Y_KEY_LABELS,
  type AnomalyBand,
  type ChartSpec,
} from "../lib/chartSpec";
import { SourceChip } from "./SourceChip";

const TOOLTIP_STYLE = {
  background: "var(--color-shelf-1)",
  border: "1px solid var(--color-hairline-strong)",
  borderRadius: "6px",
  fontSize: "12px",
  color: "var(--color-ink)",
} as const;

const AXIS_PROPS = {
  stroke: AXIS_COLOR,
  tick: { fill: AXIS_COLOR, fontSize: 11 },
  tickLine: { stroke: GRID_COLOR },
  axisLine: { stroke: GRID_COLOR },
} as const;

function label(key: string): string {
  return Y_KEY_LABELS[key] ?? key;
}

function color(i: number): string {
  return SERIES_COLORS[i % SERIES_COLORS.length];
}

function ChartFrame({
  title,
  unit,
  provenance,
  children,
}: {
  title: string;
  unit?: string;
  provenance?: ChartSpec["source_provenance"];
  children: React.ReactNode;
}) {
  const p = provenance?.[0];
  return (
    <figure className="glass rounded-md p-4">
      <figcaption className="mb-3 flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold text-ink">{title}</span>
        {unit && <span className="text-[11px] text-ink-dim">{unit}</span>}
      </figcaption>
      <div className="h-64 w-full overflow-x-auto">
        <ResponsiveContainer width="100%" height="100%" minWidth={280}>
          {children}
        </ResponsiveContainer>
      </div>
      {p && (
        <div className="mt-3">
          <SourceChip
            dataset={p.dataset}
            acquisitionTimestamp={p.acquisition_timestamp}
            freshnessMinutes={p.freshness_minutes}
          />
        </div>
      )}
    </figure>
  );
}

export function Chart({
  spec,
  title,
  band,
}: {
  spec: ChartSpec;
  title: string;
  band?: AnomalyBand | null;
}) {
  switch (spec.chart_type) {
    case "BarChart":
      return <BarChartW spec={spec} title={title} />;
    case "RadarChart":
    case "WindRose":
      return <RadarW spec={spec} title={title} />;
    default:
      return <TimeSeriesW spec={spec} title={title} band={band} />;
  }
}

function TimeSeriesW({ spec, title, band }: { spec: ChartSpec; title: string; band?: AnomalyBand | null }) {
  return (
    <ChartFrame title={title} unit={band?.label ?? spec.unit} provenance={spec.source_provenance}>
      <LineChart data={spec.series} margin={{ top: 6, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID_COLOR} strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey={spec.x_key} {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} width={44} />
        {band && (
          <ReferenceArea
            y1={band.from}
            y2={band.to}
            fill={BAND_COLOR}
            fillOpacity={0.35}
            ifOverflow="extendDomain"
          />
        )}
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: AXIS_COLOR }} />
        {spec.y_keys.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: AXIS_COLOR }} />}
        {spec.y_keys.map((key, i) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            name={label(key)}
            stroke={color(i)}
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

function BarChartW({ spec, title }: { spec: ChartSpec; title: string }) {
  return (
    <ChartFrame title={title} unit={spec.unit} provenance={spec.source_provenance}>
      <RBarChart data={spec.series} margin={{ top: 6, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID_COLOR} strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey={spec.x_key} {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} width={44} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelStyle={{ color: AXIS_COLOR }}
          cursor={{ fill: GRID_COLOR, fillOpacity: 0.3 }}
        />
        {spec.y_keys.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: AXIS_COLOR }} />}
        {spec.y_keys.map((key, i) => (
          <Bar key={key} dataKey={key} name={label(key)} fill={color(i)} radius={[2, 2, 0, 0]} />
        ))}
      </RBarChart>
    </ChartFrame>
  );
}

// RadarChart and WindRose share a renderer — a wind rose is a radar over the
// 16 compass points with one ring per speed bin.
function RadarW({ spec, title }: { spec: ChartSpec; title: string }) {
  return (
    <ChartFrame title={title} unit={spec.unit} provenance={spec.source_provenance}>
      <RRadarChart data={spec.series} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <PolarGrid stroke={GRID_COLOR} />
        <PolarAngleAxis dataKey={spec.x_key} tick={{ fill: AXIS_COLOR, fontSize: 10 }} />
        <PolarRadiusAxis angle={90} tick={{ fill: AXIS_COLOR, fontSize: 10 }} stroke={GRID_COLOR} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        {spec.y_keys.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: AXIS_COLOR }} />}
        {spec.y_keys.map((key, i) => (
          <Radar
            key={key}
            dataKey={key}
            name={label(key)}
            stroke={color(i)}
            fill={color(i)}
            fillOpacity={0.28}
          />
        ))}
      </RRadarChart>
    </ChartFrame>
  );
}
