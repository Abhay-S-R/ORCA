"use client";

// P5.28 — a small polygon and point-with-radius drawing tool for the watch
// form, hand-written (~150 lines, per the plan's own ceiling before reaching
// for a library like terra-draw). Deliberately a standalone map rather than
// an extension of the shared MapView: MapView is a single load-bearing
// component the whole app depends on, and a draw mode belongs to this one
// form, not to every surface that renders a chart.
//
// P5.6's other open half rides along for free here: the treaty boundary
// lines (`/api/map-layers`'s `maritime_boundary_lines`, the same 32-feature
// set the general chart already draws) render underneath, since a
// geofence_approach watch is exactly the case where seeing the line you are
// placing a watch against matters most.
import "maplibre-gl/dist/maplibre-gl.css";
import * as maplibregl from "maplibre-gl";
import { setWorkerUrl } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../lib/apiBase";
import { BASEMAP_STYLE, INDIA_VIEW } from "../map/basemap";

setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const EMPTY_FC = { type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection;

export function WatchGeometryPicker({
  mode,
  point,
  onPointChange,
  area,
  onAreaChange,
}: {
  mode: "point" | "area";
  point: { lat: number; lon: number } | null;
  onPointChange: (lat: number, lon: number) => void;
  area: GeoJSON.Polygon | null;
  onAreaChange: (polygon: GeoJSON.Polygon | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const vertices = useRef<[number, number][]>(area ? area.coordinates[0].slice(0, -1).map((c) => [c[0], c[1]]) : []);

  useEffect(() => {
    if (!container.current || map.current) return;
    const m = new maplibregl.Map({
      container: container.current, style: BASEMAP_STYLE,
      center: point ? [point.lon, point.lat] : INDIA_VIEW.center,
      zoom: point ? 8 : INDIA_VIEW.zoom, attributionControl: false,
      minZoom: 1, maxZoom: 22,
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl(), "top-right");
    m.on("load", () => {
      m.addSource("boundary-lines", { type: "geojson", data: EMPTY_FC });
      m.addLayer({
        id: "boundary-lines", type: "line", source: "boundary-lines",
        paint: { "line-color": "#8a3b52", "line-width": 1.5, "line-dasharray": [3, 2] },
      });
      m.addSource("draw", { type: "geojson", data: EMPTY_FC });
      m.addLayer({ id: "draw-fill", type: "fill", source: "draw", filter: ["==", "$type", "Polygon"], paint: { "fill-color": "#2f6f74", "fill-opacity": 0.2 } });
      m.addLayer({ id: "draw-line", type: "line", source: "draw", paint: { "line-color": "#2f6f74", "line-width": 2 } });
      m.addLayer({ id: "draw-points", type: "circle", source: "draw", filter: ["==", "$type", "Point"], paint: { "circle-color": "#2f6f74", "circle-radius": 5, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
      fetch(`${API_BASE}/api/map-layers`)
        .then((r) => r.json())
        .then((res) => (m.getSource("boundary-lines") as maplibregl.GeoJSONSource)?.setData(res.maritime_boundary_lines ?? EMPTY_FC))
        .catch(() => {});
      setReady(true);
    });
    return () => {
      m.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- created once; point/area handled by the render-sync effect below
  }, []);

  // Click handling — mode-dependent, re-bound whenever mode/callbacks change.
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const { lat, lng } = e.lngLat;
      if (mode === "point") {
        onPointChange(lat, lng);
        return;
      }
      vertices.current = [...vertices.current, [lng, lat]];
      syncDrawSource();
      if (vertices.current.length >= 3) {
        onAreaChange({ type: "Polygon", coordinates: [[...vertices.current, vertices.current[0]]] });
      }
    };
    const onDblClick = (e: maplibregl.MapMouseEvent) => {
      if (mode !== "area" || vertices.current.length < 3) return;
      e.preventDefault();
    };
    m.on("click", onClick);
    m.on("dblclick", onDblClick);
    return () => {
      m.off("click", onClick);
      m.off("dblclick", onDblClick);
    };
  }, [mode, onPointChange, onAreaChange, ready]);

  function syncDrawSource() {
    const m = map.current;
    if (!m) return;
    const features: GeoJSON.Feature[] = vertices.current.map((c) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: c } }));
    if (vertices.current.length >= 2) {
      const ring = vertices.current.length >= 3 ? [...vertices.current, vertices.current[0]] : vertices.current;
      features.push({ type: "Feature", properties: {}, geometry: { type: vertices.current.length >= 3 ? "Polygon" : "LineString", coordinates: vertices.current.length >= 3 ? [ring] : ring } as GeoJSON.Geometry });
    }
    (m.getSource("draw") as maplibregl.GeoJSONSource)?.setData({ type: "FeatureCollection", features });
  }

  // Render the point pin when in point mode.
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || mode !== "point") return;
    (m.getSource("draw") as maplibregl.GeoJSONSource)?.setData(
      point ? { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [point.lon, point.lat] } }] } : EMPTY_FC,
    );
  }, [point, mode, ready]);

  function reset() {
    vertices.current = [];
    syncDrawSource();
    onAreaChange(null);
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div ref={container} className="h-[260px] w-full overflow-hidden rounded-lg ring-1 ring-hairline" />
      {mode === "area" && (
        <div className="flex items-center justify-between text-[11px] text-ink-dim">
          <span>
            Click to add vertices ({vertices.current.length}); the shape closes automatically at 3+ points.
          </span>
          <button type="button" onClick={reset} className="text-accent underline underline-offset-2">
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
