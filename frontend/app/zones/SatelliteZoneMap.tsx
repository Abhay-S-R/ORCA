"use client";

// Satellite view map for fishing zones — displays high-resolution Esri satellite imagery
// fitted to the specific port region and its charted fishing grounds.
// Clean interactive pins 1, 2, 3, 4, 5 and selected departure port beacon (⚓).
// No intrusive floating black box on pins, and right-click context menu disabled.

import { useEffect, useRef, useState, useCallback } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { Compass, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import type { ProfitApiResponse, ZoneProfitResult } from "./zones-dashboard";
import { useZonesT } from "./translations";

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
  [95.0, 24.5], // NE: Bay of Bengal / Andaman & Nicobar / Bengal Delta / North of Gujarat coast
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
  onSelectPort?: (portId: string) => void;
}) {
  const { t, zoneName } = useZonesT();
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
      // 1. Selected Departure Port Marker Only (Clean Circular Beacon with Pulsing Halo, No lines/boxes)
      const portEl = document.createElement("div");
      portEl.className = "select-none pointer-events-none";
      portEl.oncontextmenu = (e) => e.preventDefault();
      portEl.innerHTML = `
        <div style="position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none;">
          <!-- Glowing Pulsing Radar Beacon Halo -->
          <div style="position: relative; display: flex; align-items: center; justify-content: center; width: 34px; height: 34px;">
            <div style="position: absolute; inset: 0px; border-radius: 9999px; background: rgba(34, 211, 238, 0.22); border: 1.5px solid #22d3ee; box-shadow: 0 0 14px rgba(34, 211, 238, 0.65); animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;"></div>
            <!-- Central Departure Circle Pin with ⚓ Anchor Icon -->
            <div style="position: relative; width: 28px; height: 28px; border-radius: 9999px; background: #0b1329; border: 2.5px solid #22d3ee; display: flex; align-items: center; justify-content: center; color: #38bdf8; font-size: 15px; line-height: 1; box-shadow: 0 4px 10px rgba(0,0,0,0.85); z-index: 10;">
              ⚓
            </div>
          </div>
          <!-- Clean floating label without box or connector line -->
          <div style="margin-top: 3px; display: flex; flex-direction: column; align-items: center; text-align: center; line-height: 1.15; pointer-events: none;">
            <span style="font-size: 11px; font-weight: 800; color: #ffffff; text-shadow: 0 1px 3px rgba(0,0,0,0.95), 0 0 8px rgba(0,0,0,0.9); white-space: nowrap; letter-spacing: 0.02em;">
              ${data.port_name}
            </span>
            <span style="font-size: 7.5px; font-weight: 800; color: #22d3ee; text-shadow: 0 1px 3px rgba(0,0,0,0.95), 0 0 6px rgba(0,0,0,0.9); letter-spacing: 0.08em; font-family: monospace;">
              ${t("DEPARTURE PORT")}
            </span>
          </div>
        </div>
      `;

      const portMarker = new Marker({ element: portEl, anchor: "top" })
        .setLngLat([data.port_lon, data.port_lat])
        .addTo(map);
      markersRef.current.push(portMarker);

      // 2. Fishing Zone Pins (1, 2, 3, 4, 5) with Clean, High-Contrast BEST ZONE badge
      zones.forEach((z, index) => {
        const isSel = z.zone_id === selectedId;
        const c = PIN_HEX[z.profit_color] ?? PIN_HEX.neutral;

        const pinBtn = document.createElement("button");
        pinBtn.type = "button";
        pinBtn.setAttribute("aria-label", `Zone ${index + 1}: ${zoneName(z.zone_name)}`);
        pinBtn.className = "group relative cursor-pointer outline-none transition-transform duration-200 select-none";
        pinBtn.style.transform = isSel ? "scale(1.15)" : "scale(1.0)";
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

        // High-contrast, clean BEST ZONE pill with pointer arrow floating clearly above the pin
        let badgeHtml = "";
        if (z.is_best_zone) {
          badgeHtml = `
            <div style="position: absolute; bottom: calc(100% + 7px); left: 50%; transform: translateX(-50%); display: flex; flex-direction: column; align-items: center; z-index: 30; pointer-events: none;">
              <div style="background: linear-gradient(135deg, #064e3b 0%, #047857 100%); color: #ecfdf5; font-size: 9px; font-weight: 800; padding: 2px 7.5px; border-radius: 9999px; border: 1.5px solid #34d399; box-shadow: 0 3px 10px rgba(0,0,0,0.85), 0 0 8px rgba(52, 211, 153, 0.4); white-space: nowrap; letter-spacing: 0.06em; display: flex; align-items: center; gap: 3.5px; line-height: 1.2;">
                <span style="color: #fbbf24; font-size: 10.5px; line-height: 1;">★</span>
                <span>${t("Best Zone")}</span>
              </div>
              <div style="width: 0; height: 0; border-left: 4.5px solid transparent; border-right: 4.5px solid transparent; border-top: 5px solid #047857; margin-top: -0.5px;"></div>
            </div>
          `;
        }

        const ringHtml = isSel
          ? `<div style="position: absolute; inset: -5px; border-radius: 9999px; background: rgba(34, 211, 238, 0.35); border: 2.5px solid #22d3ee; box-shadow: 0 0 12px rgba(34, 211, 238, 0.85);"></div>`
          : z.is_best_zone
          ? `<div style="position: absolute; inset: -3px; border-radius: 9999px; background: rgba(16, 185, 129, 0.2); border: 1.5px solid #10b981; box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);"></div>`
          : "";

        pinBtn.innerHTML = `
          <div style="position: relative; display: flex; align-items: center; justify-content: center; width: 28px; height: 28px;">
            ${badgeHtml}
            ${ringHtml}
            <div style="width: 26px; height: 26px; border-radius: 9999px; background: ${c}; border: 2.5px solid #ffffff; box-shadow: 0 3px 8px rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; color: #ffffff; font-weight: 800; font-family: monospace; font-size: 11.5px; z-index: 10;">
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
  }, [ready, zones, selectedId, data.port_lat, data.port_lon, data.port_name, onSelect, t, zoneName]);

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
        {t("Satellite Region View")} · ${data.port_name}
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
