"use client";

// Satellite view map for fishing zones — displays high-resolution Esri satellite imagery
// fitted to the specific port region and its charted fishing grounds.
// Clean interactive pins 1, 2, 3, 4, 5, departure port marker, nautical track lines.
// No intrusive floating black box on pins, and right-click context menu disabled.

import { useEffect, useRef, useState, useCallback } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { Compass, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import type { ProfitApiResponse, ZoneProfitResult } from "./zones-dashboard";

const PIN_HEX: Record<string, string> = {
  green: "#2f7a4f",
  orange: "#b8862e",
  red: "#b3402c",
  neutral: "#2f6f74",
};

// Strict boundary strictly enclosing India's coastal maritime domain and EEZ.
// Prevents the camera from panning into Pakistan, Nepal, Bhutan, New Delhi, or outside India.
const INDIA_COASTAL_BOUNDS: [[number, number], [number, number]] = [
  [64.0, 4.0],  // SW: Arabian Sea / Lakshadweep / South of Kanyakumari
  [92.0, 24.5], // NE: Bay of Bengal / Bengal Delta / North of Gujarat coast
];

// All coastal ports across India for regional context
const ALL_COASTAL_PORTS = [
  { id: "kochi", name: "Kochi", state: "Kerala", lat: 9.9312, lon: 76.2673 },
  { id: "kozhikode", name: "Kozhikode", state: "Kerala", lat: 11.2588, lon: 75.7804 },
  { id: "thiruvananthapuram", name: "Thiruvananthapuram", state: "Kerala", lat: 8.5241, lon: 76.9366 },
  { id: "mangaluru", name: "Mangaluru", state: "Karnataka", lat: 12.8698, lon: 74.8430 },
  { id: "karwar", name: "Karwar", state: "Karnataka", lat: 14.8137, lon: 74.1303 },
  { id: "chennai", name: "Chennai", state: "Tamil Nadu", lat: 13.0827, lon: 80.2707 },
  { id: "tuticorin", name: "Tuticorin", state: "Tamil Nadu", lat: 8.7642, lon: 78.1348 },
  { id: "mumbai", name: "Mumbai", state: "Maharashtra", lat: 18.9388, lon: 72.8354 },
  { id: "veraval", name: "Veraval", state: "Gujarat", lat: 20.9072, lon: 70.3673 },
  { id: "visakhapatnam", name: "Visakhapatnam", state: "Andhra Pradesh", lat: 17.6868, lon: 83.2185 },
  { id: "paradip", name: "Paradip", state: "Odisha", lat: 20.3170, lon: 86.6093 },
];

// ESRI World Imagery raster basemap specification (keyless, high-resolution)
const SATELLITE_STYLE = {
  version: 8,
  sources: {
    "esri-satellite": {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Esri, Maxar, Earthstar Geographics",
    },
    "esri-boundaries": {
      type: "raster",
      tiles: [
        "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: "satellite-tiles",
      type: "raster",
      source: "esri-satellite",
      minzoom: 0,
      maxzoom: 22,
    },
    {
      id: "places-overlay",
      type: "raster",
      source: "esri-boundaries",
      minzoom: 5,
      maxzoom: 22,
      paint: {
        "raster-opacity": 0.8,
      },
    },
  ],
};

export function SatelliteZoneMap({
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
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("maplibre-gl").Map | null>(null);
  const markersRef = useRef<import("maplibre-gl").Marker[]>([]);
  const [ready, setReady] = useState(false);

  // Recenter helper to fit bounds specifically to all points of the selected port region
  const fitToRegion = useCallback(
    (map: import("maplibre-gl").Map, animate = true) => {
      if (!data || !data.port_lat || !data.port_lon) return;

      map.resize();

      if (zones.length === 0) {
        map.flyTo({
          center: [data.port_lon, data.port_lat],
          zoom: 7.5,
          duration: animate ? 800 : 0,
        });
        return;
      }

      import("maplibre-gl").then(({ LngLatBounds }) => {
        const bounds = new LngLatBounds();
        bounds.extend([data.port_lon, data.port_lat]);
        zones.forEach((z) => {
          bounds.extend([z.lon, z.lat]);
        });

        // Fit so all zones and the departure port are fully visible without premature zoom clamp
        map.fitBounds(bounds, {
          padding: { top: 40, bottom: 40, left: 40, right: 40 },
          maxZoom: 10.5,
          duration: animate ? 800 : 0,
        });
      });
    },
    [data, zones]
  );

  // Initialize MapLibre GL
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    let isCancelled = false;

    import("maplibre-gl").then(({ Map }) => {
      if (isCancelled || !containerRef.current) return;

      const map = new Map({
        container: containerRef.current,
        style: SATELLITE_STYLE as unknown as import("maplibre-gl").StyleSpecification,
        center: [data.port_lon, data.port_lat],
        zoom: 7.0,
        minZoom: 4.6,
        maxZoom: 16,
        maxBounds: INDIA_COASTAL_BOUNDS,
        attributionControl: false,
      });

      // Suppress right-click browser context menu on map canvas
      map.getCanvas().addEventListener("contextmenu", (e) => {
        e.preventDefault();
      });

      map.on("load", () => {
        if (isCancelled) return;

        map.resize();

        // Tracks GeoJSON source
        map.addSource("zone-tracks", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });

        // Dark track casing for high contrast on light coast or dark sea
        map.addLayer({
          id: "tracks-casing",
          type: "line",
          source: "zone-tracks",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": "#0a1118",
            "line-width": ["case", ["==", ["get", "selected"], true], 5.5, 3],
            "line-opacity": 0.85,
          },
        });

        // Main nautical navigation track lines
        map.addLayer({
          id: "tracks-line",
          type: "line",
          source: "zone-tracks",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": ["get", "color"],
            "line-width": ["case", ["==", ["get", "selected"], true], 3.5, 2.0],
            "line-opacity": ["case", ["==", ["get", "selected"], true], 1.0, 0.7],
          },
        });

        setReady(true);
        fitToRegion(map, false);
      });

      mapRef.current = map;
    });

    // Resize observer
    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && containerRef.current) {
      ro = new ResizeObserver(() => {
        mapRef.current?.resize();
      });
      ro.observe(containerRef.current);
    }

    return () => {
      isCancelled = true;
      ro?.disconnect();
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      mapRef.current?.remove();
      mapRef.current = null;
      setReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Bootstrap MapLibre instance once on mount
  }, []);

  // Update track lines GeoJSON whenever zones, port, or selectedId changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    const src = map.getSource("zone-tracks") as import("maplibre-gl").GeoJSONSource | undefined;
    if (!src) return;

    const features = zones.map((z) => {
      const isSel = z.zone_id === selectedId;
      const c = PIN_HEX[z.profit_color] ?? PIN_HEX.neutral;
      return {
        type: "Feature" as const,
        geometry: {
          type: "LineString" as const,
          coordinates: [
            [data.port_lon, data.port_lat],
            [z.lon, z.lat],
          ],
        },
        properties: {
          zone_id: z.zone_id,
          selected: isSel,
          color: isSel ? "#22d3ee" : c,
        },
      };
    });

    src.setData({
      type: "FeatureCollection",
      features,
    });
  }, [ready, zones, data.port_lat, data.port_lon, selectedId]);

  // Re-fit region bounds whenever port or zones list changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    fitToRegion(map, true);
  }, [ready, data.port_id, zones, fitToRegion]);

  // Update HTML markers (pins 1..5 and departure port)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    // Remove previous markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    import("maplibre-gl").then(({ Marker }) => {
      // 1. Regional Indian Coastal Ports (Subtle Reference Markers)
      ALL_COASTAL_PORTS.forEach((p) => {
        // Skip current departure port (it has the prominent departure badge below)
        if (
          Math.abs(p.lat - data.port_lat) < 0.08 &&
          Math.abs(p.lon - data.port_lon) < 0.08
        ) {
          return;
        }

        const pEl = document.createElement("div");
        pEl.className = "select-none pointer-events-none";
        pEl.innerHTML = `
          <div style="display: inline-flex; align-items: center; gap: 4px; background: rgba(15, 23, 42, 0.78); border: 1px solid rgba(255, 255, 255, 0.28); border-radius: 6px; padding: 2px 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.5); backdrop-filter: blur(3px);">
            <span style="font-size: 10px; opacity: 0.85;">⚓</span>
            <span style="font-size: 9.5px; font-weight: 600; color: #f1f5f9; white-space: nowrap;">${p.name}</span>
          </div>
        `;

        const pMarker = new Marker({ element: pEl, anchor: "center" })
          .setLngLat([p.lon, p.lat])
          .addTo(map);
        markersRef.current.push(pMarker);
      });

      // 2. Departure Port Marker
      const portEl = document.createElement("div");
      portEl.className = "select-none";
      portEl.oncontextmenu = (e) => e.preventDefault();
      portEl.innerHTML = `
        <div style="display: inline-flex; align-items: center; gap: 6px; background: rgba(15, 23, 42, 0.92); border: 1.5px solid #22d3ee; border-radius: 8px; padding: 4px 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.6); backdrop-filter: blur(4px);">
          <span style="font-size: 13px; line-height: 1;">⚓</span>
          <div style="display: flex; flex-direction: column; text-align: left; line-height: 1.1;">
            <span style="font-size: 11px; font-weight: 700; color: #ffffff; white-space: nowrap;">${data.port_name}</span>
            <span style="font-size: 8px; font-weight: 700; color: #22d3ee; font-family: monospace; letter-spacing: 0.05em;">PORT OF DEPARTURE</span>
          </div>
        </div>
      `;

      const portMarker = new Marker({ element: portEl, anchor: "left" })
        .setLngLat([data.port_lon, data.port_lat])
        .addTo(map);
      markersRef.current.push(portMarker);

      // 3. Fishing Zone Pins (1, 2, 3, 4, 5)
      zones.forEach((z, index) => {
        const isSel = z.zone_id === selectedId;
        const c = PIN_HEX[z.profit_color] ?? PIN_HEX.neutral;

        const pinBtn = document.createElement("button");
        pinBtn.type = "button";
        pinBtn.setAttribute("aria-label", `Zone ${index + 1}: ${z.zone_name}`);
        pinBtn.className = "group relative cursor-pointer outline-none transition-transform duration-200 select-none";
        pinBtn.style.transform = isSel ? "scale(1.2)" : "scale(1.0)";
        pinBtn.style.background = "transparent";
        pinBtn.style.border = "none";
        pinBtn.style.padding = "0";

        // Click selects zone; right-click context menu suppressed
        pinBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          onSelect(z.zone_id);
        });
        pinBtn.addEventListener("contextmenu", (e) => {
          e.preventDefault();
        });

        // HTML structure: outer ring if selected + circular pin with number + Best badge
        let badgeHtml = "";
        if (z.is_best_zone) {
          badgeHtml = `
            <div style="position: absolute; top: -17px; left: 50%; transform: translateX(-50%); background: #b8862e; color: #ffffff; font-size: 8px; font-weight: 800; padding: 1.5px 5px; border-radius: 4px; border: 1px solid #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.6); white-space: nowrap; letter-spacing: 0.04em;">
              ★ BEST
            </div>
          `;
        }

        const ringHtml = isSel
          ? `<div style="position: absolute; inset: -5px; border-radius: 9999px; background: rgba(34, 211, 238, 0.35); border: 2px solid #22d3ee; box-shadow: 0 0 10px rgba(34, 211, 238, 0.7);"></div>`
          : "";

        pinBtn.innerHTML = `
          <div style="position: relative; display: flex; align-items: center; justify-content: center; width: 28px; height: 28px;">
            ${badgeHtml}
            ${ringHtml}
            <div style="width: 26px; height: 26px; border-radius: 9999px; background: ${c}; border: 2.5px solid #ffffff; box-shadow: 0 3px 8px rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; color: #ffffff; font-weight: 800; font-family: monospace; font-size: 11.5px; z-index: 10;">
              ${index + 1}
            </div>
          </div>
        `;

        const marker = new Marker({ element: pinBtn, anchor: "center" })
          .setLngLat([z.lon, z.lat])
          .addTo(map);
        markersRef.current.push(marker);
      });
    });
  }, [ready, zones, selectedId, data.port_lat, data.port_lon, data.port_name, onSelect]);

  return (
    <div
      className="relative h-[400px] w-full overflow-hidden rounded-xl border border-hairline/80 bg-slate-900 shadow-inner"
      onContextMenu={(e) => e.preventDefault()}
    >
      {/* Map container */}
      <div ref={containerRef} className="h-full w-full" />

      {/* Satellite badge overlay */}
      <div className="pointer-events-none absolute left-3 top-3 z-10 flex items-center gap-1.5 rounded-md bg-slate-950/85 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-ocean-cyan backdrop-blur-md border border-white/10 shadow-sm">
        <span className="size-2 rounded-full bg-ocean-cyan animate-pulse" />
        Satellite Region View · {data.port_name}
      </div>

      {/* Recenter & Zoom controls */}
      <div className="absolute right-3 top-3 z-10 flex flex-col gap-1.5">
        <button
          type="button"
          onClick={() => {
            if (mapRef.current) fitToRegion(mapRef.current, true);
          }}
          title="Recenter map to region"
          aria-label="Recenter map to region"
          className="flex size-7 items-center justify-center rounded-md bg-slate-950/85 text-white/90 hover:text-ocean-cyan hover:bg-slate-900 transition border border-white/15 shadow-md cursor-pointer backdrop-blur-md"
        >
          <RotateCcw className="size-3.5" />
        </button>
        <button
          type="button"
          onClick={() => mapRef.current?.zoomIn()}
          title="Zoom in"
          aria-label="Zoom in"
          className="flex size-7 items-center justify-center rounded-md bg-slate-950/85 text-white/90 hover:text-ocean-cyan hover:bg-slate-900 transition border border-white/15 shadow-md cursor-pointer backdrop-blur-md"
        >
          <ZoomIn className="size-3.5" />
        </button>
        <button
          type="button"
          onClick={() => mapRef.current?.zoomOut()}
          title="Zoom out"
          aria-label="Zoom out"
          className="flex size-7 items-center justify-center rounded-md bg-slate-950/85 text-white/90 hover:text-ocean-cyan hover:bg-slate-900 transition border border-white/15 shadow-md cursor-pointer backdrop-blur-md"
        >
          <ZoomOut className="size-3.5" />
        </button>
      </div>

      {/* Map orientation indicator */}
      <div className="pointer-events-none absolute bottom-3 right-3 z-10 flex items-center gap-1 rounded bg-slate-950/80 px-2 py-0.5 text-[9px] font-mono text-white/60 backdrop-blur-md border border-white/10">
        <Compass className="size-3 text-red-400" />
        <span>N ↑ · ESRI World Imagery</span>
      </div>
    </div>
  );
}
