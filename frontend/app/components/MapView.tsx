"use client";

// Leaflet shell (plan §4 S5 Day 3) — everyone else adds layers to this. Must
// be dynamically imported with `ssr: false` from map/page.tsx: Leaflet
// touches `window` at module load time and breaks Next's server render.
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useState } from "react";
import { CircleMarker, GeoJSON, MapContainer, Marker, Popup, TileLayer, useMapEvents } from "react-leaflet";
import { Card } from "./Card";
import { SourceChip } from "./SourceChip";

// Bundlers break Leaflet's default marker icon path resolution; point it at
// the CDN copy rather than fighting the asset pipeline for three PNGs.
delete (L.Icon.Default.prototype as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Pilot region bounds (plan precondition — matches the GEBCO extract's own
// bbox, 77.5-80.5E / 7.5-10.5N).
const PILOT_BOUNDS: [[number, number], [number, number]] = [
  [7.5, 77.5],
  [10.5, 80.5],
];

// Acceptance-test position (plan §8) — Thoothukudi, used as the default
// "you are here" marker until Phase 2 wires a real geolocation/session flow.
const DEFAULT_USER: [number, number] = [8.8, 78.14];

type BoundaryGeoJson = { type: "FeatureCollection"; features: GeoJsonFeature[] };
type GeoJsonFeature = {
  type: "Feature";
  geometry: unknown;
  properties: { name: string; designation: string };
};
type PfzFeature = { geometry: { coordinates: [number, number] }; properties: { mean_sst_c: number; approx_area_km2: number } };
type DepthResult = { depth_m: number | null; on_land: boolean; shallow_hazard: boolean };
type Bearing = { bearing_deg: number; distance_nm: number };

function ClickHandler({ onClick }: { onClick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onClick(e.latlng.lat, e.latlng.lng) });
  return null;
}

export function MapView() {
  const [boundaries, setBoundaries] = useState<BoundaryGeoJson | null>(null);
  const [nearNames, setNearNames] = useState<Set<string>>(new Set());
  const [pfzFeatures, setPfzFeatures] = useState<PfzFeature[]>([]);
  const [clicked, setClicked] = useState<{ lat: number; lon: number } | null>(null);
  const [depth, setDepth] = useState<DepthResult | null>(null);
  const [bearing, setBearing] = useState<Bearing | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/map-layers?lat=${DEFAULT_USER[0]}&lon=${DEFAULT_USER[1]}`)
      .then((r) => r.json())
      .then((layers) => setBoundaries(layers.boundaries));

    // Proximity-gradient styling (plan §4 S5 Day 4): boundaries within 25nm
    // of the user render with a heavier stroke than distant ones.
    fetch(`${API_BASE}/api/zones-nearby?lat=${DEFAULT_USER[0]}&lon=${DEFAULT_USER[1]}&radius_nm=25`)
      .then((r) => r.json())
      .then((d) => setNearNames(new Set((d.boundaries as { name: string }[]).map((b) => b.name))));

    fetch(`${API_BASE}/api/zones`)
      .then((r) => r.json())
      .then((d) => setPfzFeatures(d.features));
  }, []);

  async function handleMapClick(lat: number, lon: number) {
    setClicked({ lat, lon });
    const [depthRes, bearingRes] = await Promise.all([
      fetch(`${API_BASE}/api/depth?lat=${lat}&lon=${lon}`).then((r) => r.json()),
      fetch(`${API_BASE}/api/bearing?from_lat=${DEFAULT_USER[0]}&from_lon=${DEFAULT_USER[1]}&to_lat=${lat}&to_lon=${lon}`).then((r) =>
        r.json()
      ),
    ]);
    setDepth(depthRes);
    setBearing(bearingRes);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="h-[70vh] w-full overflow-hidden rounded border border-black/10">
        <MapContainer bounds={PILOT_BOUNDS} className="h-full w-full">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {boundaries && (
            <GeoJSON
              data={boundaries as never}
              style={(feature) => {
                const near = feature && nearNames.has((feature.properties as { name: string }).name);
                const isMpa = feature?.properties.designation !== "India EEZ" && feature?.properties.designation !== "Sri Lanka EEZ";
                return {
                  color: isMpa ? "#b45309" : "#1d4ed8",
                  weight: near ? 3 : 1,
                  opacity: near ? 0.9 : 0.35,
                  fillOpacity: isMpa ? 0.15 : 0.03,
                };
              }}
              onEachFeature={(feature, layer) => {
                const props = feature.properties as { name: string; designation: string };
                layer.bindPopup(`<strong>${props.name}</strong><br/>${props.designation}`);
              }}
            />
          )}
          {pfzFeatures.map((f, i) => (
            <CircleMarker
              key={i}
              center={[f.geometry.coordinates[1], f.geometry.coordinates[0]]}
              radius={6}
              pathOptions={{ color: "#15803d", fillOpacity: 0.7 }}
            >
              <Popup>
                PFZ proxy zone — {f.properties.mean_sst_c} °C, ~{f.properties.approx_area_km2} km²
              </Popup>
            </CircleMarker>
          ))}
          <Marker position={DEFAULT_USER}>
            <Popup>You are here (Thoothukudi)</Popup>
          </Marker>
          <ClickHandler onClick={handleMapClick} />
        </MapContainer>
      </div>

      <Card title="Depth & bearing at last click">
        {!clicked && <p className="text-sm text-black/50">Click the map to read GEBCO depth and bearing from your position.</p>}
        {clicked && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-black/50">Position</dt>
            <dd>
              {clicked.lat.toFixed(4)}, {clicked.lon.toFixed(4)}
            </dd>
            <dt className="text-black/50">Depth</dt>
            <dd>
              {depth?.on_land ? "On land" : depth?.depth_m != null ? `${depth.depth_m} m` : "…"}
              {depth?.shallow_hazard && <span className="ml-2 text-safety-caution-text">shallow hazard</span>}
            </dd>
            <dt className="text-black/50">Bearing from you</dt>
            <dd>{bearing ? `${bearing.bearing_deg}°, ${bearing.distance_nm} nm` : "…"}</dd>
          </dl>
        )}
        {clicked && (
          <div className="mt-3">
            {/* Exit criterion 4 — every number on screen carries dataset +
                timestamp, even a static reference grid like GEBCO. */}
            <SourceChip dataset="GEBCO 2026 Grid" acquisitionTimestamp="2026-08-30T00:00:00Z" />
          </div>
        )}
      </Card>

      <p className="text-xs text-black/50">
        Boundaries: Marine Regions VLIZ EEZ dataset · UNEP-WCMC WDPA / OpenStreetMap (marine protected areas).
      </p>
    </div>
  );
}
