// §4.7 `/map` instrumentation: layer_load_ms, render_ms, payload_bytes and
// dropped-frame count per layer toggle. "Engineering visibility only — a
// budget check, not an observability platform" — so this is one function,
// not a metrics SDK.
import type * as maplibregl from "maplibre-gl";
import { API_BASE } from "./apiBase";

export type LayerMetrics = {
  layer_id: string;
  layer_load_ms: number;
  render_ms: number;
  payload_bytes: number;
  dropped_frames: number;
};

// Measures one toggle-to-painted cycle for a MapLibre raster/geojson source:
// layer_load_ms = toggle -> source finished loading, render_ms = source
// loaded -> map idle (GPU composite done). transferSize on matching resource
// entries gives payload_bytes; a >34ms gap between rAF ticks counts as a
// dropped frame (below ~30fps, the plan's not-collapsing floor is 45fps).
export function measureLayerToggle(m: maplibregl.Map, layerId: string, sourceId: string): Promise<LayerMetrics> {
  return new Promise((resolve) => {
    const t0 = performance.now();
    let dropped = 0;
    let last = t0;
    let loadedAt: number | null = null;
    let raf = 0;
    let bytes = 0;

    const perfObs = new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.name.includes(sourceId) || e.name.includes(layerId)) {
          bytes += (e as PerformanceResourceTiming).transferSize || 0;
        }
      }
    });
    perfObs.observe({ type: "resource", buffered: true });

    const tick = () => {
      const now = performance.now();
      if (now - last > 34) dropped++;
      last = now;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const onSourceData = (e: maplibregl.MapSourceDataEvent) => {
      if (e.sourceId === sourceId && m.isSourceLoaded(sourceId) && loadedAt === null) {
        loadedAt = performance.now();
        m.off("sourcedata", onSourceData);
      }
    };
    m.on("sourcedata", onSourceData);

    m.once("idle", () => {
      cancelAnimationFrame(raf);
      perfObs.disconnect();
      m.off("sourcedata", onSourceData);
      const now = performance.now();
      const loaded = loadedAt ?? now;
      resolve({
        layer_id: layerId,
        layer_load_ms: Math.round(loaded - t0),
        render_ms: Math.round(now - loaded),
        payload_bytes: bytes,
        dropped_frames: dropped,
      });
    });
  });
}

export function reportLayerMetrics(metrics: LayerMetrics): void {
  if (process.env.NODE_ENV !== "production") {
    console.log("[layer-perf]", metrics);
    return;
  }
  fetch(`${API_BASE}/api/layer-metrics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metrics),
    keepalive: true,
  }).catch(() => {
    /* engineering visibility only — never block the map on this */
  });
}
