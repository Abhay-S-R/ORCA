"use client";

// Sea Route MapLibre component — extracted from sea-route and embedded into Voyage.
// Shows the actual obstacle-avoiding route from source to destination,
// along with Fishing zones, IMBL boundaries, Restricted areas, and Satellite/Chart switcher.
import { useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { Layers } from "lucide-react";
import { BASEMAP_RASTERS } from "../map/basemap";
import type { FishingZonesGeoJson, SeaRouteResult } from "../lib/seaRoute";

type GeoJSONData = Parameters<typeof import("maplibre-gl").GeoJSONSource.prototype.setData>[0];

export function SeaRouteMap({
  result,
  mapPickMode,
  startPin,
  endPin,
  onMapClick,
  zones,
  restricted,
  boundaryLines,
}: {
  result: SeaRouteResult | null;
  mapPickMode: boolean;
  startPin: [number, number] | null; // [lat, lng]
  endPin: [number, number] | null;
  onMapClick: (lat: number, lng: number) => void;
  zones: FishingZonesGeoJson | null;
  restricted: unknown;
  boundaryLines: unknown;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("maplibre-gl").Map | null>(null);
  const [ready, setReady] = useState(false);
  const [satellite, setSatellite] = useState(true);
  const satelliteRef = useRef(satellite);
  const startMarkerRef = useRef<import("maplibre-gl").Marker | null>(null);
  const endMarkerRef = useRef<import("maplibre-gl").Marker | null>(null);

  useEffect(() => {
    satelliteRef.current = satellite;
  }, [satellite]);

  // Bootstrap map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    import("maplibre-gl").then(({ Map, NavigationControl }) => {
      const map = new Map({
        container: containerRef.current!,
        style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        center: [80, 15],
        zoom: 4.5,
        maxBounds: [[60, 2], [100, 27]],
      });
      map.addControl(new NavigationControl({ showCompass: false }), "top-right");

      map.on("load", () => {
        // ── Satellite raster basemap layer ──────────────────────────────────
        const firstSymbol = map.getStyle().layers?.find((l) => l.type === "symbol")?.id;
        map.addSource("basemap-satellite", BASEMAP_RASTERS.satellite.source);
        map.addLayer(
          {
            id: "basemap-satellite-raster",
            type: "raster",
            source: "basemap-satellite",
            layout: { visibility: satelliteRef.current ? "visible" : "none" },
            paint: { "raster-opacity": 1 },
          },
          firstSymbol,
        );

        // ── Fishing zones layer ─────────────────────────────────────────────
        map.addSource("sea-zones", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "sea-zones-fill",
          type: "fill",
          source: "sea-zones",
          paint: {
            "fill-color": satelliteRef.current ? "#06b6d4" : "#2f6f74",
            "fill-opacity": satelliteRef.current ? 0.22 : 0.12,
          },
        });
        map.addLayer({
          id: "sea-zones-outline",
          type: "line",
          source: "sea-zones",
          paint: {
            "line-color": satelliteRef.current ? "#22d3ee" : "#2f6f74",
            "line-width": 1.5,
          },
        });

        // ── Restricted areas layer ──────────────────────────────────────────
        map.addSource("sea-restricted", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "sea-restricted-fill",
          type: "fill",
          source: "sea-restricted",
          paint: {
            "fill-color": "#b3402c",
            "fill-opacity": 0.08,
          },
        });
        map.addLayer({
          id: "sea-restricted-outline",
          type: "line",
          source: "sea-restricted",
          paint: {
            "line-color": "#b3402c",
            "line-width": 1.2,
            "line-dasharray": [3, 2],
          },
        });

        // ── IMBL Treaty Boundary Lines layer ─────────────────────────────────
        map.addSource("sea-imbl-lines", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "sea-imbl-lines-layer",
          type: "line",
          source: "sea-imbl-lines",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": satelliteRef.current ? "#fbbf24" : "#d97706",
            "line-width": 2.2,
            "line-dasharray": [5, 3],
            "line-opacity": 0.95,
          },
        });

        // ── Route polyline & endpoints ──────────────────────────────────────
        map.addSource("sea-route", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        // High-contrast casing underlay for both chart and satellite
        map.addLayer({
          id: "sea-route-casing",
          type: "line",
          source: "sea-route",
          filter: ["==", "$type", "LineString"],
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": "#ffffff",
            "line-width": 7,
            "line-opacity": satelliteRef.current ? 0.75 : 0.9,
          },
        });
        map.addLayer({
          id: "sea-route-line",
          type: "line",
          source: "sea-route",
          filter: ["==", "$type", "LineString"],
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": satelliteRef.current ? "#ff3366" : "#8a3b52",
            "line-width": 4,
            "line-opacity": 1.0,
          },
        });
        // Waypoint circles: Green for start, Red for destination
        map.addLayer({
          id: "sea-route-endpoints",
          type: "circle",
          source: "sea-route",
          filter: ["==", "$type", "Point"],
          paint: {
            "circle-radius": 6,
            "circle-color": [
              "case",
              ["==", ["get", "point_type"], "start"],
              "#10b981",
              "#f43f5e",
            ],
            "circle-stroke-width": 2,
            "circle-stroke-color": "#ffffff",
          },
        });

        setReady(true);
      });

      // Map-pick click handler.
      map.on("click", (e) => {
        onMapClick(e.lngLat.lat, e.lngLat.lng);
      });

      mapRef.current = map;
    });

    return () => {
      setReady(false);
      startMarkerRef.current?.remove();
      endMarkerRef.current?.remove();
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update route source when ready or result changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const src = map.getSource("sea-route");
    if (!src || src.type !== "geojson") return;
    if (result && result.coords.length > 0) {
      const coords = result.coords.map(([lat, lng]) => [lng, lat]);
      const features = [
        {
          type: "Feature" as const,
          geometry: { type: "LineString" as const, coordinates: coords },
          properties: {},
        },
        {
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: coords[0] },
          properties: { point_type: "start" },
        },
        {
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: coords[coords.length - 1] },
          properties: { point_type: "end" },
        },
      ];
      (src as import("maplibre-gl").GeoJSONSource).setData({
        type: "FeatureCollection",
        features,
      } as unknown as GeoJSONData);

      // Fit to route bounds with smooth easing.
      const lngs = coords.map((c) => c[0]);
      const lats = coords.map((c) => c[1]);
      map.fitBounds(
        [
          [Math.min(...lngs) - 0.35, Math.min(...lats) - 0.35],
          [Math.max(...lngs) + 0.35, Math.max(...lats) + 0.35],
        ],
        { padding: 50, duration: 800, maxZoom: 12 },
      );
    } else {
      (src as import("maplibre-gl").GeoJSONSource).setData({
        type: "FeatureCollection",
        features: [],
      });
    }
  }, [ready, result]);

  // Update zones source when ready or zones change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !zones) return;
    const src = map.getSource("sea-zones");
    if (src?.type === "geojson") {
      (src as import("maplibre-gl").GeoJSONSource).setData(zones as unknown as GeoJSONData);
    }
  }, [ready, zones]);

  // Update restricted source when ready or restricted change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !restricted) return;
    const src = map.getSource("sea-restricted");
    if (src?.type === "geojson") {
      (src as import("maplibre-gl").GeoJSONSource).setData(restricted as GeoJSONData);
    }
  }, [ready, restricted]);

  // Update IMBL boundary lines source when ready or boundaryLines change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !boundaryLines) return;
    const src = map.getSource("sea-imbl-lines");
    if (src?.type === "geojson") {
      (src as import("maplibre-gl").GeoJSONSource).setData(boundaryLines as GeoJSONData);
    }
  }, [ready, boundaryLines]);

  // Start pin marker for Map Pick mode or selected endpoints.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    import("maplibre-gl").then(({ Marker }) => {
      if (!mapRef.current) return;
      if (startPin) {
        if (!startMarkerRef.current) {
          const el = document.createElement("div");
          el.className =
            "flex items-center justify-center w-6 h-6 rounded-full bg-emerald-600 text-white font-bold text-[10px] shadow-lg border-2 border-white pointer-events-none";
          el.innerText = "A";
          startMarkerRef.current = new Marker({ element: el })
            .setLngLat([startPin[1], startPin[0]])
            .addTo(mapRef.current);
        } else {
          startMarkerRef.current.setLngLat([startPin[1], startPin[0]]);
        }
      } else {
        startMarkerRef.current?.remove();
        startMarkerRef.current = null;
      }
    });
  }, [ready, startPin]);

  // End pin marker for Map Pick mode or selected endpoints.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    import("maplibre-gl").then(({ Marker }) => {
      if (!mapRef.current) return;
      if (endPin) {
        if (!endMarkerRef.current) {
          const el = document.createElement("div");
          el.className =
            "flex items-center justify-center w-6 h-6 rounded-full bg-rose-600 text-white font-bold text-[10px] shadow-lg border-2 border-white pointer-events-none";
          el.innerText = "B";
          endMarkerRef.current = new Marker({ element: el })
            .setLngLat([endPin[1], endPin[0]])
            .addTo(mapRef.current);
        } else {
          endMarkerRef.current.setLngLat([endPin[1], endPin[0]]);
        }
      } else {
        endMarkerRef.current?.remove();
        endMarkerRef.current = null;
      }
    });
  }, [ready, endPin]);

  // Map-pick cursor.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.getCanvas().style.cursor = mapPickMode ? "crosshair" : "";
  }, [mapPickMode]);

  // Toggle satellite basemap and re-style route/zone layers for high contrast.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (map.getLayer("basemap-satellite-raster")) {
      map.setLayoutProperty(
        "basemap-satellite-raster",
        "visibility",
        satellite ? "visible" : "none",
      );
    }
    if (map.getLayer("sea-route-casing")) {
      map.setPaintProperty(
        "sea-route-casing",
        "line-opacity",
        satellite ? 0.75 : 0.9,
      );
    }
    if (map.getLayer("sea-route-line")) {
      map.setPaintProperty(
        "sea-route-line",
        "line-color",
        satellite ? "#ff3366" : "#8a3b52",
      );
    }
    if (map.getLayer("sea-imbl-lines-layer")) {
      map.setPaintProperty(
        "sea-imbl-lines-layer",
        "line-color",
        satellite ? "#fbbf24" : "#d97706",
      );
    }
    if (map.getLayer("sea-zones-fill")) {
      map.setPaintProperty(
        "sea-zones-fill",
        "fill-color",
        satellite ? "#06b6d4" : "#2f6f74",
      );
      map.setPaintProperty(
        "sea-zones-fill",
        "fill-opacity",
        satellite ? 0.22 : 0.12,
      );
    }
    if (map.getLayer("sea-zones-outline")) {
      map.setPaintProperty(
        "sea-zones-outline",
        "line-color",
        satellite ? "#22d3ee" : "#2f6f74",
      );
    }
  }, [ready, satellite]);

  return (
    <div className="relative w-full">
      <div
        ref={containerRef}
        className="h-[440px] min-h-[380px] lg:h-[500px] w-full rounded-2xl shadow-xl ring-1 ring-hairline overflow-hidden"
        aria-label="Sea route map"
      />
      {/* Basemap switcher: Chart vs Satellite */}
      <div
        role="group"
        aria-label="Basemap style"
        className="absolute top-3 right-14 z-10 flex rounded-lg border border-hairline bg-shelf-1/90 p-0.5 text-xs font-medium shadow-md backdrop-blur-sm"
      >
        <button
          type="button"
          onClick={() => setSatellite(false)}
          className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
            !satellite
              ? "bg-ocean-cyan text-on-accent font-semibold shadow-xs"
              : "text-ink-muted hover:text-ink hover:bg-shelf-2/60"
          }`}
          aria-pressed={!satellite}
        >
          Chart
        </button>
        <button
          type="button"
          onClick={() => setSatellite(true)}
          className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors ${
            satellite
              ? "bg-ocean-cyan text-on-accent font-semibold shadow-xs"
              : "text-ink-muted hover:text-ink hover:bg-shelf-2/60"
          }`}
          aria-pressed={satellite}
        >
          <Layers className="h-3.5 w-3.5" />
          Satellite
        </button>
      </div>

      {/* Map-pick overlay label */}
      {mapPickMode && (
        <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-lg bg-shelf-1/90 px-3.5 py-2 text-xs font-semibold text-ink shadow-lg backdrop-blur-sm ring-1 ring-hairline">
          {!startPin
            ? "Click the map to set start point"
            : !endPin
            ? "Click the map to set end point"
            : "Points set — ready to calculate"}
        </div>
      )}

      {/* Legend */}
      <div className="absolute top-3 left-3 z-10 flex flex-col gap-1.5 rounded-lg bg-shelf-1/90 p-2.5 text-[10px] font-mono shadow ring-1 ring-hairline backdrop-blur-sm">
        <span className="flex items-center gap-1.5">
          <span
            className={`inline-block h-2 w-4 rounded-sm transition-colors ${
              satellite ? "bg-[#ff3366]" : "bg-[#8a3b52]"
            }`}
          />
          Route
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-4 border-b-2 border-dashed border-[#d97706] bg-transparent" />
          IMBL Boundary
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className={`inline-block h-2 w-4 rounded-sm transition-colors ${
              satellite ? "bg-[#06b6d4]/70" : "bg-[#2f6f74]/50"
            }`}
          />
          Fishing zones
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-4 rounded-sm bg-[#b3402c]/40" />
          Restricted (2 nm)
        </span>
      </div>
    </div>
  );
}
