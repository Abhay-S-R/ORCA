"use client";

// Coastal Sea Route planner component — integrated into Voyage.
// Three modes (port→zone, port→port, map-pick) feeding the coastal A* routing engine
// with realistic polyline, IMBL boundaries, and satellite basemap switcher.
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Info, Layers, Loader2, RotateCcw, Route } from "lucide-react";
import { BASEMAP_RASTERS } from "../map/basemap";
import { Button } from "../components/Button";
import { Field, inputClass } from "../components/Field";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import {
  computeSeaRoute,
  fetchFishingZones,
  fetchMaritimeBoundaryLines,
  fetchRestrictedAreas,
  fetchSeaPorts,
  type FishingZoneFeature,
  type FishingZonesGeoJson,
  type SeaPort,
  type SeaRouteResult,
} from "../lib/seaRoute";

// India bbox — must match backend config.
const INDIA_BBOX = { w: 66, e: 95, s: 5, n: 24 };

type Mode = "port_to_zone" | "port_to_port" | "map_pick";

function hoursLabel(h: number): string {
  if (h < 24) return `${h.toFixed(1)} h`;
  const days = Math.floor(h / 24);
  const rem = h % 24;
  return rem > 0.5 ? `${days}d ${rem.toFixed(0)}h` : `${days} days`;
}

type GeoJSONData = Parameters<typeof import("maplibre-gl").GeoJSONSource.prototype.setData>[0];

function SeaRouteMap({
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
  const [satellite, setSatellite] = useState(false);
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
            layout: { visibility: "none" },
            paint: { "raster-opacity": 1.0 },
          },
          firstSymbol
        );

        // ── Fishing zones layer ──────────────────────────────────────────────
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
        [[Math.min(...lngs) - 0.35, Math.min(...lats) - 0.35],
         [Math.max(...lngs) + 0.35, Math.max(...lats) + 0.35]],
        { padding: 50, duration: 800, maxZoom: 12 },
      );
    } else {
      (src as import("maplibre-gl").GeoJSONSource).setData({
        type: "FeatureCollection", features: [],
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

  // Start pin marker for Map Pick mode.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    import("maplibre-gl").then(({ Marker }) => {
      if (!mapRef.current) return;
      if (startPin) {
        if (!startMarkerRef.current) {
          const el = document.createElement("div");
          el.className = "flex items-center justify-center w-6 h-6 rounded-full bg-emerald-600 text-white font-bold text-[10px] shadow-lg border-2 border-white pointer-events-none";
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

  // End pin marker for Map Pick mode.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    import("maplibre-gl").then(({ Marker }) => {
      if (!mapRef.current) return;
      if (endPin) {
        if (!endMarkerRef.current) {
          const el = document.createElement("div");
          el.className = "flex items-center justify-center w-6 h-6 rounded-full bg-rose-600 text-white font-bold text-[10px] shadow-lg border-2 border-white pointer-events-none";
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

  // Toggle satellite basemap and re-style route/zone layers for high contrast
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (map.getLayer("basemap-satellite-raster")) {
      map.setLayoutProperty(
        "basemap-satellite-raster",
        "visibility",
        satellite ? "visible" : "none"
      );
    }
    if (map.getLayer("sea-route-casing")) {
      map.setPaintProperty(
        "sea-route-casing",
        "line-opacity",
        satellite ? 0.75 : 0.9
      );
    }
    if (map.getLayer("sea-route-line")) {
      map.setPaintProperty(
        "sea-route-line",
        "line-color",
        satellite ? "#ff3366" : "#8a3b52"
      );
    }
    if (map.getLayer("sea-imbl-lines-layer")) {
      map.setPaintProperty(
        "sea-imbl-lines-layer",
        "line-color",
        satellite ? "#fbbf24" : "#d97706"
      );
    }
    if (map.getLayer("sea-zones-fill")) {
      map.setPaintProperty(
        "sea-zones-fill",
        "fill-color",
        satellite ? "#06b6d4" : "#2f6f74"
      );
      map.setPaintProperty(
        "sea-zones-fill",
        "fill-opacity",
        satellite ? 0.22 : 0.12
      );
    }
    if (map.getLayer("sea-zones-outline")) {
      map.setPaintProperty(
        "sea-zones-outline",
        "line-color",
        satellite ? "#22d3ee" : "#2f6f74"
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
          {!startPin ? "Click the map to set start point" : !endPin ? "Click the map to set end point" : "Points set — ready to calculate"}
        </div>
      )}
      {/* Legend */}
      <div className="absolute top-3 left-3 z-10 flex flex-col gap-1.5 rounded-lg bg-shelf-1/90 p-2.5 text-[10px] font-mono shadow ring-1 ring-hairline backdrop-blur-sm">
        <span className="flex items-center gap-1.5">
          <span className={`inline-block h-2 w-4 rounded-sm transition-colors ${satellite ? "bg-[#ff3366]" : "bg-[#8a3b52]"}`} />
          Route
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-4 border-b-2 border-dashed border-[#d97706] bg-transparent" />
          IMBL Boundary
        </span>
        <span className="flex items-center gap-1.5">
          <span className={`inline-block h-2 w-4 rounded-sm transition-colors ${satellite ? "bg-[#06b6d4]/70" : "bg-[#2f6f74]/50"}`} />
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

export function CoastalSeaRoute() {
  const [mode, setMode] = useState<Mode>("port_to_zone");

  // Port → Zone
  const [fromPortId, setFromPortId] = useState("");
  const [toZoneId, setToZoneId] = useState("");

  // Port → Port
  const [fromPortId2, setFromPortId2] = useState("");
  const [toPortId2, setToPortId2] = useState("");

  // Map pick
  const [pickingPin, setPickingPin] = useState<"start" | "end">("start");
  const [startPin, setStartPin] = useState<[number, number] | null>(null); // [lat, lng]
  const [endPin, setEndPin] = useState<[number, number] | null>(null);

  // Shared
  const [speedKnots, setSpeedKnots] = useState(8);
  const [departure, setDeparture] = useState("");

  // Data
  const [ports, setPorts] = useState<SeaPort[]>([]);
  const [zones, setZones] = useState<FishingZonesGeoJson | null>(null);
  const [restricted, setRestricted] = useState<unknown>(null);
  const [boundaryLines, setBoundaryLines] = useState<unknown>(null);

  // State
  const [result, setResult] = useState<SeaRouteResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load reference data on mount.
  useEffect(() => {
    fetchSeaPorts().then(setPorts).catch(() => {});
    fetchFishingZones().then(setZones).catch(() => {});
    fetchRestrictedAreas().then(setRestricted).catch(() => {});
    fetchMaritimeBoundaryLines().then(setBoundaryLines).catch(() => {});
  }, []);

  // Map-pick click handler.
  const handleMapClick = useCallback((lat: number, lng: number) => {
    if (mode !== "map_pick") return;
    // Validate India bbox.
    if (lat < INDIA_BBOX.s || lat > INDIA_BBOX.n || lng < INDIA_BBOX.w || lng > INDIA_BBOX.e) {
      setError("Please select a point within Indian waters");
      return;
    }
    if (pickingPin === "start") {
      setStartPin([lat, lng]);
      setPickingPin("end");
      setError(null);
    } else {
      setEndPin([lat, lng]);
      setPickingPin("start");
      setError(null);
    }
  }, [mode, pickingPin, setError]);

  function resetMapPick() {
    setStartPin(null);
    setEndPin(null);
    setPickingPin("start");
    setResult(null);
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let req;
      if (mode === "port_to_zone") {
        req = { mode, port_from: fromPortId, zone_id: toZoneId, speed_knots: speedKnots, departure: departure || null };
      } else if (mode === "port_to_port") {
        req = { mode, port_from: fromPortId2, port_to: toPortId2, speed_knots: speedKnots, departure: departure || null };
      } else {
        if (!startPin || !endPin) {
          setError("Click the map to set start and end points first");
          setLoading(false);
          return;
        }
        req = {
          mode,
          from_lat: startPin[0], from_lng: startPin[1],
          to_lat: endPin[0], to_lng: endPin[1],
          speed_knots: speedKnots,
          departure: departure || null,
        };
      }
      const r = await computeSeaRoute(req);
      setResult(r);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Routing failed";
      // Match spec error messages.
      if (msg.toLowerCase().includes("land")) {
        setError("Selected point is on land, please choose a point in the sea");
      } else if (msg.toLowerCase().includes("indian waters") || msg.toLowerCase().includes("bbox")) {
        setError("Please select a point within Indian waters");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  const canSubmit =
    !loading &&
    (mode === "port_to_zone"
      ? fromPortId && toZoneId
      : mode === "port_to_port"
      ? fromPortId2 && toPortId2
      : startPin && endPin);

  const majorPorts = ports.filter((p) => p.type === "major");
  const minorPorts = ports.filter((p) => p.type !== "major" && p.type !== "fishing_harbour");
  const fishingPorts = ports.filter((p) => p.type === "fishing_harbour");
  const zoneList = zones?.features ?? [];

  return (
    <div className="grid gap-6 lg:grid-cols-[400px_1fr]">
      {/* ── Left panel ─────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4">
        <Panel title="Coastal Route Planner" dense>
          {/* Mode tabs */}
          <div className="mb-4 flex rounded-lg border border-hairline overflow-hidden text-xs font-semibold">
            {(["port_to_zone", "port_to_port", "map_pick"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => { setMode(m); setResult(null); setError(null); }}
                className={`flex-1 px-2 py-2 transition-colors ${
                  mode === m
                    ? "bg-ocean-cyan text-on-accent"
                    : "bg-shelf-1/60 text-ink-muted hover:bg-shelf-2/80"
                }`}
              >
                {m === "port_to_zone" ? "Port → Zone" : m === "port_to_port" ? "Port → Port" : "Map Pick"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-1">
            {/* ── Mode 1: Port → Fishing Zone ─────────────────────────── */}
            {mode === "port_to_zone" && (
              <>
                <Field label="From port">
                  {(id) => (
                    <select id={id} value={fromPortId} onChange={(e) => setFromPortId(e.target.value)} className={inputClass}>
                      <option value="">Select a port…</option>
                      {majorPorts.length > 0 && <optgroup label="Major Ports">{majorPorts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.state})</option>)}</optgroup>}
                      {minorPorts.length > 0 && <optgroup label="Minor Ports">{minorPorts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.state})</option>)}</optgroup>}
                      {fishingPorts.length > 0 && <optgroup label="Fishing Harbours">{fishingPorts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.state})</option>)}</optgroup>}
                    </select>
                  )}
                </Field>
                <Field label="To fishing zone">
                  {(id) => (
                    <select id={id} value={toZoneId} onChange={(e) => setToZoneId(e.target.value)} className={inputClass}>
                      <option value="">Select a zone…</option>
                      {zoneList.map((z: FishingZoneFeature) => (
                        <option key={z.properties.id} value={z.properties.id}>{z.properties.name}</option>
                      ))}
                    </select>
                  )}
                </Field>
                <p className="mb-1 text-[11px] text-ink-dim">Route ends at the zone entry point (boundary nearest to port).</p>
              </>
            )}

            {/* ── Mode 2: Port → Port ──────────────────────────────────── */}
            {mode === "port_to_port" && (
              <>
                <Field label="From port">
                  {(id) => (
                    <select id={id} value={fromPortId2} onChange={(e) => setFromPortId2(e.target.value)} className={inputClass}>
                      <option value="">Select start port…</option>
                      {majorPorts.length > 0 && <optgroup label="Major Ports">{majorPorts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.state})</option>)}</optgroup>}
                      {minorPorts.length > 0 && <optgroup label="Minor Ports">{minorPorts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.state})</option>)}</optgroup>}
                      {fishingPorts.length > 0 && <optgroup label="Fishing Harbours">{fishingPorts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.state})</option>)}</optgroup>}
                    </select>
                  )}
                </Field>
                <Field label="To port">
                  {(id) => (
                    <select id={id} value={toPortId2} onChange={(e) => setToPortId2(e.target.value)} className={inputClass}>
                      <option value="">Select end port…</option>
                      {majorPorts.length > 0 && <optgroup label="Major Ports">{majorPorts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.state})</option>)}</optgroup>}
                      {minorPorts.length > 0 && <optgroup label="Minor Ports">{minorPorts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.state})</option>)}</optgroup>}
                      {fishingPorts.length > 0 && <optgroup label="Fishing Harbours">{fishingPorts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.state})</option>)}</optgroup>}
                    </select>
                  )}
                </Field>
              </>
            )}

            {/* ── Mode 3: Map Pick ─────────────────────────────────────── */}
            {mode === "map_pick" && (
              <div className="mb-3 flex flex-col gap-2">
                <div className="flex gap-2">
                  <div className={`flex-1 rounded-lg border px-3 py-2 text-xs ${startPin ? "border-ocean-cyan/60 bg-shelf-2/60 text-ink" : "border-hairline text-ink-dim"}`}>
                    <span className="block text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim mb-0.5">Start</span>
                    {startPin ? `${startPin[0].toFixed(4)}°N, ${startPin[1].toFixed(4)}°E` : "Click map…"}
                  </div>
                  <div className={`flex-1 rounded-lg border px-3 py-2 text-xs ${endPin ? "border-accent/60 bg-shelf-2/60 text-ink" : "border-hairline text-ink-dim"}`}>
                    <span className="block text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim mb-0.5">End</span>
                    {endPin ? `${endPin[0].toFixed(4)}°N, ${endPin[1].toFixed(4)}°E` : "Click map…"}
                  </div>
                </div>
                <Button type="button" variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={resetMapPick} className="self-start">
                  Reset picks
                </Button>
                <p className="text-[11px] text-ink-dim">
                  Picking: <span className="font-semibold text-ink">{pickingPin === "start" ? "start point" : "end point"}</span> — both must be in the sea within Indian waters.
                </p>
              </div>
            )}

            {/* ── Shared controls ──────────────────────────────────────── */}
            <div className="grid grid-cols-2 gap-x-3">
              <Field label="Speed (knots)">
                {(id) => (
                  <input id={id} type="number" min={1} max={50} step={0.5} value={speedKnots}
                    onChange={(e) => setSpeedKnots(Number(e.target.value))} className={inputClass} />
                )}
              </Field>
              <Field label="Departure" hint="Defaults to now">
                {(id) => (
                  <input id={id} type="datetime-local" value={departure}
                    onChange={(e) => setDeparture(e.target.value)} className={inputClass} />
                )}
              </Field>
            </div>

            <Button
              type="submit"
              variant="primary"
              className="mt-1"
              disabled={!canSubmit}
              icon={loading ? <Loader2 className="size-4 animate-spin" /> : <Route className="size-4" />}
            >
              {loading ? "Routing…" : "Calculate Route"}
            </Button>
          </form>
        </Panel>

        {/* ── Result card ────────────────────────────────────────────────── */}
        {result && (
          <Panel title="Voyage Summary">
            <ReadoutGrid cols={2}>
              <Readout label="Distance" value={result.distance_nm.toFixed(1)} unit="nm" />
              <Readout label="Distance" value={result.distance_km.toFixed(0)} unit="km" />
              <Readout label="Duration" value={hoursLabel(result.hours)} />
              <Readout label="ETA" value={new Date(result.eta).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" })} hint="IST" />
            </ReadoutGrid>

            {result.warnings.length > 0 && (
              <div className="mt-4 flex flex-col gap-1.5">
                {result.warnings.map((w, i) => (
                  <div
                    key={i}
                    className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-[11px] leading-snug ${
                      w.startsWith("DISCLAIMER") || w.startsWith("NOTE")
                        ? "border-hairline/60 bg-shelf-2/30 text-ink-dim"
                        : w.toLowerCase().includes("monsoon")
                        ? "border-caution/40 bg-caution/8 text-ink-muted"
                        : "border-no-go/30 bg-no-go/6 text-ink-muted"
                    }`}
                  >
                    <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                    <span>{w}</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2.5 rounded-xl border border-no-go/40 bg-no-go/8 px-3.5 py-3 text-xs text-no-go">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span className="font-medium">{error}</span>
          </div>
        )}

        {/* Disclaimer */}
        <div className="flex items-start gap-2 rounded-lg border border-hairline/50 bg-shelf-2/30 px-3 py-2.5 text-[11px] text-ink-dim">
          <Info className="mt-0.5 size-3.5 shrink-0 text-ocean-cyan" aria-hidden="true" />
          <span>
            Route strictly adheres to official <span className="font-semibold text-ink">International Maritime Boundary Lines (IMBL)</span> and Marine Protected Areas (MPA) geofences. Always follow Indian Coast Guard advisories and official navigational charts.
          </span>
        </div>
      </div>

      {/* ── Right: map ───────────────────────────────────────────────────── */}
      <SeaRouteMap
        result={result}
        mapPickMode={mode === "map_pick"}
        startPin={startPin}
        endPin={endPin}
        onMapClick={handleMapClick}
        zones={zones}
        restricted={restricted}
        boundaryLines={boundaryLines}
      />
    </div>
  );
}
