"use client";

// Fishing zones — dashboard pieces (toolbar, KPI strip, map + ranked list,
// zone breakdown). Drop this next to page.tsx. Uses the existing Badge, Skeleton
// and useT, plus the shelf / ink / hairline / go / caution / no-go tokens.

import { useEffect, useMemo, useState } from "react";
import { Anchor, ChevronDown, Compass, Fish, Layers, Sparkles, TrendingUp } from "lucide-react";
import { Badge } from "../components/Badge";
import { Skeleton } from "../components/States";
import { useT } from "../i18n/useT";
import { SatelliteZoneMap } from "./SatelliteZoneMap";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// ─── types ───────────────────────────────────────────────────────────────────

export type PricedSpeciesRow = {
  aphia_id: number;
  common_name: string;
  scientific_name: string;
  share_pct: number;
  est_kg: number;
  price_low: number;
  price_high: number;
  price_mid: number;
  income_mid: number;
};

export type ZoneProfitResult = {
  zone_id: string;
  zone_name: string;
  zone_type: string;
  state: string;
  lat: number;
  lon: number;
  distance_km: number;
  vessel_key: string;
  vessel_label: string;
  show_profit: boolean;
  priced_species: PricedSpeciesRow[];
  income_low: number | null;
  income_high: number | null;
  income_mid: number | null;
  profit_low: number | null;
  profit_high: number | null;
  profit_mid: number | null;
  margin_pct: number | null;
  profit_label: string;
  profit_color: "green" | "orange" | "red" | "neutral";
  fuel_cost: number;
  fuel_liters?: number;
  fuel_burn_lph?: number;
  round_trip_nm?: number;
  fixed_cost: number;
  total_cost: number;
  sort_rank: number;
  limited_data: boolean;
  zone_description: string;
  is_best_zone: boolean;
};

export type ProfitApiResponse = {
  port_id: string;
  port_name: string;
  port_state: string;
  port_lat: number;
  port_lon: number;
  vessel_key: string;
  vessel_label: string;
  show_profit: boolean;
  fallback_message: string | null;
  zones: ZoneProfitResult[];
  speed_kn?: number;
  fuel_burn_lph?: number;
  diesel_price_inr: number;
  disclaimer: string;
};

export type ProfitState = { data: ProfitApiResponse | null; loading: boolean; error: boolean };

type Tone = "go" | "caution" | "no-go" | "neutral";

// ─── helpers ─────────────────────────────────────────────────────────────────

export const VESSEL_OPTIONS = [
  { key: "small_fishing", label: "Small boat" },
  { key: "mechanized_trawler", label: "Trawler" },
  { key: "cargo_vessel", label: "Cargo" },
];

const PIN_HEX: Record<string, string> = {
  green: "#2f7a4f",
  orange: "#b8862e",
  red: "#b3402c",
  neutral: "#2f6f74",
};

export function calculateBearing(lat1: number, lon1: number, lat2: number, lon2: number): { deg: number; compass: string } {
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos((lat2 * Math.PI) / 180);
  const x =
    Math.cos((lat1 * Math.PI) / 180) * Math.sin((lat2 * Math.PI) / 180) -
    Math.sin((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.cos(dLon);
  let brng = (Math.atan2(y, x) * 180) / Math.PI;
  brng = (brng + 360) % 360;
  const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  const compass = dirs[Math.round(brng / 22.5) % 16];
  return { deg: Math.round(brng), compass };
}

const toneOf = (c: string): Tone =>
  c === "green" ? "go" : c === "orange" ? "caution" : c === "red" ? "no-go" : "neutral";

const TONE_TEXT: Record<Tone, string> = {
  go: "text-go",
  caution: "text-caution",
  "no-go": "text-no-go",
  neutral: "text-ink-dim",
};

export const inr = (v: number | null | undefined) => {
  if (v == null) return "—";
  return v < 0 ? `−₹${Math.abs(v).toLocaleString("en-IN")}` : `₹${v.toLocaleString("en-IN")}`;
};

export const inrK = (v: number | null | undefined) => {
  if (v == null) return "—";
  const a = Math.abs(v);
  const s = a >= 1000 ? `${(a / 1000).toFixed(1).replace(/\.0$/, "")}k` : String(a);
  return `${v < 0 ? "−" : ""}₹${s}`;
};

const CARD = "rounded-xl border border-hairline bg-shelf-2/60 p-4";

// ─── data hook ───────────────────────────────────────────────────────────────

export function useFishingProfit(
  lat: number,
  lon: number,
  vessel: string,
  speedKn?: number | null
): ProfitState {
  const [data, setData] = useState<ProfitApiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resetting fetch state when parameters change
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ lat: String(lat), lon: String(lon), vessel });
    if (speedKn != null && speedKn > 0) {
      params.set("speed_kn", String(speedKn));
    }
    fetch(`${API_BASE}/api/fishing-profit?${params.toString()}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((d: ProfitApiResponse) => {
        if (!cancelled) {
          setData(d);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [lat, lon, vessel, speedKn]);

  return { data, loading, error };
}

// ─── 1. toolbar: port + vessel in one row ────────────────────────────────────

type PortLite = { id: string; name: string; state: string };

export function ZonesToolbar({
  ports,
  selectedPortKey,
  onSelectPortKey,
  registeredHomePortName,
  activeVessel,
  onSelectVessel,
  profileVesselLabel,
  isProfileVesselActive,
}: {
  ports: PortLite[];
  currentPort?: PortLite;
  selectedPortKey: string;
  onSelectPortKey: (key: string) => void;
  registeredHomePortName: string | null;
  activeVessel: string;
  onSelectVessel: (key: string) => void;
  profileVesselLabel?: string | null;
  isProfileVesselActive?: boolean;
}) {
  const byState = useMemo(() => {
    const m = new Map<string, PortLite[]>();
    ports.forEach((p) => m.set(p.state, [...(m.get(p.state) ?? []), p]));
    return Array.from(m.entries());
  }, [ports]);

  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2.5">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-ocean-cyan/15 text-ocean-cyan">
          <Anchor className="size-4" aria-hidden="true" />
        </span>
        <div className="relative">
          <label htmlFor="zones-port" className="sr-only">
            Home port
          </label>
          <select
            id="zones-port"
            value={selectedPortKey}
            onChange={(e) => onSelectPortKey(e.target.value)}
            className="cursor-pointer appearance-none rounded-lg border border-hairline bg-shelf-1 py-1.5 pl-3 pr-8 text-xs font-semibold text-ink focus:border-ocean-cyan focus:outline-none focus:ring-1 focus:ring-ocean-cyan"
          >
            <option value="default_home">
              {registeredHomePortName ?? "Kochi"} (profile default)
            </option>
            {byState.map(([state, list]) => (
              <optgroup key={state} label={state}>
                {list.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-dim" />
        </div>
      </div>

      <div className="flex items-center gap-2.5">
        <div
          role="group"
          aria-label="Vessel profile"
          className="inline-flex rounded-lg border border-hairline bg-shelf-1 p-0.5"
        >
          {VESSEL_OPTIONS.map((v) => {
            const on = activeVessel === v.key;
            return (
              <button
                key={v.key}
                type="button"
                aria-pressed={on}
                onClick={() => onSelectVessel(v.key)}
                className={`cursor-pointer rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                  on ? "bg-ocean-cyan font-bold text-black" : "text-ink-muted hover:text-ink"
                }`}
              >
                {v.label}
              </button>
            );
          })}
        </div>
        {profileVesselLabel && (
          <p className="hidden text-[11px] text-ink-dim sm:block">
            {isProfileVesselActive
              ? `From your profile · ${profileVesselLabel}`
              : "Changed for this page only"}
          </p>
        )}
      </div>
    </div>
  );
}

// ─── 2. KPI strip ────────────────────────────────────────────────────────────

function Kpi({
  label,
  value,
  badge,
  tone,
  note,
}: {
  label: string;
  value: string;
  badge: string;
  tone: Tone;
  note?: string;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-hairline bg-shelf-2/60 p-3">
      <p className="text-[11px] text-ink-dim">{label}</p>
      <p className="mt-0.5 truncate text-lg font-semibold leading-tight text-ink" title={value}>
        {value}
      </p>
      <div className="mt-1.5">
        <Badge tone={tone}>{badge}</Badge>
      </div>
      {note && (
        <p className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-ink-dim" title={note}>
          {note}
        </p>
      )}
    </div>
  );
}

export function KpiStrip({
  sector,
  nearest,
  bestZone,
}: {
  sector: { gap: boolean; name: string; message: string };
  nearest: {
    found: boolean;
    label: string | null;
    within: boolean | null;
    beyondReach: boolean;
    zoneName?: string | null;
  };
  bestZone: ZoneProfitResult | null;
  ban?: unknown;
}) {
  const t = useT();

  const nearestBadge = !nearest.found
    ? { text: "None charted", tone: "neutral" as Tone }
    : nearest.within
    ? { text: "Within reach", tone: "go" as Tone }
    : { text: "Beyond day trip", tone: "caution" as Tone };

  // Box 4: Estimated Trip Profit / Net Return (Understandable to fisherman)
  let profitLabel = "Est. Trip Profit";
  let profitValue = "—";
  let profitBadge = "Net return";
  let profitTone: Tone = "neutral";
  let profitNote: string | undefined = undefined;

  if (bestZone) {
    if (bestZone.show_profit) {
      profitValue = `${inrK(bestZone.profit_low)} – ${inrK(bestZone.profit_high)}`;
      const isPositive = bestZone.profit_mid != null && bestZone.profit_mid > 0;
      profitBadge = isPositive ? "High return" : "Low margin";
      profitTone = isPositive ? "go" : "caution";
      profitNote = `Net return after ₹${Math.round(bestZone.fuel_cost / 1000)}k fuel & crew`;
    } else {
      profitLabel = "Est. Fuel Burn";
      profitValue = `${bestZone.fuel_liters ?? "—"} L`;
      profitBadge = "Round trip";
      profitTone = "neutral";
      profitNote = "Estimated voyage consumption";
    }
  }

  return (
    <div className="mb-4 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
      <Kpi
        label={t("zones.yourSector")}
        value={sector.name}
        badge={sector.gap ? t("zones.noAdvisory") : "Active coverage"}
        tone={sector.gap ? "caution" : "go"}
        note={sector.message}
      />
      <Kpi
        label={t("zones.nearestZone")}
        value={nearest.label ?? "—"}
        badge={nearest.zoneName ? nearest.zoneName : nearestBadge.text}
        tone={nearestBadge.tone}
        note={nearest.within ? "Within safe day steaming reach" : "Extended offshore voyage required"}
      />
      <Kpi
        label="Best margin"
        value={bestZone?.margin_pct != null ? `${bestZone.margin_pct}%` : "—"}
        badge={bestZone ? bestZone.zone_name : "No priced zone"}
        tone={bestZone ? toneOf(bestZone.profit_color) : "neutral"}
      />
      <Kpi
        label={profitLabel}
        value={profitValue}
        badge={profitBadge}
        tone={profitTone}
        note={profitNote}
      />
    </div>
  );
}

// ─── 3. map ──────────────────────────────────────────────────────────────────

function ZoneMap({
  data,
  zones,
  selectedId,
  onSelect,
  onSelectPort,
}: {
  data: ProfitApiResponse;
  zones: ZoneProfitResult[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onSelectPort?: (portId: string) => void;
}) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [mapViewMode, setMapViewMode] = useState<"satellite" | "chart">("satellite");

  const W = 560;
  const H = 340;

  const isWestCoast =
    data.port_lon < 77.5 ||
    ["Kerala", "Karnataka", "Goa", "Maharashtra", "Gujarat"].includes(data.port_state);

  // Position departure port along the natural coastline:
  // West coast: land on right (East), vast open sea on left (West) -> port at x ~ 405 (72% of W)
  // East coast: land on left (West), vast open sea on right (East) -> port at x ~ 155 (28% of W)
  const px = isWestCoast ? 405 : 155;

  const latKmPerDeg = 111;
  const centerLat = data.port_lat;
  const lonKmPerDeg = 111 * Math.cos((centerLat * Math.PI) / 180);

  // Compute km offsets relative to departure port
  const deltas = zones.map((z) => ({
    ...z,
    dx_km: (z.lon - data.port_lon) * lonKmPerDeg,
    dy_km: (z.lat - data.port_lat) * latKmPerDeg, // positive = North
  }));

  // Find max extents
  const maxEastWestKm = Math.max(35, ...deltas.map((d) => Math.abs(d.dx_km)));
  const maxNorthKm = Math.max(10, ...deltas.map((d) => Math.max(0, d.dy_km)));
  const maxSouthKm = Math.max(10, ...deltas.map((d) => Math.max(0, -d.dy_km)));
  const totalNorthSouthKm = Math.max(70, maxNorthKm + maxSouthKm);

  // Usable canvas space for sea distribution
  const usableWidthSea = isWestCoast ? px - 45 : W - px - 45;
  const usableHeight = H - 90;

  // Isotropic scale: 1 km East-West = 1 km North-South (eliminates all squashing!)
  const scaleX = usableWidthSea / (maxEastWestKm * 1.15);
  const scaleY = usableHeight / (totalNorthSouthKm * 1.15);
  const scale = Math.min(scaleX, scaleY, 1.75);

  // Port vertical position py based on North-South spread
  const py = Math.max(65, Math.min(H - 65, 45 + maxNorthKm * 1.15 * scale));

  // Projected pixel coordinates
  const rawCoords = deltas.map((d) => ({
    ...d,
    x: px + d.dx_km * scale,
    y: py - d.dy_km * scale, // SVG y is inverted (North is negative y)
  }));

  // Collision separation pass: ensures every numbered pin (1, 2, 3, 4, 5) and port
  // is spaced at least 32px apart, preventing any overlapping or clustering
  const placedZones = rawCoords.map((pt, idx, arr) => {
    let x = pt.x;
    let y = pt.y;

    // Check distance to port
    const dPort = Math.hypot(x - px, y - py);
    if (dPort < 34) {
      const angle = Math.atan2(y - py, x - px);
      x = px + Math.cos(angle) * 36;
      y = py + Math.sin(angle) * 36;
    }

    // Check distance to already placed zones
    for (let j = 0; j < idx; j++) {
      const other = arr[j];
      const dist = Math.hypot(x - other.x, y - other.y);
      if (dist < 34 && dist > 0) {
        const angle = Math.atan2(y - other.y, x - other.x);
        x += Math.cos(angle) * (34 - dist);
        y += Math.sin(angle) * (34 - dist);
      }
    }

    // Clamp inside canvas margins
    x = Math.max(28, Math.min(W - 28, x));
    y = Math.max(28, Math.min(H - 28, y));
    return { ...pt, x, y };
  });

  const maxZoneDist = Math.max(50, ...zones.map((z) => z.distance_km));
  const rings = maxZoneDist > 160 ? [50, 100, 150, 200] : maxZoneDist > 90 ? [50, 100, 150] : [25, 50, 75];

  // Smooth natural coastline
  const coastPath = isWestCoast
    ? `M ${px + 10} 0 Q ${px - 16} ${H * 0.3}, ${px + 6} ${py} T ${px - 10} ${H} L ${W} ${H} L ${W} 0 Z`
    : `M ${px - 10} 0 Q ${px + 16} ${H * 0.3}, ${px - 6} ${py} T ${px + 10} ${H} L 0 ${H} L 0 0 Z`;

  const coastLine = isWestCoast
    ? `M ${px + 10} 0 Q ${px - 16} ${H * 0.3}, ${px + 6} ${py} T ${px - 10} ${H}`
    : `M ${px - 10} 0 Q ${px + 16} ${H * 0.3}, ${px - 6} ${py} T ${px + 10} ${H}`;

  // Currently active zone for the telemetry HUD
  const activeZone =
    zones.find((z) => z.zone_id === (hoveredId ?? selectedId)) ??
    zones.find((z) => z.zone_id === selectedId) ??
    zones.find((z) => z.is_best_zone) ??
    zones[0] ??
    null;

  return (
    <div
      className={`${CARD} flex flex-col p-3.5 gap-2.5`}
      onContextMenu={(e) => e.preventDefault()}
    >
      {/* Header bar with Satellite / Sea Chart toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline/60 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-ocean-cyan/15 text-ocean-cyan">
            <Compass className="size-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-ink">
              Fishing Grounds &amp; Regional Map · {data.port_name}
            </h3>
            <p className="text-[10px] font-mono text-ink-dim">
              {data.port_lat.toFixed(2)}°N, {data.port_lon.toFixed(2)}°E · {data.port_state} Coast
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div
            role="tablist"
            aria-label="Map style"
            className="inline-flex rounded-lg border border-hairline bg-shelf-1 p-0.5"
          >
            <button
              type="button"
              role="tab"
              aria-selected={mapViewMode === "satellite"}
              onClick={() => setMapViewMode("satellite")}
              className={`cursor-pointer rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                mapViewMode === "satellite"
                  ? "bg-ocean-cyan font-bold text-black shadow-xs"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              🛰️ Satellite
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mapViewMode === "chart"}
              onClick={() => setMapViewMode("chart")}
              className={`cursor-pointer rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                mapViewMode === "chart"
                  ? "bg-ocean-cyan font-bold text-black shadow-xs"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              🧭 Sea Chart
            </button>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1 rounded bg-shelf-3 px-2 py-0.5 text-[10px] font-mono text-ink-dim border border-hairline/60">
            <span className="size-1.5 rounded-full bg-ocean-cyan animate-pulse" /> Live Telemetry
          </span>
        </div>
      </div>

      {/* Map View Body */}
      {mapViewMode === "satellite" ? (
        <SatelliteZoneMap
          data={data}
          zones={zones}
          selectedId={selectedId}
          onSelect={onSelect}
          onSelectPort={onSelectPort}
        />
      ) : (
        /* SVG Nautical Chart Frame */
        <div
          className="relative overflow-hidden rounded-xl border border-hairline/80 shadow-inner bg-shelf-1"
          onContextMenu={(e) => e.preventDefault()}
        >
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full select-none"
            role="group"
            aria-label={`Admiralty navigation chart of ${zones.length} fishing grounds near ${data.port_name}`}
            onContextMenu={(e) => e.preventDefault()}
          >
            <defs>
              <filter id="pin-shadow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="1.5" stdDeviation="2" floodColor="#1b2633" floodOpacity="0.22" />
              </filter>
              <linearGradient id="sea-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#eef7f8" stopOpacity="0.95" />
                <stop offset="100%" stopColor="#e2eff1" stopOpacity="0.85" />
              </linearGradient>
              <linearGradient id="land-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#f5eedd" stopOpacity="0.98" />
                <stop offset="100%" stopColor="#ece1c4" stopOpacity="0.95" />
              </linearGradient>
            </defs>

            {/* 1. Sea Water Canvas Base */}
            <rect width={W} height={H} fill="url(#sea-gradient)" />

            {/* 2. Landmass Polygon */}
            <path d={coastPath} fill="url(#land-gradient)" />
            <path d={coastLine} fill="none" stroke="#cfc1a0" strokeWidth="2.5" />
            <path d={coastLine} fill="none" stroke="#8a7f66" strokeWidth="0.8" strokeDasharray="6 3" />

            {/* 3. Sea & Land Watermark Labels */}
            <text
              x={isWestCoast ? 24 : W - 24}
              y={28}
              textAnchor={isWestCoast ? "start" : "end"}
              fontSize="10"
              fontWeight="bold"
              letterSpacing="0.16em"
              fill="#2f6f74"
              fillOpacity="0.28"
            >
              {isWestCoast ? "ARABIAN SEA" : "BAY OF BENGAL"} · CONTINENTAL SHELF
            </text>
            <text
              x={isWestCoast ? W - 18 : 18}
              y={H - 16}
              textAnchor={isWestCoast ? "end" : "start"}
              fontSize="9"
              fontWeight="bold"
              letterSpacing="0.12em"
              fill="#8c8672"
              fillOpacity="0.75"
            >
              {data.port_state.toUpperCase()} COAST
            </text>

            {/* 4. Bathymetric Shelf Depth Contours & Soundings */}
            {[-55, -115, -185].map((d, idx) => {
              const shift = isWestCoast ? d : -d;
              const contour = isWestCoast
                ? `M ${px + 10 + shift} 0 Q ${px - 14 + shift} ${H * 0.3}, ${px + 8 + shift} ${py} T ${px - 10 + shift} ${H}`
                : `M ${px - 10 + shift} 0 Q ${px + 14 + shift} ${H * 0.3}, ${px - 8 + shift} ${py} T ${px + 10 + shift} ${H}`;
              const labelY = 45 + idx * 80;
              const labelX = px + shift - (isWestCoast ? 8 : -8);
              const depths = ["20m", "50m", "100m shelf"];

              return (
                <g key={`bathy-${idx}`} className="pointer-events-none">
                  <path
                    d={contour}
                    fill="none"
                    stroke="#2f6f74"
                    strokeOpacity={0.15 + idx * 0.05}
                    strokeWidth="0.9"
                    strokeDasharray="2 4"
                  />
                  {labelX > 15 && labelX < W - 25 && (
                    <text
                      x={labelX}
                      y={labelY}
                      fontSize="7.5"
                      fontFamily="monospace"
                      fill="#2f6f74"
                      fillOpacity="0.4"
                      textAnchor={isWestCoast ? "end" : "start"}
                    >
                      ~{depths[idx]}
                    </text>
                  )}
                </g>
              );
            })}

            {/* 5. Radial Distance Rings */}
            {rings.map((km) => {
              const r = km * scale;
              if (r <= 12) return null;
              const angleRad = (isWestCoast ? 200 : -20) * (Math.PI / 180);
              const lx = px + r * Math.cos(angleRad);
              const ly = py + r * Math.sin(angleRad);
              const showLabel = lx > 25 && lx < W - 25 && ly > 20 && ly < H - 20;

              return (
                <g key={`ring-${km}`} className="pointer-events-none">
                  <circle
                    cx={px}
                    cy={py}
                    r={r}
                    fill="none"
                    stroke="#2f6f74"
                    strokeOpacity={km === 50 ? 0.35 : 0.2}
                    strokeWidth={km === 50 ? 1.2 : 0.8}
                    strokeDasharray={km === 50 ? "4 3" : "3 4"}
                  />
                  {showLabel && (
                    <g transform={`translate(${lx}, ${ly})`}>
                      <rect
                        x="-22"
                        y="-7.5"
                        width="44"
                        height="15"
                        rx="3.5"
                        fill="#faf6ea"
                        fillOpacity="0.95"
                        stroke="#2f6f74"
                        strokeOpacity="0.4"
                        strokeWidth="0.8"
                      />
                      <text
                        y="3.5"
                        textAnchor="middle"
                        fontSize="8.5"
                        fontWeight="bold"
                        fontFamily="monospace"
                        fill="#2f6f74"
                      >
                        {km} km
                      </text>
                    </g>
                  )}
                </g>
              );
            })}

            {/* 6. Compass Rose */}
            <g
              transform={`translate(${isWestCoast ? W - 44 : 44}, 44)`}
              className="pointer-events-none select-none opacity-80"
            >
              <circle r="22" fill="none" stroke="#2f6f74" strokeWidth="0.8" strokeOpacity="0.35" />
              <circle r="19" fill="none" stroke="#2f6f74" strokeWidth="0.5" strokeOpacity="0.2" strokeDasharray="1 3" />
              <polygon points="0,-20 4,-5 0,-1" fill="#b3402c" />
              <polygon points="0,-20 -4,-5 0,-1" fill="#8c8672" />
              <polygon points="0,20 4,5 0,1" fill="#2f6f74" />
              <polygon points="0,20 -4,5 0,1" fill="#8c8672" />
              <polygon points="20,0 5,4 1,0" fill="#2f6f74" />
              <polygon points="20,0 5,-4 1,0" fill="#8c8672" />
              <polygon points="-20,0 -5,4 -1,0" fill="#2f6f74" />
              <polygon points="-20,0 -5,-4 -1,0" fill="#8c8672" />
              <text y="-23" textAnchor="middle" fontSize="8.5" fontWeight="bold" fill="#b3402c">
                N
              </text>
              <text x="25" y="3" textAnchor="middle" fontSize="7.5" fontWeight="600" fill="#2f6f74">
                E
              </text>
              <text y="28" textAnchor="middle" fontSize="7.5" fontWeight="600" fill="#2f6f74">
                S
              </text>
              <text x="-25" y="3" textAnchor="middle" fontSize="7.5" fontWeight="600" fill="#2f6f74">
                W
              </text>
            </g>

            {/* 7. Bearing Navigation Tracks */}
            {placedZones.map((z) => {
              const isSel = selectedId === z.zone_id;
              const isHov = hoveredId === z.zone_id;
              const active = isSel || isHov;
              const c = PIN_HEX[z.profit_color] ?? PIN_HEX.neutral;

              return (
                <g key={`v-${z.zone_id}`} className="cursor-pointer" onClick={() => onSelect(z.zone_id)}>
                  {active && (
                    <line
                      x1={px}
                      y1={py}
                      x2={z.x}
                      y2={z.y}
                      stroke={c}
                      strokeWidth={3.5}
                      strokeOpacity={0.3}
                      strokeLinecap="round"
                    />
                  )}
                  <line
                    x1={px}
                    y1={py}
                    x2={z.x}
                    y2={z.y}
                    stroke={c}
                    strokeWidth={active ? 2 : 1}
                    strokeOpacity={active ? 0.95 : 0.35}
                    strokeDasharray={active ? "none" : "4 4"}
                  />
                </g>
              );
            })}

            {/* 8. Departure Home Port Marker */}
            <g transform={`translate(${px}, ${py})`}>
              <circle r="20" fill="#2f6f74" fillOpacity="0.1" />
              <circle r="13" fill="#2f6f74" fillOpacity="0.22" />
              <circle r="7" fill="#1f4d51" stroke="#ffffff" strokeWidth="2" filter="url(#pin-shadow)" />
              <circle r="2.5" fill="#ffffff" />
            </g>
            <g
              transform={`translate(${px + (isWestCoast ? 14 : -14)}, ${py})`}
              className="pointer-events-none select-none"
            >
              <text
                x={isWestCoast ? 2 : -2}
                y="-1"
                textAnchor={isWestCoast ? "start" : "end"}
                fontSize="11"
                fontWeight="bold"
                fill="#0f172a"
              >
                ⚓ {data.port_name}
              </text>
              <text
                x={isWestCoast ? 2 : -2}
                y="11"
                textAnchor={isWestCoast ? "start" : "end"}
                fontSize="8"
                fontWeight="700"
                fontFamily="monospace"
                fill="#0284c7"
                letterSpacing="0.05em"
              >
                DEPARTURE PORT
              </text>
            </g>

            {/* 9. Waypoint Pins 1, 2, 3, 4, 5 (Clean Pins without floating black box tooltip) */}
            {placedZones.map((z, i) => {
              const isSel = selectedId === z.zone_id;
              const isHov = hoveredId === z.zone_id;
              const active = isSel || isHov;
              const c = PIN_HEX[z.profit_color] ?? PIN_HEX.neutral;

              return (
                <g
                  key={z.zone_id}
                  transform={`translate(${z.x}, ${z.y})`}
                  className="cursor-pointer"
                  role="button"
                  tabIndex={0}
                  aria-label={`${z.zone_name}, ${Math.round(z.distance_km)} km`}
                  aria-pressed={isSel}
                  onClick={() => onSelect(z.zone_id)}
                  onMouseEnter={() => setHoveredId(z.zone_id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(z.zone_id);
                    }
                  }}
                >
                  {/* Outer Radar Halo on hover/active */}
                  <circle
                    r={active ? 22 : z.is_best_zone ? 17 : 14}
                    fill={c}
                    fillOpacity={active ? 0.35 : 0.16}
                    stroke={c}
                    strokeOpacity={active ? 0.7 : 0.3}
                    strokeWidth={active ? 1.5 : 1}
                  />

                  {/* Waypoint Circle */}
                  <circle
                    r={active ? 13 : 11.5}
                    fill={c}
                    stroke="#ffffff"
                    strokeWidth="2.5"
                    filter="url(#pin-shadow)"
                  />
                  {/* Clean Prominent Number (1, 2, 3, 4, 5) */}
                  <text
                    y="4"
                    textAnchor="middle"
                    fontSize="11"
                    fontWeight="bold"
                    fontFamily="monospace"
                    fill="#ffffff"
                  >
                    {i + 1}
                  </text>

                  {/* Best Zone Badge - Small & Subtle */}
                  {z.is_best_zone && (
                    <g transform="translate(0, -17)">
                      <rect
                        x="-14"
                        y="-5"
                        width="28"
                        height="10"
                        rx="2.5"
                        fill="#92400e"
                        stroke="#fef3c7"
                        strokeWidth="0.6"
                      />
                      <text
                        y="2.5"
                        textAnchor="middle"
                        fontSize="6.5"
                        fontWeight="bold"
                        fill="#fef3c7"
                        letterSpacing="0.02em"
                      >
                        ★ Best
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      )}

      {/* 10. Selected Ground Quick Telemetry HUD */}
      {activeZone && (
        <div className="rounded-lg border border-hairline/80 bg-shelf-1/90 p-3 shadow-2xs space-y-2">
          {/* Top row: pin number + zone title + indicators, right: status badge */}
          <div className="flex items-center justify-between gap-2.5">
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <span
                className="flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white shadow-xs font-mono"
                style={{ backgroundColor: PIN_HEX[activeZone.profit_color] ?? PIN_HEX.neutral }}
              >
                {zones.findIndex((z) => z.zone_id === activeZone.zone_id) + 1}
              </span>
              <div className="flex items-center gap-2 flex-wrap min-w-0">
                <span className="text-xs sm:text-sm font-bold text-ink">{activeZone.zone_name}</span>
                <span className="rounded bg-shelf-3 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ocean-cyan border border-hairline/60">
                  {Math.round(activeZone.distance_km)} km ·{" "}
                  {calculateBearing(data.port_lat, data.port_lon, activeZone.lat, activeZone.lon).compass}
                </span>
                {activeZone.is_best_zone && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-extrabold text-emerald-700 dark:text-emerald-400 border border-emerald-500/30">
                    <span className="text-amber-500">★</span> Best Zone
                  </span>
                )}
              </div>
            </div>

            <div className="shrink-0">
              <Badge tone={toneOf(activeZone.profit_color)}>{activeZone.profit_label}</Badge>
            </div>
          </div>

          {/* Bottom row: description and trip cost on left, net profit on right */}
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 border-t border-hairline/60 pt-2 text-xs">
            <p className="min-w-0 flex-1 text-[11px] leading-normal text-ink-dim break-words">
              {activeZone.zone_description} · Trip cost: <strong className="font-semibold text-ink">{inr(activeZone.total_cost)}</strong> (fuel + fixed)
            </p>

            {activeZone.show_profit && activeZone.profit_mid != null && (
              <div className="flex items-center gap-1.5 shrink-0 font-mono text-[11px]">
                <span className="text-[10px] uppercase font-bold text-ink-dim">Est. Net Profit:</span>
                <span className="font-bold text-ink">
                  {inrK(activeZone.profit_low ?? 0)} – {inrK(activeZone.profit_high ?? 0)}
                </span>
                {activeZone.margin_pct != null && (
                  <span className="font-semibold text-go">({activeZone.margin_pct}%)</span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── 4. ranked list ──────────────────────────────────────────────────────────

function RankedZoneList({
  zones,
  selectedId,
  onSelect,
  showProfit,
}: {
  zones: ZoneProfitResult[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  showProfit: boolean;
}) {
  return (
    <div
      className={`${CARD} flex flex-col p-0 overflow-hidden`}
      onContextMenu={(e) => e.preventDefault()}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-hairline/60 bg-shelf-1/60">
        <h3 className="text-sm font-bold text-ink flex items-center gap-2">
          <Layers className="size-4 text-ocean-cyan" />
          {showProfit ? "Ranked Fishing Grounds" : "Nearest Fishing Grounds"}
        </h3>
        <span className="text-[11px] font-mono text-ink-dim">{zones.length} Charted</span>
      </div>
      <ul className="flex flex-col divide-y divide-hairline/60">
        {zones.map((z, i) => {
          const sel = selectedId === z.zone_id;
          const tone = toneOf(z.profit_color);
          const c = PIN_HEX[z.profit_color] ?? PIN_HEX.neutral;
          return (
            <li key={z.zone_id}>
              <button
                type="button"
                aria-pressed={sel}
                onClick={() => onSelect(z.zone_id)}
                className={`flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3 text-left transition ${
                  sel
                    ? "bg-ocean-cyan/10 border-l-3 border-ocean-cyan"
                    : "hover:bg-shelf-3/50 border-l-3 border-transparent"
                }`}
              >
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <span
                    className="flex size-6 shrink-0 items-center justify-center rounded-full font-mono text-[11px] font-bold text-white shadow-xs mt-0.5"
                    style={{ backgroundColor: c }}
                  >
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {/* Full zone name displayed without truncation */}
                      <span className="text-sm font-bold text-ink leading-snug break-words">
                        {z.zone_name}
                      </span>
                      {z.is_best_zone && (
                        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-extrabold text-emerald-700 dark:text-emerald-400 border border-emerald-500/30">
                          <span className="text-amber-500">★</span> Best Choice
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-dim">
                      <span className="shrink-0 font-mono font-semibold text-ocean-cyan">
                        {Math.round(z.distance_km)} km
                      </span>
                      <span>·</span>
                      <span className="line-clamp-1">{z.zone_description}</span>
                    </div>
                  </div>
                </div>

                {showProfit && z.profit_label !== "cargo" && (
                  <div className="shrink-0 text-right pl-2">
                    <div className="flex items-center justify-end gap-1.5">
                      {z.margin_pct != null && (
                        <span className="font-mono text-[11px] font-bold text-go">
                          {z.margin_pct}%
                        </span>
                      )}
                      <Badge tone={tone}>{z.profit_label}</Badge>
                    </div>
                    {z.profit_low != null && z.profit_high != null && (
                      <span className={`mt-0.5 block font-mono text-[11px] font-semibold ${TONE_TEXT[tone]}`}>
                        {inrK(z.profit_low)} – {inrK(z.profit_high)}
                      </span>
                    )}
                  </div>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ─── 5. selected zone breakdown ──────────────────────────────────────────────

function LedgerRow({ label, value, strong, className = "" }: { label: string; value: string; strong?: boolean; className?: string }) {
  return (
    <div className={`flex items-center justify-between gap-3 py-1 text-xs ${className}`}>
      <span className={strong ? "font-medium text-ink" : "text-ink-muted"}>{label}</span>
      <span className={`font-mono ${strong ? "font-bold" : "font-semibold text-ink"}`}>{value}</span>
    </div>
  );
}

function ZoneBreakdown({ zone }: { zone: ZoneProfitResult }) {
  const tone = toneOf(zone.profit_color);
  const species = zone.priced_species.slice(0, 6);
  const totalKg = zone.priced_species.reduce((sum, sp) => sum + sp.est_kg, 0);

  return (
    <div className={CARD}>
      {/* Header with Title & Status Badges */}
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-2 border-b border-hairline/60 pb-2.5">
        <div>
          <div className="flex items-center gap-2">
            <Fish className="size-4.5 text-ocean-cyan" />
            <h3 className="text-sm font-bold text-ink">{zone.zone_name} Catch &amp; Profit Breakdown</h3>
          </div>
          <p className="mt-0.5 text-[11px] text-ink-dim">
            {zone.distance_km.toFixed(1)} km from port · {zone.zone_description}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {zone.limited_data && zone.show_profit && <Badge tone="caution">Limited data</Badge>}
          {zone.is_best_zone && zone.show_profit && <Badge tone="go">★ Best Zone for You</Badge>}
          <Badge tone={tone}>{zone.profit_label}</Badge>
        </div>
      </div>

      {!zone.show_profit ? (
        <p className="text-xs text-ink-muted">Profit estimates apply to fishing vessels only.</p>
      ) : species.length === 0 ? (
        <p className="text-xs italic text-ink-muted">Profit not available for this zone — no priced species data.</p>
      ) : (
        <>
          {/* Top Banner: Prominent Low & High Approximate Profit Per Trip */}
          {zone.profit_low != null && zone.profit_high != null && (
            <div className="mb-4 rounded-xl border border-hairline/80 bg-shelf-1/90 p-3.5 shadow-xs">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-dim">
                    Approximate profit per trip
                  </span>
                  <div className="flex items-baseline gap-2 mt-0.5">
                    <span className={`text-xl font-bold font-mono ${TONE_TEXT[tone]}`}>
                      {inr(zone.profit_low)} – {inr(zone.profit_high)}
                    </span>
                    <span className="text-xs text-ink-muted">
                      (Normal day: <strong className="font-mono font-bold text-ink">{zone.profit_mid != null ? inr(zone.profit_mid) : "—"}</strong>)
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {zone.margin_pct != null && (
                    <span className="rounded-md bg-go/15 px-2 py-1 font-mono text-xs font-bold text-go">
                      {zone.margin_pct}% margin
                    </span>
                  )}
                  <Badge tone={tone}>{zone.profit_label}</Badge>
                </div>
              </div>

              {/* Visual Boat Expenses vs Net Sales Kept Progress Bar */}
              <div className="mt-2.5">
                <div className="flex items-center justify-between text-[11px] font-mono text-ink-dim mb-1">
                  <span>Boat expenses: {inr(zone.total_cost)}</span>
                  <span>{zone.margin_pct ?? 0}% of sales kept</span>
                </div>
                <div className="h-2 w-full rounded-full bg-shelf-3/80 overflow-hidden">
                  <div
                    className={`h-2 rounded-full transition-all duration-500 ${
                      zone.profit_color === "green"
                        ? "bg-go"
                        : zone.profit_color === "orange"
                        ? "bg-caution"
                        : "bg-no-go"
                    }`}
                    style={{ width: `${Math.max(10, Math.min(100, zone.margin_pct ?? 50))}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Trip Economics Ledger */}
          {zone.income_low != null && zone.income_high != null && (
            <div className="mb-4 rounded-xl border border-hairline/80 bg-shelf-1/80 p-3.5 shadow-xs">
              <div className="flex items-center justify-between gap-2 mb-3">
                <p className="text-xs font-bold text-ink flex items-center gap-1.5">
                  <TrendingUp className="size-4 text-ocean-cyan" />
                  Estimated Trip Economics
                </p>
                <span className="text-[11px] font-mono text-ink-dim">
                  {Math.round(zone.distance_km * 2)} km round trip
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                {/* 1. Catch Value */}
                <div className="rounded-lg border border-hairline bg-shelf-2/60 p-2.5">
                  <div className="text-[10px] text-ink-dim font-bold uppercase tracking-wider">
                    Expected Catch Value
                  </div>
                  <div className="text-sm font-bold font-mono text-ink mt-1">
                    {inr(zone.income_low)} – {inr(zone.income_high)}
                  </div>
                  <div className="text-[10px] text-ink-muted mt-0.5">
                    Typical day: <strong className="font-mono text-ink">{zone.income_mid != null ? inr(zone.income_mid) : "—"}</strong>
                  </div>
                  <div className="text-[10px] text-ink-dim mt-0.5">Auction landing value</div>
                </div>

                {/* 2. Boat Expenses */}
                <div className="rounded-lg border border-hairline bg-shelf-2/60 p-2.5">
                  <div className="text-[10px] text-ink-dim font-bold uppercase tracking-wider">
                    Trip Operating Costs
                  </div>
                  <div className="text-sm font-bold font-mono text-no-go mt-1">
                    −{inr(zone.total_cost)}
                  </div>
                  <div className="text-[10px] text-ink-muted mt-0.5">
                    Diesel: <strong className="font-mono text-ink">{inr(zone.fuel_cost)}</strong>{zone.fuel_liters != null ? ` (~${zone.fuel_liters} L)` : ""}
                  </div>
                  <div className="text-[10px] text-ink-dim mt-0.5">
                    Ice &amp; Crew provision: <strong className="font-mono text-ink">{inr(zone.fixed_cost)}</strong>
                  </div>
                </div>

                {/* 3. Take-Home Profit */}
                <div className="rounded-lg border border-hairline bg-shelf-2/60 p-2.5">
                  <div className="text-[10px] text-ink-dim font-bold uppercase tracking-wider">
                    Net Return to Boat
                  </div>
                  <div className={`text-sm font-bold font-mono mt-1 ${TONE_TEXT[tone]}`}>
                    {inr(zone.profit_low)} – {inr(zone.profit_high)}
                  </div>
                  <div className="text-[10px] text-ink-muted mt-0.5">
                    Expected net: <strong className="font-mono text-ink">{zone.profit_mid != null ? inr(zone.profit_mid) : "—"}</strong>
                  </div>
                  <div className="text-[10px] text-ink-dim mt-0.5">
                    {zone.margin_pct != null ? `${zone.margin_pct}% kept after trip costs` : "Clear profit after costs"}
                  </div>
                </div>
              </div>

              <div className="text-[11px] text-ink-muted mt-2.5 pt-2 border-t border-hairline/60">
                Net return is what you take home after paying <strong>{inr(zone.fuel_cost)}</strong> for diesel and <strong>{inr(zone.fixed_cost)}</strong> for crew, ice and landing fees.
              </div>

              {/* Formula: How Trip Economics is Calculated */}
              <div className="mt-3 rounded-lg border border-hairline/80 bg-shelf-2/50 p-3 text-xs">
                <div className="flex items-center gap-1.5 font-semibold text-ink mb-2">
                  <span className="text-ocean-cyan">📐</span>
                  <span>Calculation Formula:</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
                  <div className="rounded border border-hairline/60 bg-shelf-1/80 p-2">
                    <span className="text-[10px] font-bold uppercase text-ink-dim block">Expected Catch Value</span>
                    <span className="font-mono text-ink text-[11px] mt-0.5 block">Catch Weight (kg) × Auction Price (₹/kg)</span>
                  </div>
                  <div className="rounded border border-hairline/60 bg-shelf-1/80 p-2">
                    <span className="text-[10px] font-bold uppercase text-ink-dim block">Trip Operating Costs</span>
                    <span className="font-mono text-ink text-[11px] mt-0.5 block">Diesel (L × ₹/L) + Ice, Crew &amp; Port Fees</span>
                  </div>
                  <div className="rounded border border-hairline/60 bg-shelf-1/80 p-2">
                    <span className="text-[10px] font-bold uppercase text-go block">Net Return to Boat</span>
                    <span className="font-mono text-go font-semibold text-[11px] mt-0.5 block">Expected Catch Value − Operating Costs</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="grid gap-5 lg:grid-cols-2">
            {/* Left: Expected Catch Share */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-dim">
                  Expected Catch Share (Estimated trip landing)
                </p>
                <span className="text-[10px] font-mono text-ink-dim">CMFRI Landings Model</span>
              </div>
              <ul className="flex flex-col gap-2.5 rounded-lg border border-hairline/60 bg-shelf-1/60 p-3">
                {species.map((sp) => (
                  <li key={sp.aphia_id}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="truncate font-medium text-ink">{sp.common_name}</span>
                      <div className="flex items-center gap-2 font-mono text-[11px]">
                        <span className="text-ink-dim">{sp.est_kg} kg</span>
                        <span className="font-bold text-ink">{sp.share_pct}%</span>
                      </div>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-shelf-3/80">
                      <div
                        className="h-1.5 rounded-full bg-ocean-cyan"
                        style={{ width: `${Math.max(2, Math.min(100, sp.share_pct))}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            {/* Right: Itemized Trip Ledger & Low-High Breakdown */}
            <div className="flex flex-col gap-3">
              {/* Gross Income Range */}
              {zone.income_low != null && zone.income_high != null && (
                <div className="rounded-lg border border-hairline/80 bg-shelf-1/70 p-3">
                  <div className="mb-1.5 flex items-center justify-between">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-dim">
                      1. Gross Fish Value (Before Costs)
                    </p>
                    <span className="text-[10px] font-mono text-ink-dim">Auction vs Retail</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="rounded border border-hairline/60 bg-shelf-2/60 p-1.5">
                      <span className="block text-[10px] text-ink-dim">Low (Harbor glut)</span>
                      <span className="font-mono text-xs font-semibold text-ink">{inr(zone.income_low)}</span>
                    </div>
                    <div className="rounded border border-ocean-cyan/30 bg-ocean-cyan/10 p-1.5">
                      <span className="block text-[10px] font-semibold text-ocean-cyan">Mid (Normal market)</span>
                      <span className="font-mono text-xs font-bold text-ink">
                        {zone.income_mid != null ? inr(zone.income_mid) : "—"}
                      </span>
                    </div>
                    <div className="rounded border border-hairline/60 bg-shelf-2/60 p-1.5">
                      <span className="block text-[10px] text-ink-dim">High (Peak demand)</span>
                      <span className="font-mono text-xs font-semibold text-ink">{inr(zone.income_high)}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Trip Expenses */}
              <div className="rounded-lg border border-hairline/80 bg-shelf-1/70 p-3">
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-dim">
                  2. Trip Costs (Diesel + Crew + Ice)
                </p>
                <LedgerRow
                  label={`Diesel fuel (${zone.fuel_liters != null ? `${zone.fuel_liters} L · ` : ""}${Math.round(zone.distance_km * 2)} km round trip)`}
                  value={`−${inr(zone.fuel_cost)}`}
                />
                <LedgerRow label="Crew share, ice blocks, harbor fees" value={`−${inr(zone.fixed_cost)}`} />
                <LedgerRow
                  strong
                  className="mt-1 border-t border-hairline pt-1 text-ink"
                  label="Total trip expense"
                  value={`−${inr(zone.total_cost)}`}
                />
              </div>

              {/* Net Profit Box (Gross Income − Trip Costs) */}
              {zone.profit_low != null && zone.profit_high != null && (
                <div
                  className={`rounded-lg border p-3 ${
                    zone.profit_color === "green"
                      ? "border-go/40 bg-go/10"
                      : zone.profit_color === "orange"
                      ? "border-caution/40 bg-caution/10"
                      : "border-no-go/40 bg-no-go/10"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-bold text-ink flex items-center gap-1.5">
                      <Sparkles className="size-3.5 text-ocean-cyan" />
                      3. Net Take-Home Profit (Income − Cost)
                    </span>
                    {zone.margin_pct != null && (
                      <span className="font-mono text-xs font-bold text-go">
                        {zone.margin_pct}% margin
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between text-base font-bold font-mono">
                    <span className="text-ink">{inr(zone.profit_low)} (Low)</span>
                    <span className="text-ink-dim font-normal text-xs">to</span>
                    <span className={TONE_TEXT[tone]}>{inr(zone.profit_high)} (Peak)</span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center justify-between border-t border-hairline/60 pt-1.5 text-[11px] text-ink-dim gap-1">
                    <span>
                      Expected mid profit: <strong className="font-mono font-bold text-ink">{zone.profit_mid != null ? inr(zone.profit_mid) : "—"}</strong>
                    </span>
                    <span className="italic">
                      {inr(zone.income_low ?? 0)} to {inr(zone.income_high ?? 0)} gross − {inr(zone.total_cost)} costs
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Detailed Species Catch & Market Value Table (with Low, High & Mid Income) */}
          <details open className="group mt-4 border-t border-hairline pt-3">
            <summary className="flex cursor-pointer list-none items-center justify-between text-xs font-semibold text-ocean-cyan hover:underline">
              <span className="flex items-center gap-1.5">
                <ChevronDown className="size-3.5 transition group-open:rotate-180" />
                Fish Species Catch &amp; Market Value (Low to High Price Ranges)
              </span>
              <span className="text-[10px] font-mono text-ink-dim font-normal">
                {zone.priced_species.length} species modeled
              </span>
            </summary>
            <div className="mt-2.5 overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-hairline text-[11px] text-ink-dim bg-shelf-1/80">
                    <th className="px-2 py-2 font-medium">Fish Species</th>
                    <th className="px-2 py-2 text-right font-medium">Share</th>
                    <th className="px-2 py-2 text-right font-medium">~kg Landed</th>
                    <th className="px-2 py-2 text-right font-medium">₹/kg Range (Low–High)</th>
                    <th className="px-2 py-2 text-right font-medium">Low Income</th>
                    <th className="px-2 py-2 text-right font-medium">High Income</th>
                    <th className="px-2 py-2 text-right font-medium text-ocean-cyan">Expected Mid</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline/40">
                  {zone.priced_species.map((sp) => {
                    const lowIncome = Math.round(sp.est_kg * sp.price_low);
                    const highIncome = Math.round(sp.est_kg * sp.price_high);
                    return (
                      <tr key={sp.aphia_id} className="hover:bg-shelf-2/40">
                        <td className="px-2 py-1.5 text-ink">
                          <div className="font-medium">{sp.common_name}</div>
                          <div className="text-[10px] italic text-ink-dim">{sp.scientific_name}</div>
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono text-ink-muted">{sp.share_pct}%</td>
                        <td className="px-2 py-1.5 text-right font-mono text-ink-muted">{sp.est_kg} kg</td>
                        <td className="px-2 py-2 text-right font-mono text-ink-muted">
                          ₹{sp.price_low} – ₹{sp.price_high}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono text-ink-muted">
                          {inr(lowIncome)}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono text-ink-muted">
                          {inr(highIncome)}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono font-bold text-ink">
                          {inr(sp.income_mid)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-hairline bg-shelf-1/90 font-semibold text-ink text-xs">
                    <td className="px-2 py-2">Total Estimated Landing</td>
                    <td className="px-2 py-2 text-right font-mono">100%</td>
                    <td className="px-2 py-2 text-right font-mono">
                      {totalKg.toFixed(1)} kg
                    </td>
                    <td className="px-2 py-2 text-right text-[10px] text-ink-dim font-normal">Trip Gross Value</td>
                    <td className="px-2 py-2 text-right font-mono text-ink">
                      {zone.income_low != null ? inr(zone.income_low) : "—"}
                    </td>
                    <td className="px-2 py-2 text-right font-mono text-ink">
                      {zone.income_high != null ? inr(zone.income_high) : "—"}
                    </td>
                    <td className="px-2 py-2 text-right font-mono text-ocean-cyan font-bold">
                      {zone.income_mid != null ? inr(zone.income_mid) : "—"}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  );
}

// ─── 6. dashboard: map + list + breakdown ────────────────────────────────────

export function ZoneDashboard({
  profit,
  onSelectPort,
}: {
  profit: ProfitState;
  onSelectPort?: (portId: string) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, loading, error } = profit;
  const zones = data?.zones ?? [];

  // Falls back to the best zone, then the first, until the user picks one.
  const selected =
    zones.find((z) => z.zone_id === selectedId) ?? zones.find((z) => z.is_best_zone) ?? zones[0] ?? null;

  if (loading) {
    return (
      <div className="mb-4 flex flex-col gap-3">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <Skeleton className="h-72 w-full" />
          <Skeleton className="h-72 w-full" />
        </div>
        <Skeleton className="h-44 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mb-4 rounded-lg border border-caution/30 bg-caution/10 p-4 text-xs text-caution">
        Profit estimates are unavailable right now. Try again shortly.
      </div>
    );
  }

  return (
    <section className="mb-4 flex flex-col gap-4" aria-label="Fishing grounds and profit">
      {data.fallback_message && (
        <div className="rounded-lg border border-caution/30 bg-caution/10 px-3 py-2 text-xs text-caution">
          {data.fallback_message}
        </div>
      )}
      {!data.show_profit && (
        <div className="rounded-lg border border-hairline bg-shelf-2/60 px-3 py-2 text-xs text-ink-muted">
          Cargo vessels don&apos;t fish, so profit figures are hidden. Zones are shown for reference.
        </div>
      )}

      {zones.length === 0 ? (
        <div className="rounded-lg border border-dashed border-hairline py-8 text-center text-xs text-ink-muted">
          No charted fishing zones for this port.
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <ZoneMap
              data={data}
              zones={zones}
              selectedId={selected?.zone_id ?? null}
              onSelect={setSelectedId}
              onSelectPort={onSelectPort}
            />
            <RankedZoneList
              zones={zones}
              selectedId={selected?.zone_id ?? null}
              onSelect={setSelectedId}
              showProfit={data.show_profit}
            />
          </div>
          {selected && <ZoneBreakdown zone={selected} />}
        </>
      )}
    </section>
  );
}
