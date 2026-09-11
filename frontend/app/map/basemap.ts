// Basemap and overlay configuration (plan §4.1: "Style URLs are config, never
// code — swapping the basemap must not be a code change").
//
// Nothing here is imported by anything except the map shell, and MapView
// contains no literal tile URL. Swapping CARTO for a self-hosted Protomaps
// PMTiles style is an env change.
// CARTO Positron — a light basemap to match the admiralty-chart paper theme
// (plan's dark ECDIS console retired in favour of the parchment chart look).
// Free to 5M tiles/month; an API key removes the watermark
// (carto.com/basemaps/apikey) and is appended as `?key=`. Keyless still
// renders, so the app runs with no signup.
const CARTO_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

export const BASEMAP_STYLE =
  process.env.NEXT_PUBLIC_BASEMAP_STYLE ??
  (process.env.NEXT_PUBLIC_CARTO_KEY ? `${CARTO_LIGHT}?key=${process.env.NEXT_PUBLIC_CARTO_KEY}` : CARTO_LIGHT);

// Geographic centre of India — a neutral fallback for API calls that need
// *some* coordinate to centre a query on before a real GPS fix (or none)
// arrives. Never rendered as a location marker; that's userLocation only.
export const INDIA_CENTER: [number, number] = [78.9, 20.5];

// The chart's default camera on load — all of India, matching the product's
// national scope. A query or region pick moves it from here.
export const INDIA_VIEW = { center: INDIA_CENTER, zoom: 4.4 };

import type { RasterSourceSpecification } from "maplibre-gl";

export const RASTER_OVERLAYS: Record<string, { source: RasterSourceSpecification; opacity: number }> = {
  // OpenSeaMap seamarks — buoys, beacons, lights, harbours (active in Pamban Pass, Kochi, Chennai, Mumbai, Goa).
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
 *  drift. Read at module scope on the client only. Re-tuned for the light
 *  Positron basemap — the old console's neon values (built to glow against
 *  near-black water) read as washed-out pastel on pale paper, so these are
 *  darker/more saturated versions of the same hues, not the same hex. */
export const CHART = {
  eez: "#2f6f74",
  eezNear: "#1c4a4d",
  mpa: "#b8862e",
  pfz: "#05df72",
  accent: "#8a3b52",
  ink: "#1c2939",
  // Same hex as --color-go/--color-caution/--color-no-go in globals.css —
  // kept in sync by hand (CHART is CSS-var-derived only where noted above;
  // MapLibre paint expressions need literal hex, not a var() reference).
  go: "#2f7a4f",
  caution: "#b8862e",
  noGo: "#b3402c",
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
