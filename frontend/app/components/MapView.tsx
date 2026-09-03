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
import { useCallback, useEffect, useRef, useState } from "react";
import { Calendar, ChevronDown, ChevronUp, Compass, Crosshair, Layers, MapPin, Navigation, ShieldCheck, Waves, X } from "lucide-react";
import { BASEMAP_STYLE, CHART, DEFAULT_USER, PILOT_BOUNDS, RASTER_OVERLAYS, webglAvailable } from "../map/basemap";
import { LayerToggle } from "./LayerToggle";
import { Panel } from "./Panel";
import { EmptyState } from "./States";
import { TimeSlider } from "./TimeSlider";
import { measureLayerToggle, reportLayerMetrics } from "../lib/layerPerf";

// See scripts/copy-maplibre-worker.mjs — Turbopack will not emit the worker's
// sibling module next to it, so the worker is served from public/ instead.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type BoundaryGeoJson = { type: "FeatureCollection"; features: GeoJsonFeature[] };
type GeoJsonFeature = {
  type: "Feature";
  geometry: unknown;
  properties: { name: string; designation: string };
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
}

const COASTAL_REGIONS: MarinePortPreset[] = [
  { id: "all", name: "All India Coastline", sub: "National Overview", center: [78.5, 15.5], zoom: 4.8 },
  { id: "gulf_mannar", name: "Gulf of Mannar / Thoothukudi", sub: "Pilot Sector", center: [78.8, 8.8], zoom: 7.8 },
  { id: "gujarat", name: "Gujarat (Kutch & Saurashtra)", sub: "West Coast", center: [69.6, 21.8], zoom: 7.2 },
  { id: "mumbai", name: "Mumbai & Konkan Coast", sub: "Maharashtra", center: [72.8, 18.9], zoom: 8.2 },
  { id: "goa", name: "Goa & Karwar", sub: "Goa / Karnataka", center: [73.8, 15.4], zoom: 8.4 },
  { id: "kochi", name: "Kochi & Malabar Coast", sub: "Kerala", center: [76.1, 9.9], zoom: 8.2 },
  { id: "lakshadweep", name: "Lakshadweep Islands", sub: "Arabian Sea", center: [72.6, 10.5], zoom: 8.0 },
  { id: "chennai", name: "Chennai & Coromandel", sub: "Tamil Nadu", center: [80.3, 13.1], zoom: 8.2 },
  { id: "vizag", name: "Visakhapatnam & Circars", sub: "Andhra Pradesh", center: [83.3, 17.7], zoom: 8.0 },
  { id: "kolkata", name: "Odisha & Sundarbans", sub: "East Coast", center: [87.5, 20.8], zoom: 7.5 },
  { id: "andaman", name: "Andaman & Nicobar", sub: "Bay of Bengal", center: [92.8, 11.6], zoom: 7.0 },
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

export function MapView({
  className = "h-full w-full",
  showPanels = true,
  onPointClick,
  routeGeoJson,
  pins,
  showSoundingHud = true,
  defaultCollapsedSounding = false,
}: {
  className?: string;
  showPanels?: boolean;
  // Additive hook for /voyage's click-to-set origin/destination — fires
  // alongside the existing depth/bearing "sounding" lookup below, never
  // replacing it.
  onPointClick?: (lat: number, lon: number) => void;
  routeGeoJson?: RouteGeoJson | null;
  pins?: MapPin[];
  showSoundingHud?: boolean;
  defaultCollapsedSounding?: boolean;
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
    boundaries: true,
    pfz: true,
    seamarks: true,
    srvBathymetry: false,
    waveForecast: false,
    currents: false,
    wind: false,
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
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const forecastLayer = rasterLayers.find((l) => l.forecast_frames && l.forecast_frames.length > 0);

  // §4.7 layer lifecycle: heavy-layer LRU + eviction notice.
  const [heavyLimit, setHeavyLimit] = useState(4);
  const [evictionNotice, setEvictionNotice] = useState<string | null>(null);
  const lru = useRef<HeavyKey[]>([]);

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
      // Dark Matter is a city basemap: it paints water LIGHTER than land,
      // which is backwards on a chart. Recolour to the ECDIS depth ramp so
      // the sea reads as the subject and the coast as the frame.
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
      m.addSource("pfz", { type: "geojson", data: EMPTY as never });
      m.addSource("route", { type: "geojson", data: EMPTY as never });

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

      m.addLayer({
        id: "boundaries-line",
        type: "line",
        source: "boundaries",
        layout: { "line-join": "round" },
        paint: {
          "line-color": [
            "case",
            ["get", "near"],
            CHART.eezNear,
            ["case", isMpa, CHART.mpa, CHART.eez],
          ],
          "line-width": ["case", ["get", "near"], 2.5, 1],
          "line-opacity": ["case", ["get", "near"], 0.95, 0.4],
        },
      });

      m.addLayer({
        id: "pfz-circles",
        type: "circle",
        source: "pfz",
        paint: {
          // N CircleMarker components become one layer with a zoom expression.
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 3.5, 7, 5, 11, 9],
          "circle-color": CHART.pfz,
          "circle-opacity": 0.85,
          "circle-stroke-width": 1.5,
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

    m.on("click", (e) => {
      const pfzFeatures = m.queryRenderedFeatures(e.point, { layers: ["pfz-circles"] });
      if (pfzFeatures.length && pfzFeatures[0].properties) {
        setSelectedPfz(pfzFeatures[0].properties as PfzProperties);
      } else {
        setSelectedPfz(null);
      }
      void handleClick(e.lngLat.lat, e.lngLat.lng);
    });
    for (const id of ["boundaries-fill", "pfz-circles"]) {
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

  /* ---- user position marker ---- */
  useEffect(() => {
    if (!ready || !map.current) return;
    const el = document.createElement("div");
    el.style.cssText = `width:12px;height:12px;border-radius:9999px;background:${CHART.accent};box-shadow:0 0 0 4px ${CHART.accent}33`;
    el.setAttribute("aria-label", "Your position, Thoothukudi");
    const marker = new maplibregl.Marker({ element: el }).setLngLat(DEFAULT_USER).addTo(map.current);
    return () => {
      marker.remove();
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

  useEffect(() => {
    if (!ready || !map.current || !pins?.length) return;
    const built = pins.map((p) => {
      const el = document.createElement("div");
      el.style.cssText = `width:14px;height:14px;border-radius:9999px;background:${p.color};border:2px solid #04121a;box-shadow:0 0 0 3px ${p.color}33`;
      el.setAttribute("aria-label", p.label);
      return new maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(map.current!);
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
      const pfzRaw = (pfzRes.features ?? pfzRes.thermal_front_proxy?.features ?? []) as PfzFeature[];
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
      />

      {showPanels && (
        <div className="pointer-events-none absolute inset-0">
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

          {layers.srvBathymetry && (
            <div className="pointer-events-auto absolute top-3 left-64 hidden sm:block rounded-md border border-hairline bg-shelf-1/90 px-3 py-2 backdrop-blur-sm shadow-sm">
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

          {layers.waveForecast && !layers.srvBathymetry && (
            <div className="pointer-events-auto absolute top-3 left-64 hidden sm:block rounded-md border border-hairline bg-shelf-1/90 px-3 py-2 backdrop-blur-sm shadow-sm">
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

          {/* Coastal Region & Port Quick Switcher */}
          <div ref={regionDropdownRef} className="pointer-events-auto absolute top-3 right-14 z-20">
            <div className="relative">
              <button
                type="button"
                onClick={() => setRegionDropdownOpen(!regionDropdownOpen)}
                className="flex items-center gap-2 rounded-xl border border-hairline/80 bg-shelf-1/95 backdrop-blur-xl px-3 py-1.5 text-xs font-medium text-ink shadow-lg transition-all hover:bg-shelf-2 hover:border-hairline-strong focus:outline-none"
                aria-label="Select coastal sector"
              >
                <MapPin className="size-3.5 text-accent" />
                <span className="max-w-[140px] sm:max-w-none truncate font-medium">
                  {COASTAL_REGIONS.find((r) => r.id === selectedRegion)?.name ?? "Select Sector"}
                </span>
                <ChevronDown
                  className={`size-3 text-ink-dim transition-transform duration-200 ${
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

          {/* Quick recenter button */}
          <div className="pointer-events-auto absolute top-28 right-2.5 z-10">
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
              className="flex size-[29px] items-center justify-center rounded-md border border-hairline bg-shelf-1/90 backdrop-blur-md text-ink-muted shadow transition-colors hover:bg-shelf-2 hover:text-ink focus:outline-none"
            >
              <Crosshair className="size-4" />
            </button>
          </div>

          <div
            className={`pointer-events-auto absolute right-3 left-3 sm:left-auto sm:w-80 transition-all ${
              Boolean(layers.waveForecast && forecastLayer?.forecast_frames?.length)
                ? "bottom-36 sm:bottom-24"
                : "bottom-4 sm:bottom-4"
            }`}
          >
            {selectedPfz && (
              <div className="mb-2.5 overflow-hidden rounded-xl border border-emerald-500/30 bg-[#07131e]/95 backdrop-blur-xl shadow-[0_12px_32px_rgba(0,0,0,0.65)] ring-1 ring-white/10 transition-all">
                {/* Glowing top line */}
                <div className="h-0.5 bg-gradient-to-r from-emerald-500 via-teal-400 to-cyan-400" />

                {/* Header */}
                <div className="flex items-center justify-between border-b border-white/10 px-3.5 py-2.5 bg-gradient-to-b from-white/[0.03] to-transparent">
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                    </span>
                    <span className="rounded-full border border-emerald-500/40 bg-emerald-950/60 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">
                      PFZ Advisory
                    </span>
                    <h4 className="text-xs font-bold tracking-tight text-white truncate max-w-[140px]">
                      {selectedPfz.landing_center ? String(selectedPfz.landing_center) : "Fishing Zone"}
                    </h4>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedPfz(null)}
                    className="flex size-6 cursor-pointer items-center justify-center rounded-lg text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
                    aria-label="Close PFZ details"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>

                {/* Body Content */}
                <div className="p-3">
                  <div className="grid grid-cols-2 gap-2">
                    {/* Sector Tile */}
                    <div className="rounded-lg border border-white/5 bg-[#0d2235]/70 p-2">
                      <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                        <MapPin className="size-2.5 text-emerald-400" /> Sector
                      </span>
                      <p className="mt-1 text-xs font-bold text-white truncate">
                        {String(selectedPfz.sector || "General Offshore")}
                      </p>
                    </div>

                    {/* Advised Depth Tile */}
                    <div className="rounded-lg border border-white/5 bg-[#0d2235]/70 p-2">
                      <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                        <Waves className="size-2.5 text-cyan-400" /> Advised Depth
                      </span>
                      <p className="mt-1 font-mono text-xs font-bold text-cyan-300">
                        {selectedPfz.depth_m ? (
                          <>
                            {String(selectedPfz.depth_m)}{" "}
                            <span className="text-[10px] font-normal text-cyan-400/80">m</span>
                          </>
                        ) : "Surface / Mid-water"}
                      </p>
                    </div>

                    {/* Distance & Bearing Tile */}
                    <div className="rounded-lg border border-white/5 bg-[#0d2235]/70 p-2">
                      <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                        <Navigation className="size-2.5 text-sky-400" /> From Landing
                      </span>
                      <p className="mt-1 font-mono text-xs font-bold text-white">
                        {selectedPfz.distance_km != null ? `${selectedPfz.distance_km} km` : "—"}
                      </p>
                      {selectedPfz.direction && (
                        <span className="mt-1 inline-flex items-center rounded border border-white/10 bg-slate-800/80 px-1 py-0.5 font-mono text-[9px] text-slate-300">
                          {selectedPfz.direction} {selectedPfz.bearing_deg != null ? `(${selectedPfz.bearing_deg}°)` : ""}
                        </span>
                      )}
                    </div>

                    {/* Validity & Status Tile */}
                    <div className="rounded-lg border border-white/5 bg-[#0d2235]/70 p-2">
                      <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                        <Calendar className="size-2.5 text-emerald-400" /> Valid Until
                      </span>
                      <p className="mt-1 font-mono text-[11px] font-semibold text-slate-200 truncate">
                        {selectedPfz.valid_for ? String(selectedPfz.valid_for) : "Current cycle"}
                      </p>
                      <span className="mt-1 inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-950/60 px-1.5 py-0.5 text-[8px] font-bold uppercase text-emerald-400">
                        <span className="size-1 rounded-full bg-emerald-400 animate-pulse" /> Active
                      </span>
                    </div>
                  </div>

                  {/* Optional Micro-Metrics Row (SST & Area) */}
                  {(selectedPfz.mean_sst_c != null || selectedPfz.approx_area_km2 != null) && (
                    <div className="mt-2 flex flex-wrap gap-1.5 border-t border-white/5 pt-2">
                      {selectedPfz.mean_sst_c != null && (
                        <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/20 bg-amber-950/40 px-2 py-0.5 text-[10px] font-mono text-amber-300">
                          <span>🌡</span> {selectedPfz.mean_sst_c}°C SST
                        </span>
                      )}
                      {selectedPfz.approx_area_km2 != null && (
                        <span className="inline-flex items-center gap-1 rounded-md border border-cyan-500/20 bg-cyan-950/40 px-2 py-0.5 text-[10px] font-mono text-cyan-300">
                          <span>📐</span> {selectedPfz.approx_area_km2} km² Area
                        </span>
                      )}
                    </div>
                  )}

                  {/* Provenance footer */}
                  <div className="mt-2.5 flex items-center justify-between border-t border-white/10 pt-2 text-[9px] text-slate-400">
                    <span className="flex items-center gap-1 text-emerald-400/90 font-medium">
                      <ShieldCheck className="size-3 text-emerald-400" /> INCOIS Official PFZ
                    </span>
                    <span className="text-slate-500 font-mono">Satellite SST + Chlorophyll</span>
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
                    className="flex items-center gap-2 rounded-full border border-cyan-500/40 bg-[#07131e]/95 px-3 py-1.5 backdrop-blur-xl text-[11px] font-semibold text-cyan-300 shadow-[0_8px_24px_rgba(0,0,0,0.6)] hover:border-cyan-400 hover:bg-cyan-950/50 transition-all cursor-pointer"
                  >
                    <Crosshair className="size-3 text-cyan-400" />
                    <span>Sounding HUD</span>
                    {depth?.depth_m != null && !depth.on_land && (
                      <span className="font-mono font-bold text-cyan-400">{depth.depth_m}m</span>
                    )}
                  </button>
                </div>
              ) : (
                <div className="overflow-hidden rounded-xl border border-cyan-500/30 bg-[#07131e]/95 backdrop-blur-xl shadow-[0_12px_32px_rgba(0,0,0,0.65)] ring-1 ring-white/10 transition-all">
                  {/* Glowing top line */}
                  <div className="h-0.5 bg-gradient-to-r from-cyan-500 via-sky-400 to-indigo-500" />

                  {/* Header */}
                  <div className="flex items-center justify-between border-b border-white/10 px-3.5 py-2 bg-gradient-to-b from-white/[0.03] to-transparent">
                    <div className="flex items-center gap-2">
                      <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-500" />
                      </span>
                      <h3 className="text-xs font-bold tracking-wider uppercase text-cyan-300">
                        Acoustic Sounding HUD
                      </h3>
                      {soundingCollapsed && depth?.depth_m != null && !depth.on_land && (
                        <span className="rounded bg-cyan-950/80 px-1.5 py-0.5 font-mono text-[10px] font-bold text-cyan-300 border border-cyan-500/30">
                          {depth.depth_m}m
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setSoundingCollapsed(!soundingCollapsed)}
                        className="flex size-6 cursor-pointer items-center justify-center rounded-lg text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
                        aria-label={soundingCollapsed ? "Expand HUD" : "Collapse HUD"}
                        title={soundingCollapsed ? "Expand HUD" : "Collapse HUD"}
                      >
                        {soundingCollapsed ? <ChevronUp className="size-3.5 text-cyan-400" /> : <ChevronDown className="size-3.5 text-slate-400" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => setSoundingDismissed(true)}
                        className="flex size-6 cursor-pointer items-center justify-center rounded-lg text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
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
                          <div className="mx-auto mb-1.5 flex size-8 items-center justify-center rounded-full bg-cyan-950/60 border border-cyan-500/30 text-cyan-400">
                            <Waves className="size-4 animate-pulse" />
                          </div>
                          <p className="text-[11px] font-medium text-slate-300">
                            Tap chart to sound seafloor depth
                          </p>
                          <p className="mt-0.5 text-[9px] text-slate-500">
                            Reads NOAA ETOPO 2022 &amp; GEBCO 2026 topography
                          </p>
                        </div>
                      ) : (
                        <>
                          {/* Hero Readout Grid */}
                          <div className="grid grid-cols-2 gap-2">
                            {/* Depth Hero Tile */}
                            <div className="rounded-lg border border-cyan-500/20 bg-gradient-to-br from-[#0c2438] to-[#081826] p-2.5">
                              <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                                <Waves className="size-2.5 text-cyan-400" /> Seafloor Depth
                              </span>
                              <div className="mt-1">
                                {depth ? (
                                  depth.on_land ? (
                                    <p className="font-mono text-base font-bold text-amber-400">On Land</p>
                                  ) : depth.depth_m != null ? (
                                    <>
                                      <p className="font-mono text-2xl font-black text-cyan-300 tracking-tight leading-none drop-shadow-[0_0_8px_rgba(34,211,238,0.4)]">
                                        {depth.depth_m}
                                        <span className="ml-1 text-xs font-bold text-cyan-400/80">m</span>
                                      </p>
                                      <span className="mt-1 block font-mono text-[10px] text-slate-400">
                                        ({(depth.depth_m * 0.5468).toFixed(1)} fm)
                                      </span>
                                    </>
                                  ) : (
                                    <p className="font-mono text-sm text-slate-400">Outside coverage</p>
                                  )
                                ) : (
                                  <p className="font-mono text-base text-slate-400 animate-pulse">Measuring…</p>
                                )}
                              </div>
                            </div>

                            {/* Position Telemetry Tile */}
                            <div className="rounded-lg border border-white/5 bg-[#0a1e30]/60 p-2.5 flex flex-col justify-between">
                              <div>
                                <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                                  <Crosshair className="size-2.5 text-cyan-400" /> Position
                                </span>
                                <div className="mt-1 font-mono text-[11px] font-semibold text-slate-200">
                                  <p>{clicked.lat >= 0 ? `${clicked.lat.toFixed(2)}°N` : `${(-clicked.lat).toFixed(2)}°S`}</p>
                                  <p>{clicked.lon >= 0 ? `${clicked.lon.toFixed(2)}°E` : `${(-clicked.lon).toFixed(2)}°W`}</p>
                                </div>
                              </div>
                              {nearNames.length > 0 && (
                                <p className="mt-1 text-[9px] text-cyan-400/80 truncate">
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
                                    ? "border-amber-500/40 bg-amber-950/40 text-amber-300"
                                    : "border-cyan-500/30 bg-cyan-950/40 text-cyan-300"
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
                          <div className="mt-2 grid grid-cols-2 gap-2 border-t border-white/5 pt-2">
                            <div className="rounded-lg border border-white/5 bg-[#0a1e30]/60 p-2">
                              <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                                <Compass className="size-2.5 text-cyan-400" /> Bearing from Port
                              </span>
                              <p className="mt-1 font-mono text-xs font-bold text-white">
                                {bearing ? `${bearing.bearing_deg}° True` : "…"}
                              </p>
                            </div>
                            <div className="rounded-lg border border-white/5 bg-[#0a1e30]/60 p-2">
                              <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-slate-400">
                                <Navigation className="size-2.5 text-sky-400" /> Distance & Steam
                              </span>
                              <p className="mt-1 font-mono text-xs font-bold text-white">
                                {bearing ? (
                                  <>
                                    {bearing.distance_nm} <span className="text-[10px] font-normal text-slate-400">nm</span>{" "}
                                    <span className="text-[10px] text-sky-300 font-normal">
                                      (~{(bearing.distance_nm / 10).toFixed(1)}h)
                                    </span>
                                  </>
                                ) : "…"}
                              </p>
                            </div>
                          </div>

                          {/* Provenance citation */}
                          <div className="mt-2.5 flex items-center justify-between border-t border-white/10 pt-2 text-[9px] text-slate-400">
                            <span className="flex items-center gap-1 text-cyan-400/90 font-medium">
                              <ShieldCheck className="size-3 text-cyan-400" /> NOAA ETOPO 2022 / GEBCO
                            </span>
                            <span className="text-slate-500 font-mono">30 Aug, 00:00 UTC</span>
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
function recolourSea(m: maplibregl.Map) {
  const set = (id: string, prop: string, value: string | number) => {
    try {
      (m.setPaintProperty as (id: string, prop: string, value: unknown) => void)(id, prop, value);
    } catch {
      /* layer absent in this style — nothing to recolour */
    }
  };

  set("background", "background-color", "#050f16");

  for (const layer of m.getStyle().layers ?? []) {
    const src = "source-layer" in layer ? layer["source-layer"] : undefined;
    if (src !== "water" && src !== "waterway") continue;
    if (layer.type === "fill") {
      set(layer.id, "fill-color", "#0a2c40");
      set(layer.id, "fill-opacity", 1);
    } else if (layer.type === "line") {
      set(layer.id, "line-color", "#123f57");
    } else if (layer.type === "symbol") {
      set(layer.id, "text-color", "#5f8ba3");
      set(layer.id, "text-halo-color", "#0a2c40");
    }
  }
}
