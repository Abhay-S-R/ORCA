// Sea-route API client — thin wrappers matching the same pattern as
// lib/voyages.ts and lib/watches.ts.  No auth required for read endpoints;
// POST /api/sea-route is public (stateless, no user identity).
import { API_BASE } from "./apiBase";

export type LatLng = [number, number]; // [lat, lng]

export interface SeaRouteRequest {
  mode: "port_to_port" | "port_to_zone" | "map_pick";
  port_from?: string | null;
  port_to?: string | null;
  zone_id?: string | null;
  from_lat?: number | null;
  from_lng?: number | null;
  to_lat?: number | null;
  to_lng?: number | null;
  speed_knots?: number;
  departure?: string | null; // ISO-8601
}

export interface SeaRouteResult {
  coords: LatLng[];
  distance_nm: number;
  distance_km: number;
  hours: number;
  eta: string;
  warnings: string[];
}

export interface SeaPort {
  id: string;
  name: string;
  code: string;
  type: "major" | "minor" | "fishing_harbour";
  state: string;
  lat: number;
  lng: number;
}

export interface FishingZoneFeature {
  type: "Feature";
  geometry: unknown;
  properties: {
    id: string;
    name: string;
    entry_lat?: number | null;
    entry_lng?: number | null;
    [key: string]: unknown;
  };
}

export interface FishingZonesGeoJson {
  type: "FeatureCollection";
  features: FishingZoneFeature[];
}

export async function computeSeaRoute(req: SeaRouteRequest): Promise<SeaRouteResult> {
  const res = await fetch(`${API_BASE}/api/sea-route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = (body as { detail?: string }).detail ?? `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return res.json() as Promise<SeaRouteResult>;
}

export async function fetchSeaPorts(): Promise<SeaPort[]> {
  const res = await fetch(`${API_BASE}/api/sea-route/ports`);
  if (!res.ok) throw new Error(`ports ${res.status}`);
  const data = (await res.json()) as { ports: SeaPort[] };
  return data.ports;
}

export async function fetchFishingZones(): Promise<FishingZonesGeoJson> {
  const res = await fetch(`${API_BASE}/api/sea-route/fishing-zones`);
  if (!res.ok) throw new Error(`zones ${res.status}`);
  return res.json() as Promise<FishingZonesGeoJson>;
}

export async function fetchRestrictedAreas(): Promise<unknown> {
  const res = await fetch(`${API_BASE}/api/sea-route/restricted-areas`);
  if (!res.ok) throw new Error(`restricted ${res.status}`);
  return res.json();
}
