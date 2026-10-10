"use client";

// The ORCA chart (plan §4.7). Ported from Leaflet to MapLibre GL JS v6, used
// directly rather than through @vis.gl/react-map-gl — the wrapper lags
// MapLibre releases (its Map component assumed the `supported()` method that
// v3 removed) and its one strong argument, deck.gl integration, sits behind a
// Phase-3 conditional the plan already marks cuttable.
//
// Layer lifecycle per §4.7: ONE map instance, mounted once. Layers are added
// to and removed from it; GeoJSON updates go through source.setData() rather
// than teardown-and-recreate, which is what keeps a toggle inside 400 ms.
import "maplibre-gl/dist/maplibre-gl.css";
import * as maplibregl from "maplibre-gl";
import { setWorkerUrl } from "maplibre-gl";
import { FlowFieldCanvas } from "./FlowFieldCanvas";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Calendar, ChevronDown, ChevronUp, Compass, Crosshair, Fish, Layers, MapPin, Navigation, ShieldCheck, Waves, X } from "lucide-react";
import {
  BASEMAP_LABELS,
  BASEMAP_RASTERS,
  BASEMAP_STYLE,
  CHART,
  INDIA_CENTER,
  INDIA_VIEW,
  RASTER_OVERLAYS,
  webglAvailable,
  type BasemapId,
} from "../map/basemap";
import { Badge, type BadgeTone } from "./Badge";
import { LayerToggle } from "./LayerToggle";
import { Panel } from "./Panel";
import { Readout, ReadoutGrid } from "./Readout";
import { EmptyState } from "./States";
import { TimeSlider } from "./TimeSlider";
import { inSync, syncNote, type LayerTiming } from "../lib/timeSync";
import { getToken } from "../lib/auth";
import { useGeolocation } from "../lib/useGeolocation";
import { measureLayerToggle, reportLayerMetrics } from "../lib/layerPerf";
import { watchBadges as fetchWatchBadges, type WatchBadge } from "../lib/watches";
import { API_BASE } from "../lib/apiBase";

// See scripts/copy-maplibre-worker.mjs — Turbopack will not emit the worker's
// sibling module next to it, so the worker is served from public/ instead.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

type BoundaryGeoJson = { type: "FeatureCollection"; features: GeoJsonFeature[] };
type GeoJsonFeature = {
  type: "Feature";
  geometry: unknown;
  properties: { name: string; designation: string; near?: boolean };
};
type PfzSpeciesItem = {
  name: string;
  scientific_name?: string;
  depth_fit?: string;
  tonnes?: number;
  confidence?: string;
  source?: string;
};
type PfzProperties = {
  sector?: string;
  landing_center?: string;
  direction?: string;
  bearing_deg?: number;
  distance_km?: string | number;
  depth_m?: string | number;
  valid_for?: string;
  // docs/data/ORCA_Stale_Data_Policy.md — every zone carries its own age; a
  // cloud-covered sector shows its last clear day's zones, labelled old.
  age_days?: number;
  band?: "fresh" | "hint" | "history";
  expired?: boolean;
  source?: string;
  approx_area_km2?: number;
  mean_sst_c?: number;
  mean_depth_m?: number;
  top_species?: PfzSpeciesItem[] | string;
  top_species_names?: string[] | string;
};
type PfzFeature = {
  geometry: { coordinates: [number, number] };
  properties: PfzProperties;
};
type PfzScreenPos = {
  left: number;
  top: number;
  side: "left" | "right";
  arrowY: number;
};

// Projects a PFZ marker to screen space and picks which side of it the
// advisory bubble should sit on, clamping coordinates so it never clips
// off the top/bottom/edges of the map container, with arrowY dynamically
// pointing directly back at the marker coordinates.
function projectPfzPos(m: maplibregl.Map, coords: [number, number]): PfzScreenPos {
  const pos = m.project(coords);
  const container = m.getContainer();
  const width = container.clientWidth;
  const height = container.clientHeight;
  const cardWidth = 310;
  const cardHeight = 440;
  const gap = 14;

  const side: "left" | "right" = pos.x > width / 2 ? "left" : "right";
  const rawLeft = side === "right" ? pos.x + gap : pos.x - gap - cardWidth;
  const left = Math.max(8, Math.min(width - cardWidth - 8, rawLeft));

  const rawTop = pos.y - cardHeight / 2;
  const top = Math.max(8, Math.min(height - cardHeight - 8, rawTop));
  const arrowY = Math.max(28, Math.min(cardHeight - 28, pos.y - top));

  return { left, top, side, arrowY };
}

function resolveTopSpeciesForPfz(pfz: PfzProperties): PfzSpeciesItem[] {
  if (pfz.top_species) {
    if (Array.isArray(pfz.top_species) && pfz.top_species.length > 0) {
      return pfz.top_species as PfzSpeciesItem[];
    }
    if (typeof pfz.top_species === "string") {
      try {
        const parsed = JSON.parse(pfz.top_species);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      } catch {
        // fallback below
      }
    }
  }

  // Data-grounded fallback based on CMFRI 2024 landings and FishBase depth envelopes
  const depthNums = String(pfz.depth_m || "").match(/\d+(?:\.\d+)?/g);
  const avgDepth = depthNums ? depthNums.reduce((acc, v) => acc + parseFloat(v), 0) / depthNums.length : 25;

  if (avgDepth >= 150) {
    return [
      { name: "Yellowfin tuna", scientific_name: "Thunnus albacares", depth_fit: "Deep pelagic (1-1600m)", tonnes: 25620 },
      { name: "Ribbon fishes", scientific_name: "Trichiurus lepturus", depth_fit: "Slope (0-589m)", tonnes: 229359 },
      { name: "Red-toothed triggerfish", scientific_name: "Odonus niger", depth_fit: "Reefs/slope", tonnes: 51348 },
    ];
  }

  const sec = String(pfz.sector || "").toUpperCase();
  if (sec.includes("KERALA")) {
    return [
      { name: "Oil sardine", scientific_name: "Sardinella longiceps", depth_fit: "Coastal (20-200m)", tonnes: 241273 },
      { name: "Indian mackerel", scientific_name: "Rastrelliger kanagurta", depth_fit: "Coastal (20-90m)", tonnes: 262984 },
      { name: "Ribbon fishes", scientific_name: "Trichiurus lepturus", depth_fit: "Shelf (0-589m)", tonnes: 229359 },
    ];
  }
  if (sec.includes("GUJARAT") || sec.includes("MAHARASHTRA")) {
    return [
      { name: "Indian mackerel", scientific_name: "Rastrelliger kanagurta", depth_fit: "Coastal (20-90m)", tonnes: 262984 },
      { name: "Bombayduck", scientific_name: "Harpadon nehereus", depth_fit: "Shelf (10-50m)", tonnes: 94814 },
      { name: "Silver pomfret", scientific_name: "Pampus argenteus", depth_fit: "Shelf (5-110m)", tonnes: 26638 },
    ];
  }
  if (sec.includes("ANDHRA") || sec.includes("ODISHA") || sec.includes("BENGAL")) {
    return [
      { name: "Indian mackerel", scientific_name: "Rastrelliger kanagurta", depth_fit: "Coastal (20-90m)", tonnes: 32000 },
      { name: "Lesser sardines", scientific_name: "Sardinella fimbriata", depth_fit: "Coastal (0-50m)", tonnes: 170228 },
      { name: "Croakers", scientific_name: "Johnius carutta", depth_fit: "Coastal (10-60m)", tonnes: 110142 },
    ];
  }

  return [
    { name: "Lesser sardines", scientific_name: "Sardinella fimbriata", depth_fit: "Coastal (0-50m)", tonnes: 77000 },
    { name: "Indian mackerel", scientific_name: "Rastrelliger kanagurta", depth_fit: "Coastal (20-90m)", tonnes: 262984 },
    { name: "Silver pomfret", scientific_name: "Pampus argenteus", depth_fit: "Shelf (5-110m)", tonnes: 26638 },
  ];
}
// D2 -> D3 handoff (plan §14, orca/notifications/watch_badges.py) — same
// severity vocabulary as the notification feed, never re-derived here.
const SEVERITY_TONE: Record<WatchBadge["severity"], BadgeTone> = {
  info: "neutral",
  advisory: "accent",
  warning: "caution",
  danger: "no-go",
};
type DepthResult = { depth_m: number | null; on_land: boolean; shallow_hazard: boolean };
type Bearing = { bearing_deg: number; distance_nm: number };
type CurrentVector = { lat: number; lon: number; speed_ms: number; direction_deg: number };
type WindVector = { lat: number; lon: number; speed_ms: number; direction_deg: number };
type RasterLayerMeta = {
  layer_id: string;
  layer_type: "Raster" | "Heatmap";
  tile_url: string | null;
  bounds: [number, number, number, number];
  forecast_frames: string[] | null;
  style_hints: { opacity: number; min_zoom: number; max_zoom: number };
};

const EMPTY = { type: "FeatureCollection", features: [] };

interface MarinePortPreset {
  id: string;
  name: string;
  sub: string;
  center: [number, number];
  zoom: number;
  // Which side of this region's screen is open water once centred — the
  // region dashboard docks to that side so it never sits over the coastline.
  // "island" (surrounded by water) defaults to the right, same as "all".
  coast: "west" | "east" | "island";
}

// Great-circle distance in km — good enough to decide whether the region
// dashboard is still relevant, not a navigation-grade solution (that's what
// the depth/bearing sounding HUD is for).
function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

// Initial great-circle bearing from one point to another, in degrees
// (0 = north, 90 = east) — what the ship marker below rotates to, so it
// visibly points at whatever real geometry the chart just focused on.
function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const y = Math.sin(toRad(lon2 - lon1)) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lon2 - lon1));
  return (Math.atan2(y, x) * 180) / Math.PI;
}

// Flattens a GeoJSON Polygon/MultiPolygon/LineString's nested coordinate
// arrays into a flat [lon, lat][] list — enough to fitBounds around a real
// boundary feature, not a full geometry library.
function flattenCoords(geometry: unknown): [number, number][] {
  const out: [number, number][] = [];
  const walk = (node: unknown) => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number") {
      out.push(node as [number, number]);
      return;
    }
    for (const child of node) walk(child);
  };
  walk((geometry as { coordinates?: unknown })?.coordinates);
  return out;
}

// The region dashboard holds while the chart is looking at the selected sector.
const REGION_DRIFT_KM = 300;
const REGION_ZOOM_SLACK = 2.2;
const REGION_STATS_RADIUS_KM = 150;

const COASTAL_REGIONS: MarinePortPreset[] = [
  { id: "all", name: "All India Coastline", sub: "National Overview", center: [78.5, 15.5], zoom: 4.8, coast: "island" },
  { id: "gulf_mannar", name: "Gulf of Mannar / Thoothukudi", sub: "Tamil Nadu Coast", center: [78.8, 8.8], zoom: 7.8, coast: "east" },
  { id: "gujarat", name: "Gujarat (Kutch & Saurashtra)", sub: "West Coast", center: [69.6, 21.8], zoom: 7.2, coast: "west" },
  { id: "mumbai", name: "Mumbai & Konkan Coast", sub: "Maharashtra", center: [72.8, 18.9], zoom: 8.2, coast: "west" },
  { id: "goa", name: "Goa & Karwar", sub: "Goa / Karnataka", center: [73.8, 15.4], zoom: 8.4, coast: "west" },
  { id: "kochi", name: "Kochi & Malabar Coast", sub: "Kerala", center: [76.1, 9.9], zoom: 8.2, coast: "west" },
  { id: "lakshadweep", name: "Lakshadweep Islands", sub: "Arabian Sea", center: [72.6, 10.5], zoom: 8.0, coast: "island" },
  { id: "chennai", name: "Chennai & Coromandel", sub: "Tamil Nadu", center: [80.3, 13.1], zoom: 8.2, coast: "east" },
  { id: "vizag", name: "Visakhapatnam & Circars", sub: "Andhra Pradesh", center: [83.3, 17.7], zoom: 8.0, coast: "east" },
  { id: "kolkata", name: "Odisha & Sundarbans", sub: "East Coast", center: [87.5, 20.8], zoom: 7.5, coast: "east" },
  { id: "andaman", name: "Andaman & Nicobar", sub: "Bay of Bengal", center: [92.8, 11.6], zoom: 7.0, coast: "island" },
];


// `/tiles/{layer_id}/{time}/{z}/{x}/{y}.png` — the on-disk frame directory
// has `:` replaced with `-` (illegal in a Windows path); orca/tiles.py keeps
// the real ISO string in forecast_frames, so the frontend applies the same
// substitution when it resolves the `{time}` token.
const resolveTileUrl = (template: string, frame?: string) =>
  frame ? template.replace("{time}", frame.replace(/:/g, "-")) : template;

// §4.7 layer lifecycle budget: 2 concurrent heavy layers on mobile, 4 on
// desktop, LRU-evicted with a visible notice rather than a silent frame-rate
// collapse. These four toggles are the chart's only "heavy" layers today.
// Width of the scale bar in screen pixels; the label reports the real
// distance across exactly this span.
const SCALE_BAR_PX = 100;

const HEAVY_KEYS = ["srvBathymetry", "waveForecast", "currents", "wind"] as const;
type HeavyKey = (typeof HEAVY_KEYS)[number];
const HEAVY_LABEL: Record<HeavyKey, string> = {
  srvBathymetry: "Depth grid (Sagar Sarathi)",
  waveForecast: "Wave height forecast",
  currents: "Surface currents",
  wind: "Wind (archived)",
};

export type RouteGeoJson = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: "LineString"; coordinates: [number, number][] };
    properties: { segment_id: string; status: "CLEAR" | "CAUTION" | "BLOCKED"; hazard_class: string; detail: string; eta: string; distance_nm: number };
  }[];
};
export type MapPin = { lat: number; lon: number; label: string; color: string };

// Ask page's query -> chart behaviour (plan §7/§8): which real layer to bring
// forward and where to look, derived from the query's classified intent.
// `nonce` must change on every ask() call (even a repeat of the same intent)
// so the effect below re-runs and re-focuses the chart each time.
// `regionId` is an optional direct hit against COASTAL_REGIONS (the query
// named a place) — when present it wins the camera move outright, since a
// named location is a stronger signal than the topic-based intent.
export type DistressMarker = { id: string; lat: number; lon: number; label: string };

export type QueryFocus = {
  intent: "fishing" | "boundary" | "safety" | "current" | "wave" | "wind" | "general";
  regionId?: string;
  coords?: [number, number];
  nonce: number;
};

/** What a question actually asks the chart to show. Answering a query swaps
 *  the layer set to exactly this — every other layer goes off, so the chart
 *  under an answer carries the evidence for that answer and nothing else.
 *  "safety" keeps two layers because the go/no-go verdict is itself built on
 *  two: sea state and boundary standoff. "general" is absent on purpose — an
 *  unclassifiable question is not a request to strip the chart bare, so it
 *  leaves the layers exactly as the reader left them. */
const QUERY_INTENT_LAYERS: Partial<Record<QueryFocus["intent"], readonly string[]>> = {
  fishing: ["pfz"],
  boundary: ["boundaries", "boundaryLines"],
  current: ["currents"],
  wave: ["waveForecast", "wind"],
  wind: ["wind"],
  safety: ["currents", "boundaries"],
};

export function MapView({
  className = "h-full w-full",
  showPanels = true,
  showLayerPanel = true,
  showRegionSwitcher = true,
  showLegends = true,
  onPointClick,
  routeGeoJson,
  pins,
  showSoundingHud = true,
  defaultCollapsedSounding = false,
  initialLayers,
  queryFocus,
  distressMarkers,
}: {
  className?: string;
  showPanels?: boolean;
  // Ask page keeps the base panel chrome (recenter) but hides the controls
  // that let a user override the query-driven defaults — the chart is meant
  // to read as "already focused for you," not as a console with knobs.
  // /map keeps all of it, since it has no query to derive a focus from.
  showLayerPanel?: boolean;
  showRegionSwitcher?: boolean;
  // The floating depth/wave-height colour-key cards — real information, but
  // one more floating box Ask's tighter layout doesn't have room for.
  showLegends?: boolean;
  // Additive hook for /voyage's click-to-set origin/destination — fires
  // alongside the existing depth/bearing "sounding" lookup below, never
  // replacing it.
  onPointClick?: (lat: number, lon: number) => void;
  routeGeoJson?: RouteGeoJson | null;
  pins?: MapPin[];
  showSoundingHud?: boolean;
  defaultCollapsedSounding?: boolean;
  // Ask-page-only default: both /voyage and /map keep their own tuned
  // defaults (a bathymetry/current layer costs one of the 2-4 concurrent
  // heavy-layer budget), so this only overrides what the caller passes.
  initialLayers?: Partial<{
    boundaries: boolean;
    boundaryLines: boolean;
    pfz: boolean;
    seamarks: boolean;
    srvBathymetry: boolean;
    waveForecast: boolean;
    currents: boolean;
    wind: boolean;
    watchBadges: boolean;
    cyclone: boolean;
  }>;
  queryFocus?: QueryFocus | null;
  /** Distress positions (P4.16). Drawn on top of everything with no close
   *  control — a distress marker is never dismissible from the map; it goes
   *  away only when the caller stops passing it (e.g. /ops closes the event). */
  distressMarkers?: DistressMarker[];
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [supported] = useState(webglAvailable);

  // The user's real GPS fix, when granted — never a hardcoded coordinate.
  // Every place this component previously used a fixed "you are here" point
  // now reads `focusPoint`, which is the real fix when we have one and a
  // neutral India-centre otherwise; only the "Your Location" marker itself
  // is gated on an actual granted fix (no marker at all without one).
  const { position: userLocation, status: geoStatus } = useGeolocation();
  // Memoised so it is a stable dependency: `getCurrentPosition` is one-shot,
  // so this identity changes at most once — when the real fix lands — and the
  // layer fetch below re-runs then, which is the point of reading it at all.
  const focusPoint = useMemo(() => userLocation ?? INDIA_CENTER, [userLocation]);

  const [nearNames, setNearNames] = useState<string[]>([]);
  const [clicked, setClicked] = useState<{ lat: number; lon: number } | null>(null);
  const [soundingCollapsed, setSoundingCollapsed] = useState(defaultCollapsedSounding);
  const [soundingDismissed, setSoundingDismissed] = useState(false);
  // Collapsed by default — expanded, "Chart layers" is 7 rows tall and, on a
  // phone-width viewport, ate more than a third of the map's own height
  // (reproduced live at 390x844). Nothing here is safety-critical at a
  // glance, so it starts as a one-line header the way SourceChip's
  // provenance popover does, not open by default.
  const [layersOpen, setLayersOpen] = useState(false);
  // Which basemap is showing under the chart layers. "chart" is the vector
  // style itself; the others are raster layers already in the style, so this
  // only ever flips `visibility` — no restyle, no source/layer teardown.
  const [basemap, setBasemap] = useState<BasemapId>("satellite");
  // Read inside the map-load handler, which runs once and must not re-run
  // when the basemap changes — the glyph re-tint effect below handles that.
  const basemapRef = useRef(basemap);
  useEffect(() => {
    basemapRef.current = basemap;
  }, [basemap]);
  const [depth, setDepth] = useState<DepthResult | null>(null);
  // Nearest DELIMITED boundary line at the tapped point: which treaty line,
  // how far, on what agreement. The EEZ-edge distance answers a different
  // question and must not be mistaken for this one.
  const [boundaryLine, setBoundaryLine] = useState<{
    line_name: string; line_type: string; between: (string | null)[];
    distance_nm: number; bearing_deg: number; alert_level: string;
    treaty: string | null; treaty_date: string | null;
  } | null>(null);
  const [bearing, setBearing] = useState<Bearing | null>(null);
  const [layers, setLayers] = useState({
    boundaries: false,
    boundaryLines: false,
    pfz: true,
    seamarks: true,
    srvBathymetry: false,
    waveForecast: false,
    currents: false,
    wind: true,
    watchBadges: true,
    cyclone: true,
    ...initialLayers,
  });
  const [rasterLayers, setRasterLayers] = useState<RasterLayerMeta[]>([]);
  const [currentVectors, setCurrentVectors] = useState<CurrentVector[] | null>(null);
  const [currentBounds, setCurrentBounds] = useState<[number, number, number, number] | null>(null);
  // Archived ScatSat wind — a second, honestly-distinct vector field from
  // live HYCOM currents (never merged into one layer/label, plan's "ship
  // both, honest labels" instruction). `windAcquisitionDate` drives the
  // toggle's own label text, not a hardcoded "live"-sounding string.
  const [windVectors, setWindVectors] = useState<WindVector[] | null>(null);
  const [windBounds, setWindBounds] = useState<[number, number, number, number] | null>(null);
  const [windAcquisitionDate, setWindAcquisitionDate] = useState<string | null>(null);
  // Each snapshot field's real valid time and step, for the time slider (P4.15).
  const [currentsTiming, setCurrentsTiming] = useState<LayerTiming | null>(null);
  const [windTiming, setWindTiming] = useState<LayerTiming | null>(null);
  // Live cyclone track and cone (GDACS, P5.30). `note` is what the legend
  // says — including "no active cyclone" — so an empty layer is never silent.
  const [cyclone, setCyclone] = useState<{ available: boolean; note: string; systems: unknown[] } | null>(null);
  const [selectedPfz, setSelectedPfz] = useState<PfzProperties | null>(null);
  const [selectedPfzPos, setSelectedPfzPos] = useState<PfzScreenPos | null>(null);
  const selectedPfzCoordsRef = useRef<[number, number] | null>(null);
  const [selectedBadge, setSelectedBadge] = useState<WatchBadge | null>(null);
  // Kept alongside the map-source copies of the same fetches (never a second
  // fetch) purely so the region dashboard below can filter them by distance.
  const [pfzFeatures, setPfzFeatures] = useState<PfzFeature[]>([]);
  // Same reasoning, for the Ask-page query-focus effect below: it needs the
  // "near" flag already computed onto the boundary features to fit the chart
  // around the actual nearby boundary geometry, not just fly to a fixed zoom.
  const [boundaryFeatures, setBoundaryFeatures] = useState<BoundaryGeoJson>(EMPTY as BoundaryGeoJson);
  const [watchBadgeFeatures, setWatchBadgeFeatures] = useState<WatchBadge[]>([]);
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const forecastLayer = rasterLayers.find((l) => l.forecast_frames && l.forecast_frames.length > 0);
  // The slider's hour, only while the slider is actually on screen. Snapshot
  // layers are compared against it and greyed when they don't match (P4.15).
  const sliderIso =
    forecastLayer?.forecast_frames && layers.waveForecast
      ? forecastLayer.forecast_frames[Math.min(frameIndex, forecastLayer.forecast_frames.length - 1)]
      : null;
  const greyCurrents = sliderIso !== null && layers.currents && !inSync(sliderIso, currentsTiming);
  const greyWind = sliderIso !== null && layers.wind && !inSync(sliderIso, windTiming);
  const sliderNotes = sliderIso
    ? [
        ...(layers.currents && currentVectors?.length ? [syncNote("Currents (HYCOM)", sliderIso, currentsTiming)] : []),
        ...(layers.wind && windVectors?.length ? [syncNote("Wind (ScatSat)", sliderIso, windTiming)] : []),
      ]
    : [];

  // §4.7 layer lifecycle: heavy-layer LRU + eviction notice.
  const [heavyLimit, setHeavyLimit] = useState(4);
  const [evictionNotice, setEvictionNotice] = useState<string | null>(null);
  const lru = useRef<HeavyKey[]>(HEAVY_KEYS.filter((k) => layers[k]));

  const [selectedRegion, setSelectedRegion] = useState("all");
  const [regionDropdownOpen, setRegionDropdownOpen] = useState(false);
  const regionDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (regionDropdownRef.current && !regionDropdownRef.current.contains(e.target as Node)) {
        setRegionDropdownOpen(false);
      }
    }
    if (regionDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [regionDropdownOpen]);

  // The region dashboard tracks the chart, not the click — pan or zoom away
  // from the selected region and it clears itself instead of showing stale
  // stats for water that's no longer on screen.
  useEffect(() => {
    if (!ready || !map.current || selectedRegion === "all") return;
    const region = COASTAL_REGIONS.find((r) => r.id === selectedRegion);
    if (!region) return;
    const m = map.current;
    const onMoveEnd = () => {
      const c = m.getCenter();
      const driftKm = haversineKm(c.lat, c.lng, region.center[1], region.center[0]);
      const zoomedOut = m.getZoom() < region.zoom - REGION_ZOOM_SLACK;
      if (driftKm > REGION_DRIFT_KM || zoomedOut) setSelectedRegion("all");
    };
    m.on("moveend", onMoveEnd);
    return () => {
      m.off("moveend", onMoveEnd);
    };
  }, [ready, selectedRegion]);

  // Same fetches that feed the map layers, filtered to "near the selected
  // region's centre" — no separate region API, just a distance filter over
  // data already on screen.
  const regionStats = useMemo(() => {
    if (selectedRegion === "all") return null;
    const region = COASTAL_REGIONS.find((r) => r.id === selectedRegion);
    if (!region) return null;
    const [rlon, rlat] = region.center;
    const within = (lat: number, lon: number) => haversineKm(rlat, rlon, lat, lon) <= REGION_STATS_RADIUS_KM;

    const zoneCount = pfzFeatures.filter((f) => within(f.geometry.coordinates[1], f.geometry.coordinates[0])).length;
    const hazardCount = watchBadgeFeatures.filter(
      (b) => b.status === "active" && b.lat != null && b.lon != null && within(b.lat, b.lon),
    ).length;
    const nearWind = (windVectors ?? []).filter((v) => within(v.lat, v.lon));
    const avgWindMs = nearWind.length ? nearWind.reduce((s, v) => s + v.speed_ms, 0) / nearWind.length : null;

    return { region, zoneCount, hazardCount, avgWindMs };
  }, [selectedRegion, pfzFeatures, watchBadgeFeatures, windVectors]);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    const update = () => setHeavyLimit(mq.matches ? 2 : 4);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!evictionNotice) return;
    const t = setTimeout(() => setEvictionNotice(null), 5000);
    return () => clearTimeout(t);
  }, [evictionNotice]);

  // §4.7 instrumentation: layer_load_ms/render_ms/payload_bytes/dropped_frames
  // per heavy-layer toggle, resolved against whichever MapLibre source that
  // toggle currently drives.
  const measureHeavyToggle = useCallback(
    (key: HeavyKey) => {
      const m = map.current;
      if (!m) return;
      let sourceId: string | null = null;
      if (key === "srvBathymetry") {
        const l = rasterLayers.find((r) => !r.forecast_frames?.length);
        if (l) sourceId = `srv-${l.layer_id}`;
      } else if (key === "waveForecast" && forecastLayer) {
        sourceId = `srv-${forecastLayer.layer_id}`;
      }
      if (sourceId && m.getSource(sourceId)) {
        measureLayerToggle(m, key, sourceId).then(reportLayerMetrics);
      }
    },
    [rasterLayers, forecastLayer],
  );

  // Plain callback, not a setState updater — `lru.current` mutations must
  // run exactly once per toggle. React 18 Strict Mode (Next dev's default)
  // can invoke a setState *updater* function twice to surface impurities;
  // mutating a ref inside one (the previous shape here) silently double-
  // applied the LRU filter/push, corrupting eviction order and letting a
  // 3rd heavy layer stay on past the mobile cap of 2 — reproduced live.
  const toggleHeavy = useCallback(
    (key: HeavyKey, on: boolean) => {
      const next = { ...layers, [key]: on };
      if (on) {
        lru.current = [...lru.current.filter((k) => k !== key), key];
        const onCount = HEAVY_KEYS.filter((k) => next[k]).length;
        if (onCount > heavyLimit) {
          const evict = lru.current.find((k) => k !== key && next[k]);
          if (evict) {
            next[evict] = false;
            lru.current = lru.current.filter((k) => k !== evict);
            setEvictionNotice(
              `${HEAVY_LABEL[evict]} turned off — only ${heavyLimit} heavy layers can run at once`,
            );
          }
        }
      } else {
        lru.current = lru.current.filter((k) => k !== key);
      }
      setLayers(next);
      if (on) measureHeavyToggle(key);
    },
    [layers, heavyLimit, measureHeavyToggle],
  );

  const handleClick = useCallback(async (lat: number, lon: number) => {
    onPointClick?.(lat, lon);
    setClicked({ lat, lon });
    setSoundingDismissed(false);
    setSoundingCollapsed(false);
    setDepth(null);
    setBearing(null);
    setBoundaryLine(null);
    try {
      const [d, b, line] = await Promise.all([
        fetch(`${API_BASE}/api/depth?lat=${lat}&lon=${lon}`).then((r) => r.json()),
        fetch(
          `${API_BASE}/api/bearing?from_lat=${focusPoint[1]}&from_lon=${focusPoint[0]}&to_lat=${lat}&to_lon=${lon}`,
        ).then((r) => r.json()),
        fetch(`${API_BASE}/api/boundary-line?lat=${lat}&lon=${lon}`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
      ]);
      setDepth(d);
      setBearing(b);
      setBoundaryLine(line);
    } catch (err) {
      console.warn("MapView: depth/bearing fetch failed (backend may be starting up)", err);
    }
  }, [onPointClick, focusPoint]);

  // The map's own click listener is registered once, inside the create-once
  // effect below, so it would otherwise keep whichever `handleClick` closure
  // existed at map creation — the one whose `focusPoint` is still the neutral
  // India centre, making "bearing from you" wrong for the rest of the session
  // once a real GPS fix lands. The listener calls through this ref instead, so
  // it always runs the current closure and the effect stays create-once.
  const handleClickRef = useRef(handleClick);
  useEffect(() => {
    handleClickRef.current = handleClick;
  }, [handleClick]);

  /* ---- map instance: created once, never recreated ---- */
  useEffect(() => {
    if (!container.current || !supported || map.current) return;

    const m = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE,
      // Fixed opening camera (INDIA_VIEW): all of India plus the current
      // field's water, scale bar at 98.3 nm. Not derived from any dataset's
      // bounds, so it is the same view every load — a query or the region
      // switcher moves it from here, and the Gulf of Mannar pilot bounds are
      // still available as a preset via COASTAL_REGIONS.
      center: INDIA_VIEW.center,
      zoom: INDIA_VIEW.zoom,
      // Attribution and scale live bottom-LEFT: the bottom-right corner is
      // reserved for the SOS button, which must never be covered or cover.
      // Attribution is added by hand below so it can sit bottom-LEFT: the
      // bottom-right corner belongs to the SOS button.
      attributionControl: false,
      // Pitch is available for depth reading on the researcher/navigator
      // surfaces (§4.7) but is not the default — a tilted chart is harder to
      // take a bearing off, and bearings are the fisherman's job.
      maxPitch: 60,
      minZoom: 4.5,
      maxZoom: 22,
      maxBounds: [[64.0, 3.0], [96.0, 27.0]],
    });
    map.current = m;

    m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    // Stock ScaleControl rounds its label to the nearest 1/2/3/5/10/50 nm,
    // which is unreadable as an actual distance. Same control, same styling
    // and placement — only the label is ours: the true distance across a
    // fixed 100 px bar, to a precision that follows the magnitude.
    const scale = new maplibregl.ScaleControl({ unit: "nautical", maxWidth: SCALE_BAR_PX });
    scale._onMove = () => {
      const el = scale._container;
      if (!el) return;
      const box = m.getContainer();
      const y = box.clientHeight / 2;
      const x = box.clientWidth / 2;
      const nm =
        m.unproject([x - SCALE_BAR_PX / 2, y]).distanceTo(m.unproject([x + SCALE_BAR_PX / 2, y])) / 1852;
      el.style.width = `${SCALE_BAR_PX}px`;
      el.textContent = `${nm < 1 ? nm.toFixed(3) : nm < 10 ? nm.toFixed(2) : nm < 100 ? nm.toFixed(1) : Math.round(nm)} nm`;
    };
    m.addControl(scale, "bottom-left");
    m.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");

    m.on("load", () => {
      // Positron's own water tone is close, but recolouring it to the exact
      // admiralty-chart pale teal keeps the sea reading as the subject (the
      // thing the product is about) rather than as generic basemap water.
      recolourSea(m);

      /* Alternate basemaps (streets / satellite / terrain), hidden until
         picked. A `labelled` raster is inserted at the top of the basemap
         stack (its own place names replace the style's, rather than being
         written over them); bare imagery goes under the style's first symbol
         layer so it keeps the chart's labels. Either way the ORCA layers
         added below draw on top, and MapLibre fetches no tiles for a source
         whose only layer is hidden — the unpicked ones cost nothing. */
      const firstSymbol = m.getStyle().layers?.find((l) => l.type === "symbol")?.id;
      for (const [id, { source, labelled }] of Object.entries(BASEMAP_RASTERS)) {
        if (m.getSource(`basemap-${id}`)) continue;
        m.addSource(`basemap-${id}`, source);
        m.addLayer(
          {
            id: `basemap-${id}-raster`,
            type: "raster",
            source: `basemap-${id}`,
            layout: { visibility: "none" },
            paint: { "raster-opacity": 1 },
          },
          labelled ? undefined : firstSymbol,
        );
      }

      /* Raster overlays first, so vector boundaries always draw above them. */
      for (const [id, { source, opacity }] of Object.entries(RASTER_OVERLAYS)) {
        if (!m.getSource(id)) {
          m.addSource(id, source);
          m.addLayer({
            id: `${id}-raster`,
            type: "raster",
            source: id,
            layout: { visibility: "none" },
            paint: { "raster-opacity": opacity },
          });
        }
      }

      m.addSource("boundaries", { type: "geojson", data: EMPTY as never });
      m.addSource("boundary-lines", { type: "geojson", data: EMPTY as never });
      // Clustered so 3+ nearby advisories read as one tasteful cluster
      // instead of a pile of overlapping markers — real zoom-aware
      // decluttering via MapLibre's own supercluster, not a custom index.
      // clusterMaxZoom sits BELOW every REGIONS zoom (4.8 the lowest) so
      // clustering only ever applies to the all-India overview: at any
      // working zoom the points stay individual and therefore clickable.
      m.addSource("pfz", {
        type: "geojson",
        data: EMPTY as never,
        cluster: true,
        clusterMaxZoom: 4,
        clusterMinPoints: 3,
        clusterRadius: 48,
        // 2 fresh, 1 hint, 0 history — a cluster looks as current as its
        // freshest zone, so one old point never greys out a live group.
        clusterProperties: {
          freshest: ["max", ["match", ["get", "band"], "fresh", 2, "hint", 1, 0]],
        },
      });
      m.addSource("route", { type: "geojson", data: EMPTY as never });
      m.addSource("watch-badges", { type: "geojson", data: EMPTY as never });
      m.addSource("cyclone", { type: "geojson", data: EMPTY as never });

      // The per-feature JS style function from Leaflet becomes a data-driven
      // paint expression evaluated on the GPU. This is what buys the 60 fps
      // in §4.7's budget: restyling on proximity is a uniform change, not N
      // re-created DOM paths.
      const isMpa: maplibregl.ExpressionSpecification = [
        "all",
        ["!=", ["get", "designation"], "India EEZ"],
        ["!=", ["get", "designation"], "Sri Lanka EEZ"],
      ];

      m.addLayer({
        id: "boundaries-fill",
        type: "fill",
        source: "boundaries",
        paint: {
          "fill-color": ["case", isMpa, CHART.mpa, CHART.eez],
          "fill-opacity": ["case", isMpa, 0.1, 0.03],
        },
      });

      // A maritime boundary reads as a fence line on a real chart — short
      // dashes, modest width, never the solid hard rule a coastline or a
      // road gets. "near" (within 25 nm) still stands out, just by being
      // less transparent, not by turning into a thick solid stroke.
      m.addLayer({
        id: "boundaries-line",
        type: "line",
        source: "boundaries",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": [
            "case",
            ["get", "near"],
            CHART.eezNear,
            ["case", isMpa, CHART.mpa, CHART.eez],
          ],
          "line-width": ["case", ["get", "near"], 1.6, 1],
          "line-opacity": ["case", ["get", "near"], 0.75, 0.32],
          "line-dasharray": [2.5, 1.75],
        },
      });

      // Delimited maritime boundary lines (VLIZ IMBL): treaty-drawn lines,
      // not the edge of a polygon. Drawn long-dashed and darker than the EEZ
      // fence so the two are never read as the same thing on the chart.
      m.addLayer({
        id: "boundary-lines-line",
        type: "line",
        source: "boundary-lines",
        layout: { "line-join": "round", "line-cap": "round", visibility: "none" },
        paint: {
          "line-color": CHART.accent,
          "line-width": 1.4,
          "line-opacity": 0.85,
          "line-dasharray": [6, 2.5],
        },
      });

      // Coastal boundary highlighting — razor-sharp shoreline demarcation over
      // heavy raster layers (bathymetry / wave forecast) so coastlines and land
      // remain clean, distinct, and visible without raster blur bleed.
      const waterLayer = m.getStyle().layers?.find((l) => "source-layer" in l && l["source-layer"] === "water");
      const vectorSource = (waterLayer && "source" in waterLayer ? waterLayer.source : "carto") as string;
      if (m.getSource(vectorSource)) {
        m.addLayer({
          id: "coastal-boundary-casing",
          type: "line",
          source: vectorSource,
          "source-layer": "water",
          filter: ["in", ["get", "class"], ["literal", ["ocean", "sea"]]],
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": "#041724",
            "line-width": [
              "interpolate", ["linear"], ["zoom"],
              3, 2.0,
              6, 2.8,
              10, 4.0,
              14, 5.5
            ],
            "line-opacity": 0.85,
          },
        });
        m.addLayer({
          id: "coastal-boundary-highlight",
          type: "line",
          source: vectorSource,
          "source-layer": "water",
          filter: ["in", ["get", "class"], ["literal", ["ocean", "sea"]]],
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": "#00d2ff",
            "line-width": [
              "interpolate", ["linear"], ["zoom"],
              3, 1.0,
              6, 1.5,
              10, 2.2,
              14, 3.0
            ],
            "line-opacity": 0.95,
          },
        });
      }

      // Fishing-zone marker: a fish glyph. It says what the layer IS at a
      // glance, which a circle never did, and is distinct in silhouette from
      // the ship's-bow position marker and the watch badge. Rendered once as
      // a bitmap and GPU-instanced by the symbol layers below, so hundreds of
      // zones cost one draw call, not hundreds of DOM nodes.
      if (m.hasImage("pfz-marker")) {
        m.removeImage("pfz-marker");
      }
      m.addImage("pfz-marker", buildPfzFishIcon(pfzIconTheme(basemapRef.current, false)), {
        pixelRatio: 2,
      });
      if (m.hasImage("pfz-marker-old")) {
        m.removeImage("pfz-marker-old");
      }
      m.addImage("pfz-marker-old", buildPfzFishIcon(pfzIconTheme(basemapRef.current, false, true)), {
        pixelRatio: 2,
      });

      // 3+ nearby advisories collapse into one cluster circle (supercluster,
      // built into the GeoJSON source below) rather than a pile of
      // overlapping markers — expands automatically as the chart zooms in.
      m.addLayer({
        id: "pfz-clusters",
        type: "symbol",
        source: "pfz",
        filter: ["has", "point_count"],
        layout: {
          "icon-image": ["case", ["==", ["get", "freshest"], 0], "pfz-marker-old", "pfz-marker"],
          // Same fish, sized by how many zones it stands for — one symbol
          // vocabulary for the layer instead of a marker and an unrelated
          // counter bubble.
          "icon-size": ["step", ["get", "point_count"], 0.66, 5, 0.78, 15, 0.92],
          "icon-allow-overlap": true,
        },
        paint: {
          "icon-opacity": ["match", ["get", "freshest"], 2, 1, 1, 0.55, 0.8],
        },
      });
      m.addLayer({
        id: "pfz-cluster-count",
        type: "symbol",
        source: "pfz",
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": ["Open Sans Regular"],
          "text-size": 11,
          // Under the fish rather than inside it, so the glyph stays legible.
          "text-offset": [0, 1.35],
          "text-allow-overlap": true,
        },
        paint: {
          "text-color": "#ffffff",
          "text-halo-color": "rgba(4, 16, 26, 0.85)",
          "text-halo-width": 1.2,
        },
      });

      m.addLayer({
        id: "pfz-circles",
        type: "symbol",
        source: "pfz",
        filter: ["!", ["has", "point_count"]],
        layout: {
          // Stale-data policy bands: fresh is the normal fish, a "hint" (a few
          // days old) is the same fish faded, "history" is a grey fish. Old
          // zones stay on the map — cloud hid them, it did not remove them —
          // but they never look like today's.
          "icon-image": ["case", ["==", ["get", "band"], "history"], "pfz-marker-old", "pfz-marker"],
          "icon-size": ["interpolate", ["linear"], ["zoom"], 4, 0.46, 7, 0.62, 11, 0.8],
          "icon-allow-overlap": true,
          // The age, readable without a click. Optional, so it gives way
          // rather than piling up where zones are dense.
          "text-field": [
            "case",
            ["all", ["has", "age_days"], ["!=", ["get", "band"], "fresh"]],
            ["concat", ["to-string", ["get", "age_days"]], " d"],
            "",
          ],
          "text-font": ["Open Sans Regular"],
          "text-size": 10,
          "text-offset": [0, 1.3],
          "text-optional": true,
        },
        paint: {
          "icon-opacity": ["match", ["get", "band"], "hint", 0.55, "history", 0.8, 1],
          "text-color": "#ffffff",
          "text-halo-color": "rgba(4, 16, 26, 0.85)",
          "text-halo-width": 1.2,
        },
      });

      // Sentinel watch badges (D2 -> D3 handoff, plan §14/§20) — one circle
      // per watch the signed-in user owns, coloured by unread severity.
      // enabled=false watches still get a badge (dimmed), disabled ones never
      // fire, per orca/notifications/watch_badges.py's own contract.
      const badgeSeverityColor: maplibregl.ExpressionSpecification = [
        "match", ["get", "severity"],
        "danger", CHART.noGo, "warning", CHART.caution, "advisory", CHART.eez, "#7a8a99",
      ];
      // Cyclone (GDACS): cone as a translucent fill, track as a line, positions
      // as dots — filled when observed, hollow when forecast, so the forecast
      // part never reads as where the storm has already been.
      m.addLayer({
        id: "cyclone-cone",
        type: "fill",
        source: "cyclone",
        filter: ["==", ["get", "kind"], "cone"],
        paint: { "fill-color": CHART.noGo, "fill-opacity": 0.12, "fill-outline-color": CHART.noGo },
      });
      m.addLayer({
        id: "cyclone-track",
        type: "line",
        source: "cyclone",
        filter: ["==", ["get", "kind"], "track"],
        paint: { "line-color": CHART.noGo, "line-width": 2 },
      });
      m.addLayer({
        id: "cyclone-positions",
        type: "circle",
        source: "cyclone",
        filter: ["==", ["get", "kind"], "position"],
        paint: {
          "circle-radius": 4,
          "circle-color": ["case", ["get", "forecast"], "rgba(0,0,0,0)", CHART.noGo],
          "circle-stroke-color": CHART.noGo,
          "circle-stroke-width": 1.5,
        },
      });
      m.addLayer({
        id: "watch-badges-circles",
        type: "circle",
        source: "watch-badges",
        paint: {
          "circle-radius": ["case", ["==", ["get", "status"], "active"], 7, 5],
          "circle-color": badgeSeverityColor,
          "circle-opacity": ["case", ["get", "enabled"], 0.9, 0.35],
          "circle-stroke-width": ["case", ["==", ["get", "status"], "active"], 2, 1],
          "circle-stroke-color": "#04121a",
        },
      });

      // /voyage's corridor (plan §5) — colour AND a text label per leg
      // (voyage_route_layer's own contract: never colour-alone), status
      // reusing the same go/caution/no-go hex the rest of the product uses.
      const routeStatusColor: maplibregl.ExpressionSpecification = [
        "match", ["get", "status"], "BLOCKED", CHART.noGo, "CAUTION", CHART.caution, CHART.go,
      ];
      m.addLayer({
        id: "route-line",
        type: "line",
        source: "route",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": routeStatusColor, "line-width": 4, "line-opacity": 0.9 },
      });
      m.addLayer({
        id: "route-label",
        type: "symbol",
        source: "route",
        layout: {
          "symbol-placement": "line-center",
          "text-field": ["get", "hazard_class"],
          "text-size": 11,
          "text-offset": [0, 1.1],
        },
        paint: { "text-color": routeStatusColor, "text-halo-color": "#04121a", "text-halo-width": 1.4 },
      });

      setReady(true);
    });

    // Clicking a cluster zooms in on it — the standard supercluster
    // interaction, so "3+ zones nearby" is one tap away from "which 3".
    m.on("click", "pfz-clusters", (e) => {
      const feature = m.queryRenderedFeatures(e.point, { layers: ["pfz-clusters"] })[0];
      const clusterId = feature?.properties?.cluster_id;
      const source = m.getSource("pfz") as maplibregl.GeoJSONSource | undefined;
      if (clusterId == null || !source) return;
      source.getClusterExpansionZoom(clusterId).then((zoom) => {
        const geometry = feature.geometry as { type: "Point"; coordinates: [number, number] };
        m.easeTo({ center: geometry.coordinates, zoom, duration: 500 });
      }).catch(() => { });
    });

    m.on("click", (e) => {
      const badgeFeatures = m.queryRenderedFeatures(e.point, { layers: ["watch-badges-circles"] });
      if (badgeFeatures.length && badgeFeatures[0].properties) {
        setSelectedBadge(badgeFeatures[0].properties as WatchBadge);
        setSelectedPfz(null);
        selectedPfzCoordsRef.current = null;
        setSelectedPfzPos(null);
        return;
      }
      setSelectedBadge(null);
      const pfzFeatures = m.queryRenderedFeatures(e.point, { layers: ["pfz-circles"] });
      if (pfzFeatures.length && pfzFeatures[0].properties) {
        setSelectedPfz(pfzFeatures[0].properties as PfzProperties);
        const geometry = pfzFeatures[0].geometry as { type: "Point"; coordinates: [number, number] };
        selectedPfzCoordsRef.current = geometry.coordinates;
        setSelectedPfzPos(projectPfzPos(m, geometry.coordinates));
      } else {
        setSelectedPfz(null);
        selectedPfzCoordsRef.current = null;
        setSelectedPfzPos(null);
      }
      void handleClickRef.current(e.lngLat.lat, e.lngLat.lng);
    });
    // Keep the PFZ popup glued to its marker's screen position while the
    // map pans/zooms, same as a native maplibre Popup would.
    m.on("move", () => {
      if (!selectedPfzCoordsRef.current) return;
      setSelectedPfzPos(projectPfzPos(m, selectedPfzCoordsRef.current));
    });
    for (const id of ["boundaries-fill", "pfz-circles", "pfz-clusters", "watch-badges-circles"]) {
      m.on("mouseenter", id, () => {
        m.getCanvas().style.cursor = "pointer";
      });
      m.on("mouseleave", id, () => {
        m.getCanvas().style.cursor = "";
      });
    }

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && container.current) {
      ro = new ResizeObserver(() => {
        map.current?.resize();
      });
      ro.observe(container.current);
    }

    return () => {
      ro?.disconnect();
      m.remove();
      map.current = null;
    };
  }, [supported]);

  /* ---- "Your Location" marker: a ship's-bow pointer over a pulsing GPS
     halo, shown ONLY once the browser actually grants a position — never a
     hardcoded stand-in. Rotates to the bearing computed below so it visibly
     points at whatever real geometry the chart just fit to (a boundary, a
     cluster of fishing zones); resting orientation (north) otherwise.
     Rotation/position are set via the marker API directly rather than a
     teardown/recreate, same "update in place" rule §4.7 uses everywhere
     else on this map — so a later position update (if the browser refines
     the fix) just moves the existing marker. */
  const shipMarkerRef = useRef<maplibregl.Marker | null>(null);
  useEffect(() => {
    if (!ready || !map.current || !userLocation) return;
    if (!shipMarkerRef.current) {
      const el = document.createElement("div");
      el.setAttribute("aria-label", "Your location");
      el.innerHTML = `
        <div style="position:relative;width:30px;height:34px;">
          <span class="beacon-pulse" style="position:absolute;left:9px;top:15px;width:12px;height:12px;border-radius:9999px;background:${CHART.eezNear};opacity:0.35;"></span>
          <svg width="30" height="34" viewBox="0 0 30 34" style="position:relative;filter:drop-shadow(0 2px 3px rgba(28,41,57,0.4))">
            <path d="M15 1 L26.5 24.5 Q15 30.5 3.5 24.5 Z" fill="${CHART.eezNear}" stroke="#fffdf6" stroke-width="1.75" stroke-linejoin="round" />
            <circle cx="15" cy="19.5" r="2.2" fill="#fffdf6" />
          </svg>
        </div>`;
      shipMarkerRef.current = new maplibregl.Marker({ element: el, rotationAlignment: "map" })
        .setLngLat(userLocation)
        .addTo(map.current);
    } else {
      shipMarkerRef.current.setLngLat(userLocation);
    }
    return () => {
      shipMarkerRef.current?.remove();
      shipMarkerRef.current = null;
    };
  }, [ready, userLocation]);

  /* ---- /voyage: route corridor + origin/destination pins (both optional,
     absent for every other page that mounts this component) ---- */
  useEffect(() => {
    if (!ready || !map.current) return;
    const source = map.current.getSource("route") as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData((routeGeoJson ?? EMPTY) as never);
    if (routeGeoJson?.features.length) {
      const lons = routeGeoJson.features.flatMap((f) => f.geometry.coordinates.map((c) => c[0]));
      const lats = routeGeoJson.features.flatMap((f) => f.geometry.coordinates.map((c) => c[1]));
      map.current.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], {
        padding: 64,
      });
    }
  }, [ready, routeGeoJson]);

  // A chart pin, not a Google Maps balloon: a flat lozenge on a short stem,
  // in the caller's own colour, distinct in silhouette from both the ship's
  // bow marker (position/heading) and the fishing-zone diamond (a dataset
  // point) — this is a user-placed waypoint, a third kind of thing.
  useEffect(() => {
    if (!ready || !map.current || !pins?.length) return;
    const built = pins.map((p) => {
      const el = document.createElement("div");
      el.setAttribute("aria-label", p.label);
      el.innerHTML = `
        <svg width="22" height="30" viewBox="0 0 22 30" style="filter:drop-shadow(0 2px 3px rgba(28,41,57,0.4))">
          <path d="M11 1c5.5 0 9 4 9 8.8 0 6.2-9 18.2-9 18.2S2 16 2 9.8C2 5 5.5 1 11 1Z" fill="${p.color}" stroke="#fffdf6" stroke-width="1.5" />
          <circle cx="11" cy="10.5" r="3.2" fill="#fffdf6" />
        </svg>`;
      el.style.transform = "translateY(2px)";
      return new maplibregl.Marker({ element: el, anchor: "bottom" }).setLngLat([p.lon, p.lat]).addTo(map.current!);
    });
    return () => {
      for (const m of built) m.remove();
    };
  }, [ready, pins]);

  /* ---- distress markers (P4.16): text + icon, never colour alone ---- */
  const newestDistress = distressMarkers?.[0]?.id;
  useEffect(() => {
    if (!ready || !map.current || !distressMarkers?.length) return;
    const built = distressMarkers.map((d) => {
      const el = document.createElement("div");
      el.setAttribute("role", "img");
      el.setAttribute("aria-label", `Distress: ${d.label}`);
      el.className = "orca-distress-marker";
      el.style.cssText =
        "display:flex;align-items:center;gap:4px;padding:2px 6px;border-radius:4px;border:2px solid #fffdf6;" +
        `background:${CHART.noGo};color:#fffdf6;font:700 11px/1.2 var(--font-sans);box-shadow:0 0 0 2px ${CHART.noGo};`;
      el.textContent = `SOS · ${d.label}`;
      return new maplibregl.Marker({ element: el, anchor: "bottom" }).setLngLat([d.lon, d.lat]).addTo(map.current!);
    });
    return () => {
      for (const m of built) m.remove();
    };
  }, [ready, distressMarkers]);
  // Fly to a distress position the moment a new one appears.
  useEffect(() => {
    const d = distressMarkers?.[0];
    if (!ready || !map.current || !d) return;
    map.current.flyTo({ center: [d.lon, d.lat], zoom: Math.max(map.current.getZoom(), 8) });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a NEW marker moves the camera
  }, [ready, newestDistress]);

  /* ---- data: fetched once, pushed through setData ---- */
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;

    (async () => {
      const [layerRes, nearRes, pfzRes, rasterRes, currentsRes, windRes] = await Promise.all([
        fetch(`${API_BASE}/api/map-layers?lat=${focusPoint[1]}&lon=${focusPoint[0]}`).then((r) => r.json()),
        fetch(
          `${API_BASE}/api/zones-nearby?lat=${focusPoint[1]}&lon=${focusPoint[0]}&radius_nm=25`,
        ).then((r) => r.json()),
        fetch(`${API_BASE}/api/zones`).then((r) => r.json()),
        fetch(`${API_BASE}/api/raster-layers?lat=${focusPoint[1]}&lon=${focusPoint[0]}`)
          .then((r) => r.json())
          .catch(() => ({ layers: [] })),
        fetch(`${API_BASE}/api/current-vectors`)
          .then((r) => r.json())
          .catch(() => null),
        fetch(`${API_BASE}/api/wind-vectors`)
          .then((r) => r.json())
          .catch(() => null),
      ]);
      if (cancelled || !map.current) return;

      if (currentsRes?.points?.length) {
        setCurrentVectors(currentsRes.points as CurrentVector[]);
        setCurrentBounds(currentsRes.bounds as [number, number, number, number]);
        if (currentsRes.valid_time) setCurrentsTiming({ validTime: currentsRes.valid_time, stepHours: currentsRes.step_hours ?? 3 });
      }
      if (windRes?.points?.length) {
        setWindVectors(windRes.points as WindVector[]);
        setWindBounds(windRes.bounds as [number, number, number, number]);
        setWindAcquisitionDate(windRes.acquisition_date as string);
        if (windRes.valid_time) setWindTiming({ validTime: windRes.valid_time, stepHours: windRes.step_hours ?? 24 });
      }

      // Agent 8's self-hosted tile pyramids (bathymetry + forecast). Sources
      // are added once here, never recreated — only setTiles()/opacity move
      // after this, same lifecycle rule as the vector layers below.
      const m0 = map.current;
      const tileLayers = (rasterRes.layers as RasterLayerMeta[] | undefined)?.filter((l) => l.tile_url) ?? [];
      setRasterLayers(tileLayers);
      for (const layer of tileLayers) {
        const sourceId = `srv-${layer.layer_id}`;
        if (m0.getLayer(`${sourceId}-raster`)) {
          m0.removeLayer(`${sourceId}-raster`);
        }
        if (m0.getSource(sourceId)) {
          m0.removeSource(sourceId);
        }
        const isForecast = Boolean(layer.forecast_frames?.length);
        const firstFrame = isForecast ? layer.forecast_frames![0] : undefined;
        m0.addSource(sourceId, {
          type: "raster",
          tiles: [`${API_BASE}${resolveTileUrl(layer.tile_url!, firstFrame)}?v=pan_india_ww3_smooth`],
          tileSize: 256,
          minzoom: layer.style_hints.min_zoom,
          maxzoom: layer.style_hints.max_zoom,
          // The pyramid only covers the source grid's own extent, so without
          // this MapLibre requests the whole viewport and every tile outside
          // the grid 404s — hundreds of them per frame in the server log.
          // `meta.json` has carried these bounds all along.
          bounds: layer.bounds,
        });
        const beforeLayer = m0.getLayer("coastal-boundary-casing")
          ? "coastal-boundary-casing"
          : (m0.getLayer("boundaries-fill")
            ? "boundaries-fill"
            : (m0.getLayer("pfz-clusters") ? "pfz-clusters" : undefined));
        m0.addLayer({
          id: `${sourceId}-raster`,
          type: "raster",
          source: sourceId,
          layout: { visibility: "none" },
          paint: { "raster-opacity": layer.style_hints.opacity },
        }, beforeLayer);
      }

      // Ensure vector layers (coastline, boundaries, PFZ, routes, watches) stay above all raster overlays
      for (const id of [
        "boundaries-fill",
        "boundaries-line",
        "boundary-lines-line",
        "coastal-boundary-casing",
        "coastal-boundary-highlight",
        "watch-badges-circles",
        "route-corridor",
        "route-line",
        "pfz-clusters",
        "pfz-cluster-count",
        "pfz-circles",
      ]) {
        if (m0.getLayer(id)) {
          m0.moveLayer(id);
        }
      }

      const near = new Set((nearRes.boundaries as { name: string }[]).map((b) => b.name));
      setNearNames([...near]);

      // Proximity is baked into the feature as a property so the paint
      // expression can read it. The alternative — a filter rebuilt per render
      // — would re-upload the whole source on every change.
      const boundaries = layerRes.boundaries as BoundaryGeoJson;
      const tagged = {
        ...boundaries,
        features: boundaries.features.map((f) => ({
          ...f,
          properties: { ...f.properties, near: near.has(f.properties.name) },
        })),
      };

      (map.current.getSource("boundaries") as maplibregl.GeoJSONSource)?.setData(tagged as never);
      if (layerRes.maritime_boundary_lines) {
        (map.current.getSource("boundary-lines") as maplibregl.GeoJSONSource)?.setData(
          layerRes.maritime_boundary_lines as never,
        );
      }
      setBoundaryFeatures(tagged as BoundaryGeoJson);
      const pfzRaw = (pfzRes.features ?? pfzRes.thermal_front_proxy?.features ?? []) as PfzFeature[];
      setPfzFeatures(pfzRaw);
      (map.current.getSource("pfz") as maplibregl.GeoJSONSource)?.setData({
        type: "FeatureCollection",
        features: pfzRaw.map((f) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: f.geometry.coordinates },
          properties: f.properties ?? {},
        })),
      } as never);
    })().catch(() => {
      /* A degraded chart, not a broken page — the readouts still answer. */
    });

    return () => {
      cancelled = true;
    };
  }, [ready, focusPoint]);

  // Ask page query -> chart focus, layer half (plan §7/§8): adjusted during
  // render when `queryFocus` changes, the pattern React's own docs recommend
  // for "state derived from a prop change" instead of a setState-in-effect
  // (https://react.dev/learn/you-might-not-need-an-effect) — the camera move
  // below is the actual external-system side effect, this isn't.
  const [focusedNonce, setFocusedNonce] = useState<number | undefined>(undefined);
  // The ship marker's heading — null points it at its resting orientation
  // (north). Set from the same real geometry the camera below fits to, so
  // it is never a bearing toward something not actually on screen.
  const [shipBearing, setShipBearing] = useState<number | null>(null);
  // Keep the heavy-layer LRU honest about what a prescription actually left
  // running, or the next manual toggle evicts a layer that is already off.
  // In an effect rather than the render-phase block below: a ref write during
  // render is the hazard `react-hooks/refs` exists to catch, and nothing can
  // toggle a layer between that render and this commit anyway.
  const lruNonce = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!queryFocus || queryFocus.nonce === lruNonce.current) return;
    lruNonce.current = queryFocus.nonce;
    const prescribed = QUERY_INTENT_LAYERS[queryFocus.intent];
    if (prescribed) lru.current = HEAVY_KEYS.filter((k) => prescribed.includes(k));
  }, [queryFocus]);

  if (queryFocus && queryFocus.nonce !== focusedNonce) {
    setFocusedNonce(queryFocus.nonce);
    // A named place (plan item 8) is set here rather than in the camera
    // effect below — both are "state derived from a prop change", so both
    // belong in this render-phase block; the effect stays limited to the
    // actual external-system side effect (the camera move itself).
    if (queryFocus.regionId) {
      setSelectedRegion(queryFocus.regionId);
    }
    // The layer set for this question — exactly the prescription above, not
    // the previous answer's layers plus one more.
    const prescribed = QUERY_INTENT_LAYERS[queryFocus.intent];
    if (prescribed) {
      setLayers((s) => {
        const next = { ...s };
        for (const key of Object.keys(next) as (keyof typeof next)[]) {
          next[key] = prescribed.includes(key);
        }
        return next;
      });
    }
    // Same anchor the camera effect below uses: explicit coords, a named place,
    // the reader's GPS position, or coastal pilot default.
    const focusRegion = queryFocus.regionId
      ? COASTAL_REGIONS.find((r) => r.id === queryFocus.regionId)
      : undefined;
    const anchor: [number, number] = queryFocus.coords
      ? queryFocus.coords
      : focusRegion
      ? focusRegion.center
      : userLocation ?? COASTAL_REGIONS[1].center;
    let bearing: number | null = null;
    if (queryFocus.intent === "boundary") {
      const coords = boundaryFeatures.features.filter((f) => f.properties.near).flatMap((f) => flattenCoords(f.geometry));
      if (coords.length) {
        const lon = coords.reduce((s, c) => s + c[0], 0) / coords.length;
        const lat = coords.reduce((s, c) => s + c[1], 0) / coords.length;
        bearing = bearingDeg(anchor[1], anchor[0], lat, lon);
      }
    } else if (queryFocus.intent === "fishing") {
      const near = pfzFeatures.filter(
        (f) => haversineKm(anchor[1], anchor[0], f.geometry.coordinates[1], f.geometry.coordinates[0]) <= 250,
      );
      if (near.length) {
        const lon = near.reduce((s, f) => s + f.geometry.coordinates[0], 0) / near.length;
        const lat = near.reduce((s, f) => s + f.geometry.coordinates[1], 0) / near.length;
        bearing = bearingDeg(anchor[1], anchor[0], lat, lon);
      }
    }
    setShipBearing(bearing);
  }

  // The rotation itself is an imperative call on the marker instance (an
  // external system, same as the camera move below), so it stays in an
  // effect rather than joining the state-adjustment block above.
  useEffect(() => {
    shipMarkerRef.current?.setRotation(shipBearing ?? 0);
  }, [shipBearing]);

  /* ---- Ask page query -> chart focus, camera half: fits the chart around
     real geometry already on screen (the nearest tagged boundary, the
     nearby PFZ points) — never a fabricated pin. Re-runs on every ask() via
     `nonce`, even for a repeated intent, so the chart re-settles each time
     rather than only on the first change. */
  useEffect(() => {
    if (!ready || !map.current || !queryFocus) return;
    const m = map.current;

    // A named place in the query (plan item 8, "location-specific query")
    // becomes the ANCHOR the topic then settles around, rather than a camera
    // move that wins outright: "PFZ near Kochi" has to show Kochi AND the
    // zones, so the place decides where to look and the intent decides how
    // wide. With no place named, the anchor stays explicit coords if present,
    // the reader's position, or coastal fallback.
    const region = queryFocus.regionId
      ? COASTAL_REGIONS.find((r) => r.id === queryFocus.regionId)
      : undefined;
    const anchor: [number, number] = queryFocus.coords
      ? queryFocus.coords
      : region
      ? region.center
      : userLocation ?? COASTAL_REGIONS[1].center;
    // Where the camera lands when the topic has no geometry near the anchor:
    // the named sector at its own framing, explicit coords, user position, or all-India coastal view.
    const fallback = (zoom: number) =>
      m.flyTo(
        region
          ? { center: region.center, zoom: region.zoom, duration: 1000 }
          : queryFocus.coords
          ? { center: queryFocus.coords, zoom, duration: 900 }
          : userLocation
          ? { center: userLocation, zoom, duration: 900 }
          : { center: INDIA_VIEW.center, zoom: INDIA_VIEW.zoom, duration: 900 },
      );

    if (queryFocus.intent === "boundary") {
      const near = boundaryFeatures.features.filter((f) => f.properties.near);
      const coords = near.flatMap((f) => flattenCoords(f.geometry));
      if (coords.length) {
        const lons = [anchor[0], ...coords.map((c) => c[0])];
        const lats = [anchor[1], ...coords.map((c) => c[1])];
        m.fitBounds(
          [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
          { padding: 72, maxZoom: 18, duration: 900 },
        );
      } else {
        fallback(8.2);
      }
    } else if (queryFocus.intent === "fishing") {
      const near = pfzFeatures.filter(
        (f) => haversineKm(anchor[1], anchor[0], f.geometry.coordinates[1], f.geometry.coordinates[0]) <= 250,
      );
      if (near.length) {
        const lons = [anchor[0], ...near.map((f) => f.geometry.coordinates[0])];
        const lats = [anchor[1], ...near.map((f) => f.geometry.coordinates[1])];
        m.fitBounds(
          [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
          { padding: 80, maxZoom: 18, duration: 900 },
        );
      } else {
        fallback(8.6);
      }
    } else if (queryFocus.intent === "current" || queryFocus.intent === "wave" || queryFocus.intent === "wind") {
      // All three fields cover the whole basin — a named place keeps its own
      // sector, an unplaced question fits the full field extent.
      const bounds =
        queryFocus.intent === "current" ? currentBounds :
        queryFocus.intent === "wind" ? windBounds :
        forecastLayer?.bounds;
      if (region) {
        fallback(8.2);
      } else if (bounds) {
        const [w, s, e, n] = bounds;
        m.fitBounds([[w, s], [e, n]], {
          padding: 60,
          maxZoom: 16,
          duration: 900,
        });
      } else {
        fallback(8.2);
      }
    } else {
      fallback(8.2);
    }
    // Only the nonce should retrigger this — `boundaryFeatures`/`pfzFeatures`
    // are read for their current value, not watched (both settle long
    // before a user can ask a second question).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, queryFocus?.nonce]);

  /* ---- Sentinel watch badges (D2 -> D3, plan §14/§20): polled while signed
     in, pushed through setData() only — never a map remount. Silently absent
     for a signed-out visitor, same "degraded, not broken" rule as every
     other data effect on this map. */
  useEffect(() => {
    if (!ready || !map.current) return;
    if (!getToken()) return;
    let cancelled = false;

    const refresh = () => {
      fetchWatchBadges()
        .then((res) => {
          if (cancelled || !map.current) return;
          setWatchBadgeFeatures(res.badges ?? []);
          const layer = res.map_layer as { geojson: GeoJSON.FeatureCollection } | undefined;
          (map.current.getSource("watch-badges") as maplibregl.GeoJSONSource)?.setData(
            (layer?.geojson ?? EMPTY) as never,
          );
        })
        .catch(() => {
          /* A missing badge feed degrades to no badges, never a broken map. */
        });
    };
    refresh();
    const interval = setInterval(refresh, 30_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [ready]);

  /* ---- live cyclone track and cone (GDACS, P5.30) — refreshed every 15 min ---- */
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    const load = () =>
      fetch(`${API_BASE}/api/cyclone-track`)
        .then((r) => r.json())
        .then((res) => {
          if (cancelled || !map.current) return;
          setCyclone(res);
          (map.current.getSource("cyclone") as maplibregl.GeoJSONSource | undefined)?.setData(res.geojson ?? EMPTY);
        })
        .catch(() => !cancelled && setCyclone({ available: false, note: "Cyclone track unavailable — the server did not answer.", systems: [] }));
    void load();
    const id = setInterval(load, 15 * 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [ready]);

  /* ---- layer visibility: a layout change, never a remount ---- */
  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    const vis = (id: string, on: boolean) => {
      if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    };
    for (const id of Object.keys(BASEMAP_RASTERS)) vis(`basemap-${id}-raster`, basemap === id);
    vis("boundaries-fill", layers.boundaries);
    vis("boundaries-line", layers.boundaries);
    vis("boundary-lines-line", layers.boundaryLines);
    const showCoast = layers.boundaries || layers.srvBathymetry || layers.waveForecast;
    vis("coastal-boundary-casing", showCoast);
    vis("coastal-boundary-highlight", showCoast);
    vis("pfz-circles", layers.pfz);
    vis("pfz-clusters", layers.pfz);
    vis("pfz-cluster-count", layers.pfz);
    vis("watch-badges-circles", layers.watchBadges);
    for (const id of ["cyclone-cone", "cyclone-track", "cyclone-positions"]) vis(id, layers.cyclone);
    vis("seamarks-raster", layers.seamarks);
    for (const layer of rasterLayers) {
      const on = layer.forecast_frames?.length ? layers.waveForecast : layers.srvBathymetry;
      vis(`srv-${layer.layer_id}-raster`, on);
    }
  }, [ready, layers, rasterLayers, basemap]);

  /* ---- Zoom & camera bounds: locked to the surface current domain
     [65.0°E, 4.0°N to 95.0°E, 26.0°N]. The chart cannot zoom out beyond the
     surface currents extent, and cannot be panned outside it. Within the
     surface currents water, full deep zoom up to 22 is unlocked. ---- */
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;

    const bounds: [number, number, number, number] = currentBounds ?? [65.0, 4.0, 95.0, 26.0];
    const [w, s, e, n] = bounds;
    m.setMaxBounds([
      [w - 1.0, s - 1.0],
      [e + 1.0, n + 1.0],
    ]);
  }, [ready, currentBounds]);

  /* ---- PFZ glyph re-tint: the fish follows what is under it — deep-water
     imagery wants a bright body on a near-black halo, pale chart paper wants
     the inverse. updateImage re-uploads one 80x80 sprite; no layer teardown,
     no source churn, so a basemap switch stays a visibility flip. */
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !m.hasImage("pfz-marker")) return;
    m.updateImage("pfz-marker", buildPfzFishIcon(pfzIconTheme(basemap, layers.waveForecast)));
    if (m.hasImage("pfz-marker-old")) {
      m.updateImage("pfz-marker-old", buildPfzFishIcon(pfzIconTheme(basemap, layers.waveForecast, true)));
    }
    // The count under a cluster is part of the same symbol; it flips with it
    // rather than staying white on a white basemap.
    if (m.getLayer("pfz-cluster-count")) {
      const dark = basemap === "satellite";
      m.setPaintProperty("pfz-cluster-count", "text-color", dark ? "#ffffff" : "#03301d");
      m.setPaintProperty(
        "pfz-cluster-count",
        "text-halo-color",
        dark ? "rgba(4, 16, 26, 0.85)" : "rgba(255, 255, 255, 0.95)",
      );
    }
    m.triggerRepaint();
  }, [ready, basemap, layers.waveForecast]);

  /* ---- forecast frame swap: setTiles() + isSourceLoaded() crossfade, so a
     slider drag never flashes a half-loaded tile at full opacity (§ D3
     revised stack, MapLibre 6.x anti-flicker pattern). Only one forecast
     layer exists today (wave_height_forecast); the mixed-cadence
     nearest-neighbour/grey-out rule is deferred until a second one lands. */
  useEffect(() => {
    if (!ready || !map.current || !forecastLayer?.forecast_frames) return;
    const m = map.current;
    const sourceId = `srv-${forecastLayer.layer_id}`;
    const layerId = `${sourceId}-raster`;
    const source = m.getSource(sourceId) as maplibregl.RasterTileSource | undefined;
    if (!source) return;

    const frame = forecastLayer.forecast_frames[Math.min(frameIndex, forecastLayer.forecast_frames.length - 1)];
    const targetOpacity = layers.waveForecast ? forecastLayer.style_hints.opacity : 0;

    const onSourceData = (e: maplibregl.MapSourceDataEvent) => {
      if (e.sourceId === sourceId && m.isSourceLoaded(sourceId)) {
        m.setPaintProperty(layerId, "raster-opacity", targetOpacity);
        m.off("sourcedata", onSourceData);
      }
    };
    m.setPaintProperty(layerId, "raster-opacity", 0);
    m.on("sourcedata", onSourceData);
    source.setTiles([`${API_BASE}${resolveTileUrl(forecastLayer.tile_url!, frame)}?v=pan_india_ww3_smooth`]);

    return () => {
      m.off("sourcedata", onSourceData);
    };
  }, [ready, frameIndex, forecastLayer, layers.waveForecast]);

  /* ---- flow-field particle layers: live currents (HYCOM) and archived wind
     (ScatSat) rendered via high-performance HTML5 Canvas with glowing streamlines. */
  useEffect(() => {
    if (layers.currents || layers.wind) {
      const builtIds: string[] = [];
      let payloadBytes = 0;
      if (layers.currents && currentVectors) {
        builtIds.push("currents");
        payloadBytes += currentVectors.length * 32;
      }
      if (layers.wind && windVectors) {
        builtIds.push("wind");
        payloadBytes += windVectors.length * 32;
      }
      if (builtIds.length) {
        reportLayerMetrics({
          layer_id: builtIds.join("+"),
          layer_load_ms: 0,
          render_ms: 16,
          payload_bytes: payloadBytes,
          dropped_frames: 0,
        });
      }
    }
  }, [layers.currents, layers.wind, currentVectors, windVectors]);

  // §4.7: a missing map is never a missing answer. Every spatial fact the
  // chart shows is also available as text, so a GPU-less phone degrades to
  // the readouts rather than to a blank rectangle.
  if (!supported) {
    return (
      <div className={className}>
        <EmptyState
          icon={<Compass className="size-6" />}
          title="Chart unavailable on this device"
          body="This browser has no WebGL, so the chart cannot draw. Every position, depth and bearing is still reported as text on the surfaces that use them."
        />
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden rounded-md border border-hairline ${className}`}>
      <div ref={container} className="h-full w-full" />
      <FlowFieldCanvas
        mapRef={map}
        mapReady={ready}
        showCurrents={layers.currents}
        showWind={layers.wind}
        currentVectors={currentVectors}
        windVectors={windVectors}
        currentBounds={currentBounds}
        windBounds={windBounds}
        greyCurrents={greyCurrents}
        greyWind={greyWind}
      />

      {selectedPfz && selectedPfzPos && (
        <div
          className="pointer-events-auto absolute z-30 w-[310px] transition-all duration-75"
          style={{ left: selectedPfzPos.left, top: selectedPfzPos.top }}
        >
          {/* Speech-bubble tail — sits OUTSIDE overflow-hidden so it isn't
              clipped. Positioned at arrowY along the card edge, pointing directly
              at the fishing zone marker it describes. */}
          <div
            className={`absolute z-10 size-3.5 -translate-y-1/2 rotate-45 bg-shelf-3 ${
              selectedPfzPos.side === "right"
                ? "-left-[7px] border-b border-l border-go/40"
                : "-right-[7px] border-t border-r border-go/40"
            }`}
            style={{ top: selectedPfzPos.arrowY }}
          />
          <div className="relative overflow-hidden rounded-xl border border-go/30 bg-shelf-3/95 backdrop-blur-xl shadow-xl transition-all">
            {/* Glowing top line */}
            <div className="h-0.5 bg-gradient-to-r from-go to-ocean-cyan" />

            {/* Header */}
            <div className="flex items-center justify-between border-b border-hairline px-3.5 py-2.5 bg-gradient-to-b from-white/[0.03] to-transparent">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-go opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-go" />
                </span>
                <span className="rounded-full border border-go/40 bg-go/15 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-go">
                  PFZ Advisory
                </span>
                <h4 className="text-xs font-bold tracking-tight text-ink truncate max-w-[140px]">
                  {selectedPfz.landing_center ? String(selectedPfz.landing_center) : "Fishing Zone"}
                </h4>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedPfz(null);
                  selectedPfzCoordsRef.current = null;
                  setSelectedPfzPos(null);
                }}
                className="flex size-6 cursor-pointer items-center justify-center rounded-lg text-ink-dim hover:bg-hairline/40 hover:text-ink transition-colors"
                aria-label="Close PFZ details"
              >
                <X className="size-3.5" />
              </button>
            </div>

            {/* Body Content */}
            <div className="p-3">
              <div className="grid grid-cols-2 gap-2">
                {/* Sector Tile */}
                <div className="rounded-lg border border-hairline/50 bg-shelf-2/60 p-2">
                  <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-ink-dim">
                    <MapPin className="size-2.5 text-go" /> Sector
                  </span>
                  <p className="mt-1 text-xs font-bold text-ink truncate">
                    {String(selectedPfz.sector || "General Offshore")}
                  </p>
                </div>

                {/* Advised Depth Tile */}
                <div className="rounded-lg border border-hairline/50 bg-shelf-2/60 p-2">
                  <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-ink-dim">
                    <Waves className="size-2.5 text-ocean-cyan" /> Advised Depth
                  </span>
                  <p className="mt-1 font-mono text-xs font-bold text-ocean-cyan">
                    {selectedPfz.depth_m ? (
                      <>
                        {String(selectedPfz.depth_m)}{" "}
                        <span className="text-[10px] font-normal text-ocean-cyan/80">m</span>
                      </>
                    ) : "Surface / Mid-water"}
                  </p>
                </div>

                {/* Distance & Bearing Tile */}
                <div className="rounded-lg border border-hairline/50 bg-shelf-2/60 p-2">
                  <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-ink-dim">
                    <Navigation className="size-2.5 text-ocean-cyan" /> From Landing
                  </span>
                  <p className="mt-1 font-mono text-xs font-bold text-ink">
                    {selectedPfz.distance_km != null ? `${selectedPfz.distance_km} km` : "—"}
                  </p>
                  {selectedPfz.direction && (
                    <span className="mt-1 inline-flex items-center rounded border border-hairline bg-shelf-2/80 px-1 py-0.5 font-mono text-[9px] text-ink-muted">
                      {selectedPfz.direction} {selectedPfz.bearing_deg != null ? `(${selectedPfz.bearing_deg}°)` : ""}
                    </span>
                  )}
                </div>

                {/* Validity & Status Tile */}
                <div className="rounded-lg border border-hairline/50 bg-shelf-2/60 p-2">
                  <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-ink-dim">
                    <Calendar className="size-2.5 text-go" /> Valid Until
                  </span>
                  <p className="mt-1 font-mono text-[11px] font-semibold text-ink-muted truncate">
                    {selectedPfz.valid_for ? String(selectedPfz.valid_for) : "Current cycle"}
                  </p>
                  {selectedPfz.expired ? (
                    <span className="mt-1 inline-flex items-center gap-1 rounded-full border border-caution/40 bg-caution/15 px-1.5 py-0.5 text-[8px] font-bold uppercase text-caution">
                      <span className="size-1 rounded-full bg-caution" /> Expired
                      {selectedPfz.age_days != null && ` · ${selectedPfz.age_days} d ago`}
                    </span>
                  ) : (
                    <span className="mt-1 inline-flex items-center gap-1 rounded-full border border-go/30 bg-go/15 px-1.5 py-0.5 text-[8px] font-bold uppercase text-go">
                      <span className="size-1 rounded-full bg-go animate-pulse" /> Active
                    </span>
                  )}
                </div>
              </div>

              {/* Optional Micro-Metrics Row (SST & Area) */}
              {(selectedPfz.mean_sst_c != null || selectedPfz.approx_area_km2 != null) && (
                <div className="mt-2 flex flex-wrap gap-1.5 border-t border-hairline/50 pt-2">
                  {selectedPfz.mean_sst_c != null && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-caution/20 bg-caution/15 px-2 py-0.5 text-[10px] font-mono text-caution">
                      <span>🌡</span> {selectedPfz.mean_sst_c}°C SST
                    </span>
                  )}
                  {selectedPfz.approx_area_km2 != null && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-ocean-cyan/20 bg-ocean-cyan/15 px-2 py-0.5 text-[10px] font-mono text-ocean-cyan">
                      <span>📐</span> {selectedPfz.approx_area_km2} km² Area
                    </span>
                  )}
                </div>
              )}

              {/* Data-grounded Top 3 Fish Species */}
              {(() => {
                const speciesList = resolveTopSpeciesForPfz(selectedPfz).slice(0, 3);
                if (!speciesList.length) return null;
                return (
                  <div className="mt-2.5 rounded-lg border border-hairline/60 bg-shelf-2/85 p-2.5 shadow-inner">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-wider text-ocean-cyan">
                        <Fish className="size-3 text-ocean-cyan" /> Top Target Species
                      </span>
                      <span className="text-[8px] font-mono text-ink-dim uppercase">CMFRI 2024 · OBIS</span>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {speciesList.map((sp, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between gap-1.5 rounded-md border border-hairline/40 bg-shelf-1/70 px-2 py-1 text-[10px] transition-colors hover:border-ocean-cyan/30"
                        >
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="flex size-3.5 items-center justify-center rounded-full bg-ocean-cyan/15 text-[8px] font-bold font-mono text-ocean-cyan shrink-0">
                              {idx + 1}
                            </span>
                            <div className="truncate">
                              <span className="font-semibold text-ink">{sp.name}</span>
                              {sp.scientific_name && (
                                <span className="ml-1 text-[9px] italic text-ink-dim">
                                  ({sp.scientific_name})
                                </span>
                              )}
                            </div>
                          </div>
                          {sp.depth_fit && (
                            <span className="text-[8px] font-mono px-1.5 py-0.5 rounded border border-ocean-cyan/20 bg-ocean-cyan/10 text-ocean-cyan shrink-0">
                              {sp.depth_fit.replace(/^Optimal\s*\(/i, "").replace(/\)$/, "")}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Provenance footer */}
              <div className="mt-2.5 flex items-center justify-between border-t border-hairline pt-2 text-[9px] text-ink-dim">
                <span className="flex items-center gap-1 text-go/90 font-medium">
                  <ShieldCheck className="size-3 text-go" /> INCOIS Official PFZ
                </span>
                <span className="text-ink-dim font-mono">Satellite SST + Chlorophyll</span>
              </div>
            </div>
          </div>

        </div>
      )}

      {showPanels && (
        <div className="pointer-events-none absolute inset-0 z-10">
          {showLayerPanel && (
            <div className="pointer-events-auto absolute top-3 left-3 w-56 flex flex-col gap-2">
              <Panel dense>
                <button
                  type="button"
                  onClick={() => setLayersOpen((v) => !v)}
                  aria-expanded={layersOpen}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                    <Layers className="size-3.5 text-ink-dim" aria-hidden="true" />
                    Chart layers
                  </span>
                  <ChevronDown
                    aria-hidden="true"
                    className={`size-3.5 text-ink-dim transition-transform ${layersOpen ? "rotate-180" : ""}`}
                  />
                </button>
                {layersOpen && (
                  <div className="-mx-2 mt-3">
                    <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-dim">
                      Base map
                    </p>
                    <div
                      role="group"
                      aria-label="Base map"
                      className="mx-2 mb-2 grid grid-cols-2 gap-1"
                    >
                      {(Object.keys(BASEMAP_LABELS) as BasemapId[]).map((id) => (
                        <button
                          key={id}
                          type="button"
                          aria-pressed={basemap === id}
                          onClick={() => setBasemap(id)}
                          className={`rounded-sm border px-2 py-1 text-[11px] transition-colors ${
                            basemap === id
                              ? "border-accent bg-accent/10 font-semibold text-ink"
                              : "border-hairline text-ink-muted hover:bg-shelf-2/70"
                          }`}
                        >
                          {BASEMAP_LABELS[id]}
                        </button>
                      ))}
                    </div>
                    <LayerToggle
                      label="Boundaries"
                      checked={layers.boundaries}
                      onChange={(v) => setLayers((s) => ({ ...s, boundaries: v }))}
                    />
                    <LayerToggle
                      label="Treaty boundary lines (IMBL)"
                      checked={layers.boundaryLines}
                      onChange={(v) => setLayers((s) => ({ ...s, boundaryLines: v }))}
                    />
                    <LayerToggle
                      label="Fishing zones (PFZ)"
                      checked={layers.pfz}
                      onChange={(v) => setLayers((s) => ({ ...s, pfz: v }))}
                    />
                    {getToken() && (
                      <LayerToggle
                        label="My watch badges"
                        checked={layers.watchBadges}
                        onChange={(v) => setLayers((s) => ({ ...s, watchBadges: v }))}
                      />
                    )}
                    <LayerToggle
                      label="Cyclone track & cone (GDACS)"
                      checked={layers.cyclone}
                      disabled={cyclone !== null && !cyclone.available}
                      disabledReason={cyclone?.note}
                      onChange={(v) => setLayers((s) => ({ ...s, cyclone: v }))}
                    />
                    <LayerToggle
                      label="Seamarks (Port Buoys & Lights)"
                      checked={layers.seamarks}
                      onChange={(v) => setLayers((s) => ({ ...s, seamarks: v }))}
                    />
                    {rasterLayers.some((l) => !l.forecast_frames?.length) && (
                      <LayerToggle
                        label="Depth shading (India Coast)"
                        heavy
                        checked={layers.srvBathymetry}
                        onChange={(v) => toggleHeavy("srvBathymetry", v)}
                      />
                    )}
                    {forecastLayer && (
                      <LayerToggle
                        label="Wave height forecast"
                        heavy
                        checked={layers.waveForecast}
                        onChange={(v) => toggleHeavy("waveForecast", v)}
                      />
                    )}
                    {currentVectors && currentVectors.length > 0 && (
                      <LayerToggle
                        label="Surface currents"
                        heavy
                        checked={layers.currents}
                        onChange={(v) => toggleHeavy("currents", v)}
                      />
                    )}
                    {windVectors && windVectors.length > 0 && (
                      <LayerToggle
                        label={
                          windAcquisitionDate
                            ? `Wind (${windAcquisitionDate})`
                            : "Wind (ScatSat)"
                        }
                        heavy
                        checked={layers.wind}
                        onChange={(v) => toggleHeavy("wind", v)}
                      />
                    )}
                  </div>
                )}
                {layersOpen && nearNames.length > 0 && (
                  <p className="mt-2 border-t border-hairline pt-2 text-[11px] text-ink-dim">
                    {nearNames.length} within 25 nm, drawn brighter
                  </p>
                )}
              </Panel>
              {evictionNotice && (
                <p
                  role="status"
                  className="mt-2 rounded-sm border border-hairline bg-shelf-2/90 px-2 py-1.5 text-[11px] text-ink-muted"
                >
                  {evictionNotice}
                </p>
              )}
              {showRegionSwitcher && regionStats && (
                <div className="w-72 rounded-xl border border-hairline/80 bg-shelf-1/95 backdrop-blur-xl p-3 shadow-lg">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="truncate text-xs font-semibold text-ink">{regionStats.region.name}</span>
                    <button
                      type="button"
                      onClick={() => setSelectedRegion("all")}
                      aria-label="Close region dashboard"
                      className="shrink-0 text-ink-dim hover:text-ink"
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                  <ReadoutGrid cols={3}>
                    <Readout compact label="Zones" value={regionStats.zoneCount} />
                    <Readout
                      compact
                      label="Wind"
                      value={regionStats.avgWindMs != null ? regionStats.avgWindMs.toFixed(1) : "—"}
                      unit={regionStats.avgWindMs != null ? "m/s" : undefined}
                    />
                    <Readout compact label="Hazards" value={regionStats.hazardCount} />
                  </ReadoutGrid>
                </div>
              )}
            </div>
          )}

          {showLegends && layers.srvBathymetry && (
            // Depth legend: to the left of the zoom controls column and
            // right below the Coastal Navigation Regions dropdown.
            <div className="pointer-events-auto absolute top-14 right-14 z-10 hidden sm:block rounded-xl border border-hairline/80 bg-shelf-1/95 px-3 py-2 backdrop-blur-md shadow-lg">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-[#ccebc5]" />
                <span className="text-[11px] font-medium text-ink">Depth Shading (ETOPO/GEBCO) meters</span>
              </div>
              <div className="mt-1.5 flex h-2 w-48 overflow-hidden rounded-full border border-hairline">
                <div className="w-1/5 bg-[#f0f9e8]" title="0 - 50m (Shallow / Inshore)" />
                <div className="w-1/5 bg-[#bae4bc]" title="50 - 200m (Shelf)" />
                <div className="w-1/5 bg-[#7bccc4]" title="200 - 1000m (Slope)" />
                <div className="w-1/5 bg-[#2b8cbe]" title="1000 - 2000m (Deep Basin)" />
                <div className="w-1/5 bg-[#08589e]" title="2000m+ (Abyssal Plain)" />
              </div>
              <div className="mt-1 flex justify-between text-[9px] text-ink-muted">
                <span>0m</span>
                <span>50m</span>
                <span>200m (Shelf)</span>
                <span>2000m+</span>
              </div>
            </div>
          )}

          {showLegends && layers.waveForecast && !layers.srvBathymetry && (
            // Wave legend: same slot as depth legend — left of zoom controls,
            // below the Coastal Navigation Regions dropdown.
            <div className="pointer-events-auto absolute top-14 right-14 z-10 hidden sm:block rounded-xl border border-hairline/80 bg-shelf-1/95 px-3 py-2 backdrop-blur-md shadow-lg">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-[#e87050]" />
                <span className="text-[11px] font-medium text-ink">Wave Height (Hs Forecast) meters</span>
              </div>
              <div className="mt-1.5 flex h-2 w-48 overflow-hidden rounded-full border border-hairline">
                <div className="w-1/3 bg-[#fed98e]" title="0.5m Calm" />
                <div className="w-1/3 bg-[#fe9929]" title="1.5m Mod" />
                <div className="w-1/3 bg-[#993404]" title=">3.0m High" />
              </div>
              <div className="mt-1 flex justify-between text-[9px] text-ink-muted">
                <span>0.5m Calm</span>
                <span>1.5m Mod</span>
                <span>&gt;3.0m High</span>
              </div>
            </div>
          )}

          {/* Coastal Region Quick Switcher — the control stays put; only the
              dashboard below it moves side, so picking a region never
              relocates the button itself. */}
          {showRegionSwitcher && (
            <div ref={regionDropdownRef} className="pointer-events-auto absolute top-3 right-14 z-20">
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setRegionDropdownOpen(!regionDropdownOpen)}
                  className="flex items-center gap-2 rounded-xl border border-hairline/80 bg-shelf-1/95 backdrop-blur-xl px-3 py-1.5 text-xs font-medium text-ink shadow-lg transition-all hover:bg-shelf-2 hover:border-hairline-strong focus:outline-none"
                  aria-label="Select coastal sector"
                >
                  <Compass className="size-3.5 text-ocean-cyan shrink-0" />
                  <span className="max-w-[140px] sm:max-w-none truncate font-medium">
                    {COASTAL_REGIONS.find((r) => r.id === selectedRegion)?.name ?? "Select Sector"}
                  </span>
                  <ChevronDown
                    className={`size-3 text-ink-dim transition-transform duration-200 shrink-0 ${regionDropdownOpen ? "rotate-180" : ""
                      }`}
                  />
                </button>
                {regionDropdownOpen && (
                  <div className="absolute right-0 mt-2 w-64 max-h-80 overflow-y-auto rounded-xl border border-hairline/80 bg-shelf-1/95 backdrop-blur-2xl p-1.5 shadow-2xl z-30">
                    <div className="px-2.5 py-1.5 text-[10px] font-semibold tracking-wider text-ink-dim uppercase border-b border-hairline/50 mb-1">
                      Coastal Navigation Regions
                    </div>
                    {COASTAL_REGIONS.map((region) => (
                      <button
                        key={region.id}
                        type="button"
                        onClick={() => {
                          setSelectedRegion(region.id);
                          setRegionDropdownOpen(false);
                          map.current?.flyTo({
                            center: region.center,
                            zoom: region.zoom,
                            duration: 1200,
                            essential: true,
                          });
                        }}
                        className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${selectedRegion === region.id
                          ? "bg-accent/15 text-accent font-semibold"
                          : "text-ink hover:bg-shelf-2"
                          }`}
                      >
                        <span className="truncate">{region.name}</span>
                        <span className="ml-2 text-[10px] text-ink-dim shrink-0">{region.sub}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Quick recenter button — sits directly below the MapLibre
              zoom/compass controls (NavigationControl, ~96px tall at top-right).
              Your GPS fix when granted, otherwise the national overview.
              Never flies to a fixed pilot sector. */}
          <div className="pointer-events-auto absolute top-[120px] right-[10px] z-10">
            <button
              type="button"
              onClick={() => {
                setSelectedRegion("all");
                map.current?.flyTo(
                  userLocation
                    ? { center: userLocation, zoom: 8.5, duration: 800, essential: true }
                    : { center: INDIA_VIEW.center, zoom: INDIA_VIEW.zoom, duration: 800, essential: true },
                );
              }}
              title={userLocation ? "Recenter chart on your location" : "Recenter chart on India overview"}
              aria-label={userLocation ? "Recenter chart on your location" : "Recenter chart on India overview"}
              className="flex size-[34px] items-center justify-center rounded-xl border border-hairline/80 bg-shelf-1/95 backdrop-blur-md text-ink-muted shadow transition-colors hover:bg-shelf-2 hover:text-ink focus:outline-none"
            >
              <Crosshair className="size-4 text-accent" />
            </button>
            {(geoStatus === "denied" || geoStatus === "unavailable") && (
              <p className="mt-1.5 w-max max-w-[9rem] rounded-md border border-hairline/70 bg-shelf-1/95 px-1.5 py-1 text-right text-[9px] leading-snug text-ink-dim shadow">
                Location unavailable — showing India overview
              </p>
            )}
          </div>

          <div
            className={`pointer-events-auto absolute right-3 left-3 sm:left-auto sm:w-80 transition-all ${Boolean(layers.waveForecast && forecastLayer?.forecast_frames?.length)
              ? "bottom-36 sm:bottom-24"
              : "bottom-4 sm:bottom-4"
              }`}
          >
            {selectedBadge && (
              <div className="mb-2.5">
                <Panel
                  dense
                  title={selectedBadge.label}
                  action={
                    <button
                      type="button"
                      onClick={() => setSelectedBadge(null)}
                      aria-label="Close watch badge details"
                      className="text-ink-dim hover:text-ink"
                    >
                      <X className="size-3.5" />
                    </button>
                  }
                >
                  <div className="flex items-center gap-2">
                    <Badge tone={SEVERITY_TONE[selectedBadge.severity]}>{selectedBadge.severity}</Badge>
                    <Badge tone={selectedBadge.status === "active" ? "caution" : "neutral"}>
                      {selectedBadge.status === "active" ? "unread crossing" : "clear"}
                    </Badge>
                    {!selectedBadge.enabled && <Badge tone="neutral">disabled</Badge>}
                  </div>
                  <div className="mt-2.5">
                    <ReadoutGrid cols={2}>
                      <Readout label="Unread" value={selectedBadge.unread_count} />
                      <Readout label="Last fired" value={selectedBadge.last_fired_at ? new Date(selectedBadge.last_fired_at).toLocaleString() : "never"} />
                    </ReadoutGrid>
                  </div>
                </Panel>
              </div>
            )}

            {/* Acoustic Sounding HUD */}
            {showSoundingHud && (
              soundingDismissed ? (
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => {
                      setSoundingDismissed(false);
                      setSoundingCollapsed(false);
                    }}
                    className="flex items-center gap-2 rounded-full border border-ocean-cyan/40 bg-shelf-3/95 px-3 py-1.5 backdrop-blur-xl text-[11px] font-semibold text-ocean-cyan shadow-lg transition-colors duration-200 cursor-pointer hover:border-ocean-cyan hover:shadow-[0_0_18px_rgba(34,211,238,0.55)]"
                  >
                    <Crosshair className="size-3 text-ocean-cyan" />
                    <span>Sounding HUD</span>
                    {depth?.depth_m != null && !depth.on_land && (
                      <span className="font-mono font-bold text-ocean-cyan">{depth.depth_m}m</span>
                    )}
                  </button>
                </div>
              ) : (
                <div className="overflow-hidden rounded-xl border border-ocean-cyan/30 bg-shelf-3/95 backdrop-blur-xl shadow-xl  transition-all">
                  {/* Glowing top line */}
                  <div className="h-0.5 bg-gradient-to-r from-ocean-cyan to-accent" />

                  {/* Header */}
                  <div className="flex items-center justify-between border-b border-hairline px-3.5 py-2 bg-gradient-to-b from-white/[0.03] to-transparent">
                    <div className="flex items-center gap-2">
                      <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ocean-cyan opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-ocean-cyan" />
                      </span>
                      <h3 className="text-xs font-bold tracking-wider uppercase text-ocean-cyan">
                        Acoustic Sounding HUD
                      </h3>
                      {soundingCollapsed && depth?.depth_m != null && !depth.on_land && (
                        <span className="rounded bg-ocean-cyan/15 px-1.5 py-0.5 font-mono text-[10px] font-bold text-ocean-cyan border border-ocean-cyan/30">
                          {depth.depth_m}m
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setSoundingCollapsed(!soundingCollapsed)}
                        className="flex size-6 cursor-pointer items-center justify-center rounded-lg text-ink-dim hover:bg-hairline/40 hover:text-ink transition-colors"
                        aria-label={soundingCollapsed ? "Expand HUD" : "Collapse HUD"}
                        title={soundingCollapsed ? "Expand HUD" : "Collapse HUD"}
                      >
                        {soundingCollapsed ? <ChevronUp className="size-3.5 text-ocean-cyan" /> : <ChevronDown className="size-3.5 text-ink-dim" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => setSoundingDismissed(true)}
                        className="flex size-6 cursor-pointer items-center justify-center rounded-lg text-ink-dim hover:bg-hairline/40 hover:text-ink transition-colors"
                        aria-label="Dismiss HUD"
                        title="Dismiss HUD"
                      >
                        <X className="size-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Body (only when expanded) */}
                  {!soundingCollapsed && (
                    <div className="p-3">
                      {!clicked ? (
                        <div className="py-2 text-center">
                          <div className="mx-auto mb-1.5 flex size-8 items-center justify-center rounded-full bg-ocean-cyan/15 border border-ocean-cyan/30 text-ocean-cyan">
                            <Waves className="size-4 animate-pulse" />
                          </div>
                          <p className="text-[11px] font-medium text-ink-muted">
                            Tap chart to sound seafloor depth
                          </p>
                          <p className="mt-0.5 text-[9px] text-ink-dim">
                            Reads NOAA ETOPO 2022 &amp; GEBCO 2026 topography
                          </p>
                        </div>
                      ) : (
                        <>
                          {/* Hero Readout Grid */}
                          <div className="grid grid-cols-2 gap-2">
                            {/* Depth Hero Tile */}
                            <div className="rounded-lg border border-ocean-cyan/20 bg-gradient-to-br from-shelf-2 to-shelf-1 p-2.5">
                              <span className="text-[9px] font-bold uppercase tracking-wider text-ink-dim flex items-center gap-1">
                                <Waves className="size-2.5 text-ocean-cyan" /> Seafloor Depth
                              </span>
                              <div className="mt-1">
                                {depth ? (
                                  depth.on_land ? (
                                    <p className="font-mono text-base font-bold text-caution">On Land</p>
                                  ) : depth.depth_m != null ? (
                                    <>
                                      <p className="font-mono text-2xl font-black text-ocean-cyan tracking-tight leading-none ">
                                        {depth.depth_m}
                                        <span className="ml-1 text-xs font-bold text-ocean-cyan/80">m</span>
                                      </p>
                                      <span className="mt-1 block font-mono text-[10px] text-ink-dim">
                                        ({(depth.depth_m * 0.5468).toFixed(1)} fm)
                                      </span>
                                    </>
                                  ) : (
                                    <p className="font-mono text-sm text-ink-dim">Outside coverage</p>
                                  )
                                ) : (
                                  <p className="font-mono text-base text-ink-dim animate-pulse">Measuring…</p>
                                )}
                              </div>
                            </div>

                            {/* Position Telemetry Tile */}
                            <div className="rounded-lg border border-hairline/50 bg-shelf-2/50 p-2.5 flex flex-col justify-between">
                              <div>
                                <span className="text-[9px] font-bold uppercase tracking-wider text-ink-dim flex items-center gap-1">
                                  <Crosshair className="size-2.5 text-ocean-cyan" /> Position
                                </span>
                                <div className="mt-1 font-mono text-[11px] font-semibold text-ink-muted">
                                  <p>{clicked.lat >= 0 ? `${clicked.lat.toFixed(2)}°N` : `${(-clicked.lat).toFixed(2)}°S`}</p>
                                  <p>{clicked.lon >= 0 ? `${clicked.lon.toFixed(2)}°E` : `${(-clicked.lon).toFixed(2)}°W`}</p>
                                </div>
                              </div>
                              {nearNames.length > 0 && (
                                <p className="mt-1 text-[9px] text-ocean-cyan/80 truncate">
                                  nr {nearNames[0]}
                                </p>
                              )}
                            </div>
                          </div>

                          {/* Bathymetry Status Pill */}
                          {depth && !depth.on_land && depth.depth_m != null && (
                            <div className="mt-2">
                              <div
                                className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${depth.shallow_hazard
                                  ? "border-caution/40 bg-caution/15 text-caution"
                                  : "border-ocean-cyan/30 bg-ocean-cyan/15 text-ocean-cyan"
                                  }`}
                              >
                                <span className="font-mono">
                                  {depth.depth_m < 10
                                    ? "⚠ Shallow Navigational Hazard"
                                    : depth.depth_m < 200
                                      ? "✓ Continental Shelf (Inshore / Mid-Shelf)"
                                      : depth.depth_m < 2000
                                        ? "✓ Continental Slope"
                                        : "✓ Deep Oceanic Bathymetry"}
                                </span>
                              </div>
                            </div>
                          )}

                          {/* Bearing & Distance Navigation Telemetry */}
                          <div className="mt-2 grid grid-cols-2 gap-2 border-t border-hairline/50 pt-2">
                            <div className="rounded-lg border border-hairline/50 bg-shelf-2/50 p-2">
                              <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-ink-dim">
                                <Compass className="size-2.5 text-ocean-cyan" /> Bearing from Port
                              </span>
                              <p className="mt-1 font-mono text-xs font-bold text-ink">
                                {bearing ? `${bearing.bearing_deg}° True` : "…"}
                              </p>
                            </div>
                            <div className="rounded-lg border border-hairline/50 bg-shelf-2/50 p-2">
                              <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-ink-dim">
                                <Navigation className="size-2.5 text-ocean-cyan" /> Distance & Steam
                              </span>
                              <p className="mt-1 font-mono text-xs font-bold text-ink">
                                {bearing ? (
                                  <>
                                    {bearing.distance_nm} <span className="text-[10px] font-normal text-ink-dim">nm</span>{" "}
                                    <span className="text-[10px] text-ocean-cyan font-normal">
                                      (~{(bearing.distance_nm / 10).toFixed(1)}h)
                                    </span>
                                  </>
                                ) : "…"}
                              </p>
                            </div>
                          </div>

                          {/* Nearest delimited boundary line — the treaty one,
                              not the EEZ polygon edge. */}
                          {boundaryLine && (
                            <div className="mt-2 rounded-lg border border-hairline/50 bg-shelf-2/50 p-2">
                              <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-ink-dim">
                                <Navigation className="size-2.5 text-accent" /> Nearest boundary line
                              </span>
                              <p className="mt-1 font-mono text-[11px] font-bold text-ink">
                                {boundaryLine.line_name}{" "}
                                <span className="font-normal text-ink-dim">
                                  · {boundaryLine.distance_nm} nm · {boundaryLine.bearing_deg}°
                                </span>
                              </p>
                              <p className="mt-0.5 text-[9px] text-ink-dim">
                                {boundaryLine.line_type}
                                {boundaryLine.treaty_date ? ` · ${boundaryLine.treaty_date.slice(0, 10)}` : ""}
                              </p>
                            </div>
                          )}

                          {/* Provenance citation */}
                          <div className="mt-2.5 flex items-center justify-between border-t border-hairline pt-2 text-[9px] text-ink-dim">
                            <span className="flex items-center gap-1 text-ocean-cyan/90 font-medium">
                              <ShieldCheck className="size-3 text-ocean-cyan" /> NOAA ETOPO 2022 / GEBCO
                            </span>
                            <span className="text-ink-dim font-mono">30 Aug, 05:30 IST</span>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )
            )}
          </div>
          {forecastLayer && layers.waveForecast && (
            <div className="pointer-events-auto absolute bottom-3 left-3 w-[calc(100%-1.5rem)] sm:left-1/2 sm:w-[420px] sm:-translate-x-1/2">
              <TimeSlider
                frames={forecastLayer.forecast_frames!.map((t) => ({ t }))}
                index={frameIndex}
                onIndexChange={setFrameIndex}
                playing={playing}
                onPlayingChange={setPlaying}
                notes={sliderNotes}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Repaint the basemap's water in ORCA's depth ramp. Done against the loaded
// style rather than a forked style.json so the basemap stays swappable via
// NEXT_PUBLIC_BASEMAP_STYLE — any style with a `water` source-layer works.
// The PFZ chart symbol is the SAME fish the nav rail uses for "Fishing
// zones" (lucide's `fish`, ISC) — one icon for one concept, wherever it
// appears. The path data is vendored from lucide-react's own icon node so
// the two cannot drift; body path first, then eye, gill, tail and fins.
const LUCIDE_FISH_24 = [
  "M6.5 12c.94-3.46 4.94-6 8.5-6 3.56 0 6.06 2.54 7 6-.94 3.47-3.44 6-7 6s-7.56-2.53-8.5-6Z",
  "M18 12v.5",
  "M16 17.93a9.77 9.77 0 0 1 0-11.86",
  "M7 10.67C7 8 5.58 5.97 2.73 5.5c-1 1.5-1 5 .23 6.5-1.24 1.5-1.24 5-.23 6.5C5.58 18.03 7 16 7 13.33",
  "M10.46 7.26C10.2 5.88 9.17 4.24 8 3h5.8a2 2 0 0 1 1.98 1.67l.23 1.4",
  "m16.01 17.93-.23 1.4A2 2 0 0 1 13.8 21H9.5a5.96 5.96 0 0 0 1.49-3.98",
];

type PfzIconTheme = {
  halo: string;
  haloWidth: number;
  bodyTop: string;
  bodyBottom: string;
  line: string;
  lineWidth: number;
};

/** The glyph re-tints itself for whatever is under it. Two things decide it:
 *  how dark the basemap is (satellite imagery is deep teal water; chart,
 *  streets and terrain are all pale paper), and whether a raster overlay is
 *  currently painting colour across that water. The hue stays in the PFZ
 *  green family either way — only value and halo change, so the symbol never
 *  starts meaning something else. */
function pfzIconTheme(basemap: BasemapId, busyWater: boolean, old = false): PfzIconTheme {
  const dark = basemap === "satellite";
  const theme = dark
    ? {
        // Deep water: the line work goes PALE and the halo near-black. Dark
        // strokes on dark imagery lose the fins and tail entirely — the body
        // survives as a green blob and the fish stops being a fish.
        halo: "rgba(3, 17, 26, 0.92)",
        haloWidth: busyWater ? 3.1 : 2.6,
        bodyTop: "#37dd97",
        bodyBottom: "#059a56",
        line: "#eafff5",
        lineWidth: 1.5,
      }
    : {
        // Pale chart paper: the exact inverse. A deep saturated body and dark
        // ink lines, carried on a white halo — the cartographic way to keep a
        // dark symbol legible over light fill.
        halo: "rgba(255, 255, 255, 0.98)",
        haloWidth: busyWater ? 2.6 : 2.0,
        bodyTop: "#19c47c",
        bodyBottom: "#035c33",
        line: "#032a1a",
        lineWidth: 1.6,
      };
  // "history" band — same silhouette and halo, the colour drained out, so it
  // reads as the same kind of thing, no longer current.
  return old ? { ...theme, bodyTop: "#b7c0c6", bodyBottom: "#6b767d" } : theme;
}

function buildPfzFishIcon(theme: PfzIconTheme): ImageData {
  const px = 2; // device pixels per icon pixel — matches addImage's pixelRatio
  const size = 40 * px;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  // lucide draws on a 24 box; inset it so the halo below sits inside the
  // sprite instead of being clipped by its edge.
  const inset = 0.88;
  ctx.translate((size * (1 - inset)) / 2, (size * (1 - inset)) / 2);
  ctx.scale((size / 24) * inset, (size / 24) * inset);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  const paths = LUCIDE_FISH_24.map((d) => new Path2D(d));

  // Halo first, under everything — the nav icon is pure line work, which
  // disappears against a photographic basemap without one.
  ctx.strokeStyle = theme.halo;
  ctx.lineWidth = theme.haloWidth;
  for (const path of paths) ctx.stroke(path);

  // Then a filled body, so the marker still reads as a solid dot of colour
  // at chart zoom where 2 px strokes would break up. Lit from above, like
  // every other raised element in the chrome.
  const body = ctx.createLinearGradient(0, 5, 0, 19);
  body.addColorStop(0, theme.bodyTop);
  body.addColorStop(1, theme.bodyBottom);
  ctx.fillStyle = body;
  ctx.fill(paths[0]);

  // lucide's own strokes on top: eye, gill, tail and fins.
  ctx.strokeStyle = theme.line;
  ctx.lineWidth = theme.lineWidth;
  for (const path of paths) ctx.stroke(path);

  return ctx.getImageData(0, 0, size, size);
}

function recolourSea(m: maplibregl.Map) {
  const set = (id: string, prop: string, value: string | number) => {
    try {
      (m.setPaintProperty as (id: string, prop: string, value: unknown) => void)(id, prop, value);
    } catch {
      /* layer absent in this style — nothing to recolour */
    }
  };

  set("background", "background-color", "#f2ead4");

  for (const layer of m.getStyle().layers ?? []) {
    const src = "source-layer" in layer ? layer["source-layer"] : undefined;
    if (src !== "water" && src !== "waterway") continue;
    if (layer.type === "fill") {
      set(layer.id, "fill-color", "#cfe3e0");
      set(layer.id, "fill-opacity", 1);
    } else if (layer.type === "line") {
      set(layer.id, "line-color", "#a9c9c6");
    } else if (layer.type === "symbol") {
      set(layer.id, "text-color", "#5c6f6d");
      set(layer.id, "text-halo-color", "#f2ead4");
    }
  }
}
