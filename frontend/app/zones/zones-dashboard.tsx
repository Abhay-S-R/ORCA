"use client";

// Fishing zones — dashboard pieces (toolbar, KPI strip, map + ranked list,
// zone breakdown). Drop this next to page.tsx. Uses the existing Badge, Skeleton
// and useT, plus the shelf / ink / hairline / go / caution / no-go tokens.

import { useEffect, useMemo, useState } from "react";
import { Anchor, ChevronDown, Compass, Fish, Fuel, Layers, MapPin, Navigation, Sparkles, TrendingUp } from "lucide-react";
import { Badge } from "../components/Badge";
import { Skeleton } from "../components/States";
import { useT } from "../i18n/useT";

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

function calculateBearing(lat1: number, lon1: number, lat2: number, lon2: number): { deg: number; compass: string } {
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

const inr = (v: number | null | undefined) => {
  if (v == null) return "—";
  return v < 0 ? `−₹${Math.abs(v).toLocaleString("en-IN")}` : `₹${v.toLocaleString("en-IN")}`;
};

const inrK = (v: number | null | undefined) => {
  if (v == null) return "—";
  const a = Math.abs(v);
  const s = a >= 1000 ? `${(a / 1000).toFixed(1).replace(/\.0$/, "")}k` : String(a);
  return `${v < 0 ? "−" : ""}₹${s}`;
};

const CARD = "rounded-xl border border-hairline bg-shelf-2/60 p-4";

// ─── data hook ───────────────────────────────────────────────────────────────

export function useFishingProfit(lat: number, lon: number, vessel: string): ProfitState {
  const [data, setData] = useState<ProfitApiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ lat: String(lat), lon: String(lon), vessel });
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
  }, [lat, lon, vessel]);

  return { data, loading, error };
}

// ─── 1. toolbar: port + vessel in one row ────────────────────────────────────

type PortLite = { id: string; name: string; state: string };

export function ZonesToolbar({
  ports,
  currentPort,
  selectedPortKey,
  onSelectPortKey,
  registeredHomePortName,
  activeVessel,
  onSelectVessel,
}: {
  ports: PortLite[];
  currentPort: PortLite;
  selectedPortKey: string;
  onSelectPortKey: (key: string) => void;
  registeredHomePortName: string | null;
  activeVessel: string;
  onSelectVessel: (key: string) => void;
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
        <p className="hidden text-[11px] text-ink-dim sm:block">
          {selectedPortKey === "default_home"
            ? `From your profile · ${currentPort.name}`
            : "Changed for this page only"}
        </p>
      </div>

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
  ban,
}: {
  sector: { gap: boolean; name: string; message: string };
  nearest: { found: boolean; label: string | null; within: boolean | null; beyondReach: boolean };
  bestZone: ZoneProfitResult | null;
  ban: { applies_here?: boolean; in_ban_period?: boolean; window?: string; next_window?: string } | null;
}) {
  const t = useT();

  const nearestBadge = !nearest.found
    ? { text: "None found", tone: "neutral" as Tone }
    : nearest.beyondReach || nearest.within === false
    ? { text: "Beyond day trip", tone: "caution" as Tone }
    : nearest.within
    ? { text: "Within reach", tone: "go" as Tone }
    : { text: "Advisory zone", tone: "neutral" as Tone };

  const banValue = !ban ? "No data" : ban.applies_here ? "In force" : ban.in_ban_period ? "Offshore only" : "Open";
  const banTone: Tone = !ban ? "neutral" : ban.applies_here ? "no-go" : ban.in_ban_period ? "caution" : "neutral";
  const banBadge = ban ? (ban.in_ban_period ? ban.window : ban.next_window) ?? t("zones.openSeason") : "—";

  return (
    <div className="mb-4 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
      <Kpi
        label={t("zones.yourSector")}
        value={sector.name}
        badge={sector.gap ? t("zones.noAdvisory") : t("zones.advisoryPublished")}
        tone={sector.gap ? "caution" : "go"}
        note={sector.message}
      />
      <Kpi
        label={t("zones.nearestZone")}
        value={nearest.label ?? "—"}
        badge={nearestBadge.text}
        tone={nearestBadge.tone}
      />
      <Kpi
        label="Best margin"
        value={bestZone?.margin_pct != null ? `${bestZone.margin_pct}%` : "—"}
        badge={bestZone ? bestZone.zone_name : "No priced zone"}
        tone={bestZone ? toneOf(bestZone.profit_color) : "neutral"}
      />
      <Kpi label={t("zones.seasonalBan")} value={banValue} badge={banBadge} tone={banTone} />
    </div>
  );
}

// ─── 3. map ──────────────────────────────────────────────────────────────────

function ZoneMap({
  data,
  zones,
  selectedId,
  onSelect,
}: {
  data: ProfitApiResponse;
  zones: ZoneProfitResult[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const W = 560;
  const H = 340;
  const PX = 60;
  const PY = 45;

  const lats = [data.port_lat, ...zones.map((z) => z.lat)];
  const lons = [data.port_lon, ...zones.map((z) => z.lon)];

  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  const centerLat = (minLat + maxLat) / 2;
  const centerLon = (minLon + maxLon) / 2;

  const latKmPerDeg = 111;
  const lonKmPerDeg = 111 * Math.cos((centerLat * Math.PI) / 180);

  const maxZoneDist = Math.max(50, ...zones.map((z) => z.distance_km));
  const rings = maxZoneDist > 110 ? [50, 100, 150] : [25, 50, 100];
  const maxRingKm = Math.max(...rings);

  const ringLatSpan = (maxRingKm / latKmPerDeg) * 2;
  const ringLonSpan = (maxRingKm / lonKmPerDeg) * 2;

  const spanLat = Math.max(ringLatSpan * 1.2, (maxLat - minLat) * 1.5, 1.4);
  const spanLon = Math.max(ringLonSpan * 1.2, (maxLon - minLon) * 1.5, 1.6);

  const startLat = centerLat - spanLat / 2;
  const startLon = centerLon - spanLon / 2;

  const toX = (lon: number) => PX + ((lon - startLon) / spanLon) * (W - 2 * PX);
  const toY = (lat: number) => H - (PY + ((lat - startLat) / spanLat) * (H - 2 * PY));

  const px = toX(data.port_lon);
  const py = toY(data.port_lat);

  const kmToPx = (km: number) => (km / lonKmPerDeg / spanLon) * (W - 2 * PX);

  const isWestCoast =
    data.port_lon < 77.2 ||
    ["Kerala", "Karnataka", "Goa", "Maharashtra", "Gujarat"].includes(data.port_state);

  // Smooth natural coastline
  const coastPath = isWestCoast
    ? `M ${px + 10} 0 Q ${px - 14} ${H * 0.3}, ${px + 8} ${H * 0.65} T ${px - 10} ${H} L ${W} ${H} L ${W} 0 Z`
    : `M ${px - 10} 0 Q ${px + 14} ${H * 0.3}, ${px - 8} ${H * 0.65} T ${px + 10} ${H} L 0 ${H} L 0 0 Z`;

  const coastLine = isWestCoast
    ? `M ${px + 10} 0 Q ${px - 14} ${H * 0.3}, ${px + 8} ${H * 0.65} T ${px - 10} ${H}`
    : `M ${px - 10} 0 Q ${px + 14} ${H * 0.3}, ${px - 8} ${H * 0.65} T ${px + 10} ${H}`;

  // Currently active zone for the telemetry HUD
  const activeZone =
    zones.find((z) => z.zone_id === (hoveredId ?? selectedId)) ??
    zones.find((z) => z.zone_id === selectedId) ??
    zones.find((z) => z.is_best_zone) ??
    zones[0] ??
    null;

  return (
    <div className={`${CARD} flex flex-col p-3.5 gap-2.5`}>
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline/60 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-ocean-cyan/15 text-ocean-cyan">
            <Compass className="size-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-ink">
              Fishing Grounds &amp; Sea Chart · {data.port_name}
            </h3>
            <p className="text-[10px] font-mono text-ink-dim">
              {data.port_lat.toFixed(2)}°N, {data.port_lon.toFixed(2)}°E · {data.port_state} Coast
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden sm:inline-flex items-center gap-1 rounded bg-shelf-3 px-2 py-0.5 text-[10px] font-mono text-ink-dim border border-hairline/60">
            <span className="size-1.5 rounded-full bg-ocean-cyan animate-pulse" /> Live Telemetry
          </span>
          <span className="text-[11px] font-medium text-ocean-cyan">Click pin to inspect</span>
        </div>
      </div>

      {/* SVG Nautical Chart Frame */}
      <div className="relative overflow-hidden rounded-xl border border-hairline/80 shadow-inner bg-shelf-1">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full select-none"
          role="group"
          aria-label={`Admiralty navigation chart of ${zones.length} fishing grounds near ${data.port_name}`}
        >
          <defs>
            {/* Filter for realistic pin drop-shadow */}
            <filter id="pin-shadow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="1.5" stdDeviation="2" floodColor="#1b2633" floodOpacity="0.22" />
            </filter>
            {/* Subtle sea water pattern */}
            <linearGradient id="sea-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#eef7f8" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#e2eff1" stopOpacity="0.85" />
            </linearGradient>
            {/* Land pattern */}
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
              ? `M ${px + 10 + shift} 0 Q ${px - 14 + shift} ${H * 0.3}, ${px + 8 + shift} ${H * 0.65} T ${px - 10 + shift} ${H}`
              : `M ${px - 10 + shift} 0 Q ${px + 14 + shift} ${H * 0.3}, ${px - 8 + shift} ${H * 0.65} T ${px + 10 + shift} ${H}`;
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
            const r = kmToPx(km);
            if (r <= 8) return null;
            const angleRad = (isWestCoast ? 198 : -18) * (Math.PI / 180);
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

          {/* 6. Compass Rose (Nautical Orientation) */}
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

          {/* 7. Bearing Vectors from Port to Zones */}
          {zones.map((z) => {
            const zx = toX(z.lon);
            const zy = toY(z.lat);
            const isSel = selectedId === z.zone_id;
            const isHov = hoveredId === z.zone_id;
            const active = isSel || isHov;
            const c = PIN_HEX[z.profit_color] ?? PIN_HEX.neutral;
            const bearing = calculateBearing(data.port_lat, data.port_lon, z.lat, z.lon);

            const midX = (px + zx) / 2;
            const midY = (py + zy) / 2;

            return (
              <g key={`v-${z.zone_id}`} className="cursor-pointer" onClick={() => onSelect(z.zone_id)}>
                {active && (
                  <line
                    x1={px}
                    y1={py}
                    x2={zx}
                    y2={zy}
                    stroke={c}
                    strokeWidth={4.5}
                    strokeOpacity={0.25}
                    strokeLinecap="round"
                  />
                )}
                <line
                  x1={px}
                  y1={py}
                  x2={zx}
                  y2={zy}
                  stroke={c}
                  strokeWidth={active ? 2.4 : 1.2}
                  strokeOpacity={active ? 0.95 : 0.5}
                  strokeDasharray={active ? "none" : "5 4"}
                />
                {/* Distance & Heading Tag at Midpoint */}
                <g transform={`translate(${midX}, ${midY})`} className="pointer-events-none">
                  <rect
                    x="-37"
                    y="-8.5"
                    width="74"
                    height="17"
                    rx="4"
                    fill="#ffffff"
                    fillOpacity="0.96"
                    stroke={c}
                    strokeWidth={active ? 1.4 : 0.8}
                    strokeOpacity={active ? 0.95 : 0.55}
                    filter="url(#pin-shadow)"
                  />
                  <text
                    y="3.2"
                    textAnchor="middle"
                    fontSize="8.5"
                    fontWeight="bold"
                    fontFamily="monospace"
                    fill="#1c2939"
                  >
                    {Math.round(z.distance_km)} km · {bearing.compass}
                  </text>
                </g>
              </g>
            );
          })}

          {/* 8. Departure Home Port Marker */}
          <g transform={`translate(${px}, ${py})`}>
            <circle r="22" fill="#2f6f74" fillOpacity="0.1" />
            <circle r="14" fill="#2f6f74" fillOpacity="0.22" />
            <circle r="7" fill="#1f4d51" stroke="#ffffff" strokeWidth="2" filter="url(#pin-shadow)" />
            <circle r="2.5" fill="#ffffff" />
          </g>
          {/* Departure Port Label Box */}
          <g
            transform={`translate(${px + (isWestCoast ? 14 : -14)}, ${py - 14})`}
            className="pointer-events-none"
          >
            <rect
              x={isWestCoast ? 0 : -114}
              y="-12"
              width="114"
              height="30"
              rx="6"
              fill="#ffffff"
              fillOpacity="0.96"
              stroke="var(--color-hairline-strong)"
              filter="url(#pin-shadow)"
            />
            <text
              x={isWestCoast ? 8 : -8}
              y="1"
              textAnchor={isWestCoast ? "start" : "end"}
              fontSize="11"
              fontWeight="bold"
              fill="#1c2939"
            >
              ⚓ {data.port_name}
            </text>
            <text
              x={isWestCoast ? 8 : -8}
              y="12"
              textAnchor={isWestCoast ? "start" : "end"}
              fontSize="8.5"
              fontWeight="600"
              fontFamily="monospace"
              fill="#8c8672"
            >
              DEPARTURE PORT
            </text>
          </g>

          {/* 9. Waypoint Pins & Floating Labels */}
          {zones.map((z, i) => {
            const zx = toX(z.lon);
            const zy = toY(z.lat);
            const isSel = selectedId === z.zone_id;
            const isHov = hoveredId === z.zone_id;
            const active = isSel || isHov;
            const c = PIN_HEX[z.profit_color] ?? PIN_HEX.neutral;

            const labelRight = zx < W - 140;
            const labelDown = zy < H - 50;

            return (
              <g
                key={z.zone_id}
                transform={`translate(${zx}, ${zy})`}
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
                {/* Outer Radar Halo */}
                <circle
                  r={active ? 24 : z.is_best_zone ? 18 : 14}
                  fill={c}
                  fillOpacity={active ? 0.32 : 0.16}
                  stroke={c}
                  strokeOpacity={active ? 0.6 : 0.3}
                  strokeWidth={1}
                />

                {/* Waypoint Circle */}
                <circle
                  r={active ? 13 : 11}
                  fill={c}
                  stroke="#ffffff"
                  strokeWidth="2.5"
                  filter="url(#pin-shadow)"
                />
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

                {/* Best Zone Banner */}
                {z.is_best_zone && (
                  <g transform="translate(0, -18)">
                    <rect
                      x="-20"
                      y="-6"
                      width="40"
                      height="13"
                      rx="3.5"
                      fill="#b8862e"
                      stroke="#ffffff"
                      strokeWidth="1"
                      filter="url(#pin-shadow)"
                    />
                    <text
                      y="3"
                      textAnchor="middle"
                      fontSize="7.5"
                      fontWeight="bold"
                      fill="#ffffff"
                    >
                      ★ BEST
                    </text>
                  </g>
                )}

                {/* Floating Waypoint Label Tag */}
                <g
                  transform={`translate(${labelRight ? 18 : -18}, ${labelDown ? 12 : -12})`}
                  className="pointer-events-none select-none"
                >
                  <rect
                    x={labelRight ? 0 : -120}
                    y="-13"
                    width="120"
                    height="32"
                    rx="6"
                    fill="#ffffff"
                    fillOpacity={active ? 0.98 : 0.92}
                    stroke={active ? c : "var(--color-hairline)"}
                    strokeWidth={active ? 1.5 : 1}
                    filter="url(#pin-shadow)"
                  />
                  <text
                    x={labelRight ? 7 : -7}
                    y="-1"
                    textAnchor={labelRight ? "start" : "end"}
                    fontSize="10"
                    fontWeight="bold"
                    fill="#1c2939"
                  >
                    {z.zone_name}
                  </text>
                  <text
                    x={labelRight ? 7 : -7}
                    y="11"
                    textAnchor={labelRight ? "start" : "end"}
                    fontSize="8.5"
                    fontWeight="600"
                    fill={c}
                  >
                    {z.margin_pct != null ? `${z.margin_pct}% margin · ` : ""}
                    {inrK(z.profit_low ?? 0)}–{inrK(z.profit_high ?? 0)}
                  </text>
                </g>
              </g>
            );
          })}
        </svg>
      </div>

      {/* 10. Selected Ground Quick Telemetry HUD */}
      {activeZone && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-hairline/80 bg-shelf-1/90 px-3.5 py-2.5 shadow-2xs">
          <div className="flex items-center gap-2.5 min-w-0">
            <span
              className="flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white shadow-xs font-mono"
              style={{ backgroundColor: PIN_HEX[activeZone.profit_color] ?? PIN_HEX.neutral }}
            >
              {zones.findIndex((z) => z.zone_id === activeZone.zone_id) + 1}
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-bold text-ink truncate">{activeZone.zone_name}</span>
                <span className="rounded bg-shelf-3 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ocean-cyan border border-hairline/60">
                  {Math.round(activeZone.distance_km)} km ·{" "}
                  {calculateBearing(data.port_lat, data.port_lon, activeZone.lat, activeZone.lon).compass}
                </span>
                {activeZone.is_best_zone && (
                  <span className="rounded bg-go/15 px-1.5 py-0.5 text-[10px] font-bold text-go">
                    ★ Best Zone
                  </span>
                )}
              </div>
              <p className="text-[11px] text-ink-dim truncate mt-0.5">
                {activeZone.zone_description} · Trip cost: {inr(activeZone.total_cost)} (fuel + fixed)
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            {activeZone.show_profit && activeZone.profit_mid != null && (
              <div className="text-right">
                <span className="block text-[10px] uppercase font-bold text-ink-dim">Est. Net Profit</span>
                <span className="font-mono text-xs font-bold text-ink">
                  {inrK(activeZone.profit_low ?? 0)} – {inrK(activeZone.profit_high ?? 0)}
                  {activeZone.margin_pct != null && (
                    <span className="ml-1 text-[11px] font-semibold text-go">({activeZone.margin_pct}%)</span>
                  )}
                </span>
              </div>
            )}
            <Badge tone={toneOf(activeZone.profit_color)}>{activeZone.profit_label}</Badge>
          </div>
        </div>
      )}

      {/* 11. Chart Legend & Radar Scale Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-hairline/60 pt-2 text-[10px] text-ink-dim font-mono">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-go inline-block" /> High Profit (≥50%)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-caution inline-block" /> Moderate (25–50%)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-no-go inline-block" /> Low (&lt;25%)
          </span>
          <span className="flex items-center gap-1.5">
            <span>⚓</span> Departure Port
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span>Rings: 25 / 50 / 100 / 150 km</span>
          <span className="text-ink-muted">· CMFRI 2024</span>
        </div>
      </div>
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
    <div className={`${CARD} flex flex-col p-0 overflow-hidden`}>
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
                <div className="flex min-w-0 items-center gap-3">
                  <span
                    className="flex size-6 shrink-0 items-center justify-center rounded-full font-mono text-[11px] font-bold text-white shadow-xs"
                    style={{ backgroundColor: c }}
                  >
                    {i + 1}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-bold text-ink">{z.zone_name}</span>
                      {z.is_best_zone && (
                        <span className="rounded bg-go/15 px-1.5 py-0.2 text-[9px] font-bold text-go">
                          ★ Best
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-ink-dim truncate mt-0.5">
                      <span className="font-semibold text-ocean-cyan font-mono">
                        {Math.round(z.distance_km)} km
                      </span>
                      <span>·</span>
                      <span className="truncate">{z.zone_description}</span>
                    </div>
                  </div>
                </div>

                {showProfit && z.profit_label !== "cargo" && (
                  <div className="shrink-0 text-right">
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

          {/* 3-Step Simple Calculation Banner for Fishermen */}
          {zone.income_low != null && zone.income_high != null && (
            <div className="mb-4 rounded-xl border border-ocean-cyan/30 bg-ocean-cyan/5 p-3.5">
              <p className="text-xs font-bold text-ink flex items-center gap-1.5 mb-2.5">
                <TrendingUp className="size-4 text-ocean-cyan" />
                How your take-home profit is calculated (Simple 3 steps):
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                {/* Step 1: Fish Sales */}
                <div className="rounded-lg border border-hairline/80 bg-shelf-1/90 p-2.5">
                  <div className="text-[10px] text-ink-dim font-bold uppercase tracking-wider">Step 1: Fish Sales (Gross)</div>
                  <div className="text-sm font-bold font-mono text-ink mt-1">
                    {inr(zone.income_low)} – {inr(zone.income_high)}
                  </div>
                  <div className="text-[10px] text-ink-muted mt-0.5">
                    Normal day: <strong className="font-mono text-ink">{zone.income_mid != null ? inr(zone.income_mid) : "—"}</strong>
                  </div>
                  <div className="text-[10px] text-ink-dim mt-0.5 italic">Harbor auction vs retail</div>
                </div>

                {/* Step 2: Boat Expenses */}
                <div className="rounded-lg border border-hairline/80 bg-shelf-1/90 p-2.5">
                  <div className="text-[10px] text-ink-dim font-bold uppercase tracking-wider">Step 2: Boat Expenses</div>
                  <div className="text-sm font-bold font-mono text-no-go mt-1">
                    −{inr(zone.total_cost)}
                  </div>
                  <div className="text-[10px] text-ink-muted mt-0.5">
                    Diesel: {inr(zone.fuel_cost)} + Ice/Crew: {inr(zone.fixed_cost)}
                  </div>
                  <div className="text-[10px] text-ink-dim mt-0.5 italic">{Math.round(zone.distance_km * 2)} km round trip</div>
                </div>

                {/* Step 3: Take-Home Profit */}
                <div className="rounded-lg border border-hairline/80 bg-shelf-1/90 p-2.5">
                  <div className="text-[10px] text-ink-dim font-bold uppercase tracking-wider">Step 3: Profit In Hand</div>
                  <div className={`text-sm font-bold font-mono mt-1 ${TONE_TEXT[tone]}`}>
                    {inr(zone.profit_low)} – {inr(zone.profit_high)}
                  </div>
                  <div className="text-[10px] text-ink-muted mt-0.5">
                    Normal day: <strong className="font-mono text-ink">{zone.profit_mid != null ? inr(zone.profit_mid) : "—"}</strong>
                  </div>
                  <div className="text-[10px] text-ink-dim mt-0.5 italic">{zone.margin_pct}% kept after costs</div>
                </div>
              </div>

              <div className="text-[11px] text-ink-muted leading-relaxed mt-3 pt-2.5 border-t border-hairline/60">
                <span className="font-bold text-ink">💡 Simple Formula:</span> <em>Fish Sales at Harbor − Total Trip Expenses = Money in Your Hand.</em><br />
                Your boat spends <strong>{inr(zone.fuel_cost)}</strong> on diesel and <strong>{inr(zone.fixed_cost)}</strong> on crew, ice &amp; harbor fees (total <strong>{inr(zone.total_cost)}</strong>).
                <ul className="mt-1 list-disc pl-4 space-y-0.5 text-[10.5px]">
                  <li>
                    <strong>Low prices (Harbor glut / auction):</strong> {inr(zone.income_low)} sales − {inr(zone.total_cost)} costs = <strong>{inr(zone.profit_low)}</strong> take-home profit.
                  </li>
                  <li>
                    <strong>Normal market prices:</strong> {inr(zone.income_mid ?? 0)} sales − {inr(zone.total_cost)} costs = <strong>{inr(zone.profit_mid ?? 0)}</strong> take-home profit ({zone.margin_pct}% margin).
                  </li>
                  <li>
                    <strong>Peak prices (High retail demand):</strong> {inr(zone.income_high)} sales − {inr(zone.total_cost)} costs = <strong>{inr(zone.profit_high)}</strong> take-home profit.
                  </li>
                </ul>
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
                  label={`Diesel fuel (${Math.round(zone.distance_km * 2)} km round trip)`}
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

export function ZoneDashboard({ profit }: { profit: ProfitState }) {
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
          Cargo vessels don't fish, so profit figures are hidden. Zones are shown for reference.
        </div>
      )}

      {zones.length === 0 ? (
        <div className="rounded-lg border border-dashed border-hairline py-8 text-center text-xs text-ink-muted">
          No charted fishing zones for this port.
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <ZoneMap data={data} zones={zones} selectedId={selected?.zone_id ?? null} onSelect={setSelectedId} />
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

      <p className="text-[11px] leading-relaxed text-ink-dim">
        <strong className="font-semibold">Approximate values only.</strong> {data.disclaimer} Diesel assumed at ₹
        {data.diesel_price_inr}/litre. Prices cross-referenced with CMFRI 2024 national landings data.
      </p>
    </section>
  );
}
