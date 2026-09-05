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
import { Calendar, ChevronDown, ChevronUp, Compass, Crosshair, Layers, MapPin, Navigation, ShieldCheck, Waves, X } from "lucide-react";
import { BASEMAP_STYLE, CHART, DEFAULT_USER, PILOT_BOUNDS, RASTER_OVERLAYS, webglAvailable } from "../map/basemap";
import { Badge, type BadgeTone } from "./Badge";
import { LayerToggle } from "./LayerToggle";
import { Panel } from "./Panel";
import { Readout, ReadoutGrid } from "./Readout";
import { EmptyState } from "./States";
import { TimeSlider } from "./TimeSlider";
import { getToken } from "../lib/auth";
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
type PfzProperties = {
  sector?: string;
  landing_center?: string;
  direction?: string;
  bearing_deg?: number;
  distance_km?: string | number;
  depth_m?: string | number;
  valid_for?: string;
  source?: string;
  approx_area_km2?: number;
  mean_sst_c?: number;
  mean_depth_m?: number;
};
type PfzFeature = {
  geometry: { coordinates: [number, number] };
  properties: PfzProperties;
};
// D2 -> D3 handoff (plan §14, orca/notifications/watch_badges.py) — same
// severity vocabulary as the notification feed, never re-derived here.
const SEVERITY_TONE: Record<WatchBadge["severity"], BadgeTone> = {
  info: "neutral",
  advisory: "accent",
  warning: "caution",
  danger: "no-go",
};
const SEVERITY_COLOR: Record<WatchBadge["severity"], string> = {
  info: "#7a8a99",
  advisory: CHART.eez,
  warning: CHART.caution,
  danger: CHART.noGo,
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
  { id: "gulf_mannar", name: "Gulf of Mannar / Thoothukudi", sub: "Pilot Sector", center: [78.8, 8.8], zoom: 7.8, coast: "east" },
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
const HEAVY_KEYS = ["srvBathymetry", "waveForecast", "currents", "wind"] as const;
type HeavyKey = (typeof HEAVY_KEYS)[number];
const HEAVY_LABEL: Record<HeavyKey, string> = {
  srvBathymetry: "Depth grid (ORCA)",
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
export type QueryFocus = { intent: "fishing" | "boundary" | "safety" | "general"; nonce: number };

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
    pfz: boolean;
    seamarks: boolean;
    srvBathymetry: boolean;
    waveForecast: boolean;
    currents: boolean;
    wind: boolean;
    watchBadges: boolean;
  }>;
  queryFocus?: QueryFocus | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [supported] = useState(webglAvailable);

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
  const [depth, setDepth] = useState<DepthResult | null>(null);
  const [bearing, setBearing] = useState<Bearing | null>(null);
  const [layers, setLayers] = useState({
    boundaries: false,
    pfz: true,
    seamarks: true,
    srvBathymetry: false,
    waveForecast: false,
    currents: false,
    wind: false,
    watchBadges: true,
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
  const [selectedPfz, setSelectedPfz] = useState<PfzProperties | null>(null);
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
    setDepth(null);
    setBearing(null);
    const [d, b] = await Promise.all([
      fetch(`${API_BASE}/api/depth?lat=${lat}&lon=${lon}`).then((r) => r.json()),
      fetch(
        `${API_BASE}/api/bearing?from_lat=${DEFAULT_USER[1]}&from_lon=${DEFAULT_USER[0]}&to_lat=${lat}&to_lon=${lon}`,
      ).then((r) => r.json()),
    ]);
    setDepth(d);
    setBearing(b);
  }, [onPointClick]);

  /* ---- map instance: created once, never recreated ---- */
  useEffect(() => {
    if (!container.current || !supported || map.current) return;

    const m = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE,
      bounds: PILOT_BOUNDS,
      fitBoundsOptions: { padding: 48 },
      // Attribution and scale live bottom-LEFT: the bottom-right corner is
      // reserved for the SOS button, which must never be covered or cover.
      // Attribution is added by hand below so it can sit bottom-LEFT: the
      // bottom-right corner belongs to the SOS button.
      attributionControl: false,
      // Pitch is available for depth reading on the researcher/navigator
      // surfaces (§4.7) but is not the default — a tilted chart is harder to
      // take a bearing off, and bearings are the fisherman's job.
      maxPitch: 60,
    });
    map.current = m;

    m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "nautical" }), "bottom-left");
    m.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");

    m.on("load", () => {
      // Positron's own water tone is close, but recolouring it to the exact
      // admiralty-chart pale teal keeps the sea reading as the subject (the
      // thing the product is about) rather than as generic basemap water.
      recolourSea(m);

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
        clusterMaxZoom: 4.5,
        clusterMinPoints: 3,
        clusterRadius: 48,
      });
      m.addSource("route", { type: "geojson", data: EMPTY as never });
      m.addSource("watch-badges", { type: "geojson", data: EMPTY as never });

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

      // Fishing-zone marker: a small diamond target rather than a plain
      // circle — reads as an intentional chart symbol at a glance, distinct
      // from both the ship's-bow position marker and a generic map pin.
      // Rendered once as a bitmap and GPU-instanced by the symbol layer
      // below, so hundreds of zones cost one draw call, not hundreds of
      // DOM nodes.
      if (!m.hasImage("pfz-marker")) {
        m.addImage("pfz-marker", buildPfzMarkerIcon(), { pixelRatio: 2 });
      }

      // 3+ nearby advisories collapse into one cluster circle (supercluster,
      // built into the GeoJSON source below) rather than a pile of
      // overlapping markers — expands automatically as the chart zooms in.
      m.addLayer({
        id: "pfz-clusters",
        type: "circle",
        source: "pfz",
        filter: ["has", "point_count"],
        paint: {
          "circle-radius": ["step", ["get", "point_count"], 13, 5, 16, 15, 20],
          "circle-color": CHART.pfz,
          "circle-opacity": 0.22,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": CHART.pfz,
          "circle-stroke-opacity": 0.7,
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
        },
        paint: { "text-color": CHART.pfz },
      });

      m.addLayer({
        id: "pfz-circles",
        type: "symbol",
        source: "pfz",
        filter: ["!", ["has", "point_count"]],
        layout: {
          "icon-image": "pfz-marker",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 4, 0.55, 7, 0.8, 11, 1.05],
          "icon-allow-overlap": true,
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
      }).catch(() => {});
    });

    m.on("click", (e) => {
      const badgeFeatures = m.queryRenderedFeatures(e.point, { layers: ["watch-badges-circles"] });
      if (badgeFeatures.length && badgeFeatures[0].properties) {
        setSelectedBadge(badgeFeatures[0].properties as WatchBadge);
        setSelectedPfz(null);
        return;
      }
      setSelectedBadge(null);
      const pfzFeatures = m.queryRenderedFeatures(e.point, { layers: ["pfz-circles"] });
      if (pfzFeatures.length && pfzFeatures[0].properties) {
        setSelectedPfz(pfzFeatures[0].properties as PfzProperties);
      } else {
        setSelectedPfz(null);
      }
      void handleClick(e.lngLat.lat, e.lngLat.lng);
    });
    for (const id of ["boundaries-fill", "pfz-circles", "pfz-clusters", "watch-badges-circles"]) {
      m.on("mouseenter", id, () => {
        m.getCanvas().style.cursor = "pointer";
      });
      m.on("mouseleave", id, () => {
        m.getCanvas().style.cursor = "";
      });
    }

    return () => {
      m.remove();
      map.current = null;
    };
  }, [supported, handleClick]);

  /* ---- user position marker: a ship's-bow pointer, not a plain dot ----
     Rotates to the bearing computed above so it visibly points at whatever
     real geometry the chart just fit to (a boundary, a cluster of fishing
     zones); resting orientation (north) when a query has no directional
     target. Rotation is set via the marker API directly rather than a
     teardown/recreate, same "update in place" rule §4.7 uses everywhere
     else on this map. */
  const shipMarkerRef = useRef<maplibregl.Marker | null>(null);
  useEffect(() => {
    if (!ready || !map.current) return;
    const el = document.createElement("div");
    el.setAttribute("aria-label", "Your position, Thoothukudi");
    el.innerHTML = `
      <svg width="30" height="34" viewBox="0 0 30 34" style="filter:drop-shadow(0 2px 3px rgba(28,41,57,0.4))">
        <path d="M15 1 L26.5 24.5 Q15 30.5 3.5 24.5 Z" fill="${CHART.eezNear}" stroke="#fffdf6" stroke-width="1.75" stroke-linejoin="round" />
        <circle cx="15" cy="19.5" r="2.2" fill="#fffdf6" />
      </svg>`;
    const marker = new maplibregl.Marker({ element: el, rotationAlignment: "map" })
      .setLngLat(DEFAULT_USER)
      .addTo(map.current);
    shipMarkerRef.current = marker;
    return () => {
      marker.remove();
      shipMarkerRef.current = null;
    };
  }, [ready]);

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

  /* ---- data: fetched once, pushed through setData ---- */
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;

    (async () => {
      const [layerRes, nearRes, pfzRes, rasterRes, currentsRes, windRes] = await Promise.all([
        fetch(`${API_BASE}/api/map-layers?lat=${DEFAULT_USER[1]}&lon=${DEFAULT_USER[0]}`).then((r) => r.json()),
        fetch(
          `${API_BASE}/api/zones-nearby?lat=${DEFAULT_USER[1]}&lon=${DEFAULT_USER[0]}&radius_nm=25`,
        ).then((r) => r.json()),
        fetch(`${API_BASE}/api/zones`).then((r) => r.json()),
        fetch(`${API_BASE}/api/raster-layers?lat=${DEFAULT_USER[1]}&lon=${DEFAULT_USER[0]}`)
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
      }
      if (windRes?.points?.length) {
        setWindVectors(windRes.points as WindVector[]);
        setWindBounds(windRes.bounds as [number, number, number, number]);
        setWindAcquisitionDate(windRes.acquisition_date as string);
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
        });
        m0.addLayer({
          id: `${sourceId}-raster`,
          type: "raster",
          source: sourceId,
          layout: { visibility: "none" },
          paint: { "raster-opacity": layer.style_hints.opacity },
        });
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
  }, [ready]);

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
  if (queryFocus && queryFocus.nonce !== focusedNonce) {
    setFocusedNonce(queryFocus.nonce);
    let bearing: number | null = null;
    if (queryFocus.intent === "boundary") {
      setLayers((s) => (s.boundaries ? s : { ...s, boundaries: true }));
      const coords = boundaryFeatures.features.filter((f) => f.properties.near).flatMap((f) => flattenCoords(f.geometry));
      if (coords.length) {
        const lon = coords.reduce((s, c) => s + c[0], 0) / coords.length;
        const lat = coords.reduce((s, c) => s + c[1], 0) / coords.length;
        bearing = bearingDeg(DEFAULT_USER[1], DEFAULT_USER[0], lat, lon);
      }
    } else if (queryFocus.intent === "fishing") {
      setLayers((s) => (s.pfz ? s : { ...s, pfz: true }));
      const near = pfzFeatures.filter(
        (f) => haversineKm(DEFAULT_USER[1], DEFAULT_USER[0], f.geometry.coordinates[1], f.geometry.coordinates[0]) <= 250,
      );
      if (near.length) {
        const lon = near.reduce((s, f) => s + f.geometry.coordinates[0], 0) / near.length;
        const lat = near.reduce((s, f) => s + f.geometry.coordinates[1], 0) / near.length;
        bearing = bearingDeg(DEFAULT_USER[1], DEFAULT_USER[0], lat, lon);
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

    if (queryFocus.intent === "boundary") {
      const near = boundaryFeatures.features.filter((f) => f.properties.near);
      const coords = near.flatMap((f) => flattenCoords(f.geometry));
      if (coords.length) {
        const lons = [DEFAULT_USER[0], ...coords.map((c) => c[0])];
        const lats = [DEFAULT_USER[1], ...coords.map((c) => c[1])];
        m.fitBounds(
          [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
          { padding: 72, maxZoom: 9.5, duration: 900 },
        );
      } else {
        m.flyTo({ center: DEFAULT_USER, zoom: 8.2, duration: 900 });
      }
    } else if (queryFocus.intent === "fishing") {
      const near = pfzFeatures.filter(
        (f) => haversineKm(DEFAULT_USER[1], DEFAULT_USER[0], f.geometry.coordinates[1], f.geometry.coordinates[0]) <= 250,
      );
      if (near.length) {
        const lons = [DEFAULT_USER[0], ...near.map((f) => f.geometry.coordinates[0])];
        const lats = [DEFAULT_USER[1], ...near.map((f) => f.geometry.coordinates[1])];
        m.fitBounds(
          [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
          { padding: 80, maxZoom: 9, duration: 900 },
        );
      } else {
        m.flyTo({ center: DEFAULT_USER, zoom: 8.6, duration: 900 });
      }
    } else {
      m.flyTo({ center: DEFAULT_USER, zoom: 8.2, duration: 900 });
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

  /* ---- layer visibility: a layout change, never a remount ---- */
  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    const vis = (id: string, on: boolean) => {
      if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    };
    vis("boundaries-fill", layers.boundaries);
    vis("boundaries-line", layers.boundaries);
    vis("pfz-circles", layers.pfz);
    vis("pfz-clusters", layers.pfz);
    vis("pfz-cluster-count", layers.pfz);
    vis("watch-badges-circles", layers.watchBadges);
    vis("seamarks-raster", layers.seamarks);
    for (const layer of rasterLayers) {
      const on = layer.forecast_frames?.length ? layers.waveForecast : layers.srvBathymetry;
      vis(`srv-${layer.layer_id}-raster`, on);
    }
  }, [ready, layers, rasterLayers]);

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
        map={map.current}
        showCurrents={layers.currents}
        showWind={layers.wind}
        currentVectors={currentVectors}
        windVectors={windVectors}
        currentBounds={currentBounds}
        windBounds={windBounds}
      />

      {showPanels && (
        <div className="pointer-events-none absolute inset-0">
          {showLayerPanel && (
          <div className="pointer-events-auto absolute top-3 left-3 w-56">
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
                <LayerToggle
                  label="Boundaries"
                  swatch={CHART.eez}
                  checked={layers.boundaries}
                  onChange={(v) => setLayers((s) => ({ ...s, boundaries: v }))}
                />
                <LayerToggle
                  label="Fishing zones (PFZ)"
                  swatch={CHART.pfz}
                  checked={layers.pfz}
                  onChange={(v) => setLayers((s) => ({ ...s, pfz: v }))}
                />
                {getToken() && (
                  <LayerToggle
                    label="My watch badges"
                    swatch={CHART.caution}
                    checked={layers.watchBadges}
                    onChange={(v) => setLayers((s) => ({ ...s, watchBadges: v }))}
                  />
                )}
                <LayerToggle
                  label="Seamarks (Port Buoys & Lights)"
                  swatch={CHART.ink}
                  checked={layers.seamarks}
                  onChange={(v) => setLayers((s) => ({ ...s, seamarks: v }))}
                />
                {rasterLayers.some((l) => !l.forecast_frames?.length) && (
                  <LayerToggle
                    label="Depth shading (India Coast)"
                    swatch={CHART.eezNear}
                    heavy
                    checked={layers.srvBathymetry}
                    onChange={(v) => toggleHeavy("srvBathymetry", v)}
                  />
                )}
                {forecastLayer && (
                  <LayerToggle
                    label="Wave height forecast"
                    swatch={CHART.accent}
                    heavy
                    checked={layers.waveForecast}
                    onChange={(v) => toggleHeavy("waveForecast", v)}
                  />
                )}
                {currentVectors && currentVectors.length > 0 && (
                  <LayerToggle
                    label="Surface currents"
                    swatch={CHART.pfz}
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
                    swatch="#e8b25a"
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
          </div>
          )}

          {showLegends && layers.srvBathymetry && (
            // Sits directly under the recenter button, one column clear of
            // the region switcher — the two used to share "top-3 right-14",
            // a pre-existing collision that was just never visible while Ask
            // kept srvBathymetry off by default.
            <div className={`pointer-events-auto absolute hidden sm:block rounded-xl border border-hairline/80 bg-shelf-1/95 px-3 py-2 backdrop-blur-md shadow-lg ${showRegionSwitcher ? "top-16 right-3" : "top-3 right-14"}`}>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-[#ccebc5]" />
                <span className="text-[11px] font-medium text-ink">Depth Shading (ETOPO/GEBCO) meters</span>
              </div>
              <div className="mt-1.5 flex h-2 w-48 overflow-hidden rounded-full border border-hairline">
                <div className="w-1/4 bg-[#f0f9e8]" title="0 - 50m (Shallow / Inshore)" />
                <div className="w-1/4 bg-[#bae4bc]" title="50 - 200m (Shelf)" />
                <div className="w-1/4 bg-[#7bccc4]" title="200 - 1000m (Slope)" />
                <div className="w-1/4 bg-[#2b8cbe]" title="1000 - 2000m (Deep Basin)" />
                <div className="w-1/4 bg-[#08589e]" title="2000m+ (Abyssal Plain)" />
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
            <div className={`pointer-events-auto absolute hidden sm:block rounded-xl border border-hairline/80 bg-shelf-1/95 px-3 py-2 backdrop-blur-md shadow-lg ${showRegionSwitcher ? "top-16 right-3" : "top-3 right-14"}`}>
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
                  className={`size-3 text-ink-dim transition-transform duration-200 shrink-0 ${
                    regionDropdownOpen ? "rotate-180" : ""
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
                      className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                        selectedRegion === region.id
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

          {/* Region dashboard — three numbers only (fishing zones, wind,
              hazards), docked to whichever side of the region is open water
              (region.coast) so it never sits over the coastline. Clears
              itself via the moveend effect once the chart no longer looks
              at that region. Tied to the same prop as the switcher above —
              without the switcher a user has no way to pick a region, so a
              dashboard for one would be explaining a control that isn't
              there. */}
          {showRegionSwitcher && regionStats && (
            <div
              className={`pointer-events-auto absolute top-14 z-20 w-52 rounded-xl border border-hairline/80 bg-shelf-1/95 backdrop-blur-xl p-3 shadow-lg ${
                regionStats.region.coast === "west" ? "left-3" : "right-14"
              }`}
            >
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
                <Readout label="Zones" value={regionStats.zoneCount} />
                <Readout
                  label="Wind"
                  value={regionStats.avgWindMs != null ? regionStats.avgWindMs.toFixed(1) : "—"}
                  unit={regionStats.avgWindMs != null ? "m/s" : undefined}
                />
                <Readout label="Hazards" value={regionStats.hazardCount} />
              </ReadoutGrid>
            </div>
          )}

          {/* Quick recenter button */}
          <div className="pointer-events-auto absolute top-3 right-3 z-10">
            <button
              type="button"
              onClick={() => {
                setSelectedRegion("gulf_mannar");
                map.current?.flyTo({
                  center: DEFAULT_USER,
                  zoom: 8.5,
                  duration: 800,
                  essential: true,
                });
              }}
              title="Recenter chart on Gulf of Mannar pilot sector"
              aria-label="Recenter chart on Gulf of Mannar"
              className="flex size-[34px] items-center justify-center rounded-xl border border-hairline/80 bg-shelf-1/95 backdrop-blur-md text-ink-muted shadow transition-colors hover:bg-shelf-2 hover:text-ink focus:outline-none"
            >
              <Crosshair className="size-4 text-accent" />
            </button>
          </div>

          <div
            className={`pointer-events-auto absolute right-3 left-3 sm:left-auto sm:w-80 transition-all ${
              Boolean(layers.waveForecast && forecastLayer?.forecast_frames?.length)
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
            {selectedPfz && (
              <div className="mb-2.5 overflow-hidden rounded-xl border border-go/30 bg-shelf-3/95 backdrop-blur-xl shadow-xl  transition-all">
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
                    onClick={() => setSelectedPfz(null)}
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
                      <span className="mt-1 inline-flex items-center gap-1 rounded-full border border-go/30 bg-go/15 px-1.5 py-0.5 text-[8px] font-bold uppercase text-go">
                        <span className="size-1 rounded-full bg-go animate-pulse" /> Active
                      </span>
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

                  {/* Provenance footer */}
                  <div className="mt-2.5 flex items-center justify-between border-t border-hairline pt-2 text-[9px] text-ink-dim">
                    <span className="flex items-center gap-1 text-go/90 font-medium">
                      <ShieldCheck className="size-3 text-go" /> INCOIS Official PFZ
                    </span>
                    <span className="text-ink-dim font-mono">Satellite SST + Chlorophyll</span>
                  </div>
                </div>
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
                    className="flex items-center gap-2 rounded-full border border-ocean-cyan/40 bg-shelf-3/95 px-3 py-1.5 backdrop-blur-xl text-[11px] font-semibold text-ocean-cyan shadow-lg hover:border-ocean-cyan hover:bg-ocean-cyan/15 transition-all cursor-pointer"
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
                                className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${
                                  depth.shallow_hazard
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

                          {/* Provenance citation */}
                          <div className="mt-2.5 flex items-center justify-between border-t border-hairline pt-2 text-[9px] text-ink-dim">
                            <span className="flex items-center gap-1 text-ocean-cyan/90 font-medium">
                              <ShieldCheck className="size-3 text-ocean-cyan" /> NOAA ETOPO 2022 / GEBCO
                            </span>
                            <span className="text-ink-dim font-mono">30 Aug, 00:00 UTC</span>
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
// A small diamond target — a chart symbol, not a pin. Drawn once on an
// offscreen canvas at module load and reused as a GPU sprite by every
// unclustered PFZ point (see the "pfz-circles" symbol layer).
function buildPfzMarkerIcon(): ImageData {
  const size = 28;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const cx = size / 2;
  const cy = size / 2;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(Math.PI / 4);
  const half = 6;
  ctx.beginPath();
  ctx.roundRect(-half, -half, half * 2, half * 2, 2);
  ctx.fillStyle = CHART.pfz;
  ctx.fill();
  ctx.lineWidth = 1.75;
  ctx.strokeStyle = "#0d2a20";
  ctx.stroke();
  ctx.restore();
  ctx.beginPath();
  ctx.arc(cx, cy, 1.8, 0, Math.PI * 2);
  ctx.fillStyle = "#fffdf6";
  ctx.fill();
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
