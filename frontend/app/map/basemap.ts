// Basemap and overlay configuration (plan §4.1: "Style URLs are config, never
// code — swapping the basemap must not be a code change").
//
// Nothing here is imported by anything except the map shell, and MapView
// contains no literal tile URL. Swapping CARTO for a self-hosted Protomaps
// PMTiles style is an env change.
import type { RasterSourceSpecification } from "maplibre-gl";

// CARTO Dark Matter. Free to 5M tiles/month; an API key removes the
// watermark (carto.com/basemaps/apikey) and is appended as `?key=`.
// Keyless still renders, so the app runs with no signup.
const CARTO_DARK = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

export const BASEMAP_STYLE =
  process.env.NEXT_PUBLIC_BASEMAP_STYLE ??
  (process.env.NEXT_PUBLIC_CARTO_KEY ? `${CARTO_DARK}?key=${process.env.NEXT_PUBLIC_CARTO_KEY}` : CARTO_DARK);

// Pilot region (77.5–80.5 E / 7.5–10.5 N) — matches the GEBCO extract's bbox.
export const PILOT_BOUNDS: [number, number, number, number] = [77.5, 7.5, 80.5, 10.5];

// Thoothukudi — the §8 acceptance-test position, and the default "you are
// here" until a real geolocation/session flow lands in Phase 2.
export const DEFAULT_USER: [number, number] = [78.14, 8.8];

/** Raster overlays. Both are keyless and openly licensed, so the map has real
 *  bathymetry and real seamarks on day one rather than after a procurement. */
export const RASTER_OVERLAYS: Record<string, { source: RasterSourceSpecification; opacity: number }> = {
  // EMODnet Bathymetry — global DTM blended with GEBCO, CC-BY 4.0. WMS with
  // MapLibre's {bbox-epsg-3857} placeholder; the WMTS is faster but is
  // EPSG:4326-only, and MapLibre renders web mercator.
  bathymetry: {
    source: {
      type: "raster",
      tiles: [
        "https://ows.emodnet-bathymetry.eu/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap" +
          "&LAYERS=mean_multicolour&STYLES=&FORMAT=image/png&TRANSPARENT=true" +
          "&CRS=EPSG:3857&WIDTH=256&HEIGHT=256&BBOX={bbox-epsg-3857}",
      ],
      tileSize: 256,
      maxzoom: 12,
      attribution: '<a href="https://emodnet.ec.europa.eu/en/bathymetry">EMODnet Bathymetry</a>',
    },
    opacity: 0.55,
  },

  // OpenSeaMap seamarks — buoys, beacons, lights, harbours. This is the layer
  // that makes the chart read as nautical rather than as a dark webmap.
  seamarks: {
    source: {
      type: "raster",
      tiles: ["https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 18,
      attribution: '<a href="https://www.openseamap.org">OpenSeaMap</a>',
    },
    opacity: 0.9,
  },
};

/** Palette pulled from the CSS tokens so map cartography and UI chrome cannot
 *  drift. Read at module scope on the client only. */
export const CHART = {
  eez: "#22617f",
  eezNear: "#7fd4e8",
  mpa: "#ffc145",
  pfz: "#3ddc97",
  accent: "#f0468c",
  ink: "#dce9f0",
  // Same hex as --color-go/--color-caution/--color-no-go in globals.css —
  // kept in sync by hand (CHART is CSS-var-derived only where noted above;
  // MapLibre paint expressions need literal hex, not a var() reference).
  go: "#3ddc97",
  caution: "#ffc145",
  noGo: "#ff5c5c",
} as const;

/** MapLibre removed `maplibregl.supported()` in v3 — §4.7 still specifies it,
 *  and calling it throws. This is the real check the WebGL fallback needs. */
export function webglAvailable(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") ?? c.getContext("webgl"));
  } catch {
    return false;
  }
}
