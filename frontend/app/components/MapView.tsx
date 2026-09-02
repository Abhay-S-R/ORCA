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
import { useCallback, useEffect, useRef, useState } from "react";
import { Compass, Crosshair, Layers } from "lucide-react";
import {
  BASEMAP_STYLE,
  CHART,
  DEFAULT_USER,
  PILOT_BOUNDS,
  RASTER_OVERLAYS,
  webglAvailable,
} from "../map/basemap";
import { LayerToggle } from "./LayerToggle";
import { Panel } from "./Panel";
import { Readout, ReadoutGrid } from "./Readout";
import { SourceChip } from "./SourceChip";
import { EmptyState } from "./States";

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
type PfzFeature = {
  geometry: { coordinates: [number, number] };
  properties: { mean_sst_c: number; approx_area_km2: number };
};
type DepthResult = { depth_m: number | null; on_land: boolean; shallow_hazard: boolean };
type Bearing = { bearing_deg: number; distance_nm: number };

const EMPTY = { type: "FeatureCollection", features: [] };

export function MapView({
  className = "h-full w-full",
  showPanels = true,
}: {
  className?: string;
  showPanels?: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [supported] = useState(webglAvailable);

  const [nearNames, setNearNames] = useState<string[]>([]);
  const [clicked, setClicked] = useState<{ lat: number; lon: number } | null>(null);
  const [depth, setDepth] = useState<DepthResult | null>(null);
  const [bearing, setBearing] = useState<Bearing | null>(null);
  const [layers, setLayers] = useState({
    boundaries: true,
    pfz: true,
    seamarks: true,
    bathymetry: false,
  });

  const handleClick = useCallback(async (lat: number, lon: number) => {
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
  }, []);

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
        m.addSource(id, source);
        m.addLayer({
          id: `${id}-raster`,
          type: "raster",
          source: id,
          layout: { visibility: "none" },
          paint: { "raster-opacity": opacity },
        });
      }

      m.addSource("boundaries", { type: "geojson", data: EMPTY as never });
      m.addSource("pfz", { type: "geojson", data: EMPTY as never });

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
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 3, 11, 9],
          "circle-color": CHART.pfz,
          "circle-opacity": 0.65,
          "circle-stroke-width": 1,
          "circle-stroke-color": CHART.pfz,
        },
      });

      setReady(true);
    });

    m.on("click", (e) => void handleClick(e.lngLat.lat, e.lngLat.lng));
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

  /* ---- data: fetched once, pushed through setData ---- */
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;

    (async () => {
      const [layerRes, nearRes, pfzRes] = await Promise.all([
        fetch(`${API_BASE}/api/map-layers?lat=${DEFAULT_USER[1]}&lon=${DEFAULT_USER[0]}`).then((r) => r.json()),
        fetch(
          `${API_BASE}/api/zones-nearby?lat=${DEFAULT_USER[1]}&lon=${DEFAULT_USER[0]}&radius_nm=25`,
        ).then((r) => r.json()),
        fetch(`${API_BASE}/api/zones`).then((r) => r.json()),
      ]);
      if (cancelled || !map.current) return;

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
      (map.current.getSource("pfz") as maplibregl.GeoJSONSource)?.setData({
        type: "FeatureCollection",
        features: (pfzRes.features as PfzFeature[]).map((f) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: f.geometry.coordinates },
          properties: f.properties,
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
    vis("bathymetry-raster", layers.bathymetry);
  }, [ready, layers]);

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

      {showPanels && (
        <div className="pointer-events-none absolute inset-0">
          <div className="pointer-events-auto absolute top-3 left-3 w-56">
            <Panel dense title="Chart layers" action={<Layers className="size-3.5 text-ink-dim" />}>
              <div className="-mx-2">
                <LayerToggle
                  label="Boundaries"
                  swatch={CHART.eez}
                  checked={layers.boundaries}
                  onChange={(v) => setLayers((s) => ({ ...s, boundaries: v }))}
                />
                <LayerToggle
                  label="Fishing zones"
                  swatch={CHART.pfz}
                  checked={layers.pfz}
                  onChange={(v) => setLayers((s) => ({ ...s, pfz: v }))}
                />
                <LayerToggle
                  label="Seamarks"
                  swatch={CHART.ink}
                  checked={layers.seamarks}
                  onChange={(v) => setLayers((s) => ({ ...s, seamarks: v }))}
                />
                <LayerToggle
                  label="Depth shading"
                  swatch={CHART.eezNear}
                  heavy
                  checked={layers.bathymetry}
                  onChange={(v) => setLayers((s) => ({ ...s, bathymetry: v }))}
                />
              </div>
              {nearNames.length > 0 && (
                <p className="mt-2 border-t border-hairline pt-2 text-[11px] text-ink-dim">
                  {nearNames.length} within 25 nm, drawn brighter
                </p>
              )}
            </Panel>
          </div>

          <div className="pointer-events-auto absolute right-3 bottom-36 left-3 sm:left-auto sm:bottom-24 sm:w-80">
            <Panel dense title="Sounding" action={<Crosshair className="size-3.5 text-ink-dim" />}>
              {!clicked ? (
                <p className="text-xs text-ink-muted">
                  Tap the chart to read GEBCO depth and the bearing from your position.
                </p>
              ) : (
                <>
                  <ReadoutGrid cols={3}>
                    <Readout label="Position" value={`${clicked.lat.toFixed(3)}, ${clicked.lon.toFixed(3)}`} />
                    <Readout
                      label="Depth"
                      value={depth ? (depth.on_land ? "On land" : (depth.depth_m ?? "—")) : "…"}
                      unit={depth && !depth.on_land && depth.depth_m != null ? "m" : undefined}
                      hint={depth?.shallow_hazard ? <span className="text-caution">Shallow hazard</span> : undefined}
                    />
                    <Readout
                      label="Bearing"
                      value={bearing ? `${bearing.bearing_deg}°` : "…"}
                      hint={bearing ? `${bearing.distance_nm} nm` : undefined}
                    />
                  </ReadoutGrid>
                  <div className="mt-3">
                    <SourceChip
                      dataset="GEBCO 2026 Grid"
                      acquisitionTimestamp="2026-08-30T00:00:00Z"
                      detail="Bathymetry is a reference grid, not a survey. Never navigate on a charted depth alone."
                    />
                  </div>
                </>
              )}
            </Panel>
          </div>
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
