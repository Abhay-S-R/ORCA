"use client";

// P5.20 UI — saved voyages, the frontend half of a backend that has been
// API-only since it was built. Same thin-wrapper pattern as lib/watches.ts.
import { authFetch } from "./auth";

export type RoutePoint = { lat: number; lon: number };

export type Voyage = {
  id: string;
  name: string | null;
  route: RoutePoint[];
  departure_at: string;
  vessel_id: string | null;
  watch_id: string | null;
  created_at: string;
};

export type VoyageIn = {
  name?: string | null;
  route: RoutePoint[];
  departure_at: string;
  vessel_id?: string | null;
};

export async function listVoyages(): Promise<Voyage[]> {
  const r = await authFetch("/api/voyages");
  if (!r.ok) throw new Error(`voyages ${r.status}`);
  return r.json();
}

export async function createVoyage(body: VoyageIn): Promise<Voyage> {
  const r = await authFetch("/api/voyages", { method: "POST", body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`create voyage ${r.status}`);
  return r.json();
}

export async function deleteVoyage(id: string): Promise<void> {
  const r = await authFetch(`/api/voyages/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error(`delete voyage ${r.status}`);
}

export async function promoteVoyage(id: string): Promise<Voyage> {
  const r = await authFetch(`/api/voyages/${id}/watch`, { method: "POST", body: JSON.stringify({}) });
  if (!r.ok) throw new Error(`promote voyage ${r.status}`);
  return r.json();
}

export async function unpromoteVoyage(id: string): Promise<Voyage> {
  const r = await authFetch(`/api/voyages/${id}/watch`, { method: "DELETE" });
  if (!r.ok) throw new Error(`unpromote voyage ${r.status}`);
  return r.json();
}
