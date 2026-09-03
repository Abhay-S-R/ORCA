"use client";

import { API_BASE, authFetch, getToken } from "./auth";

// ---------------------------------------------------------------------------
// Types. `WatchBadge` is the D2 -> D3 map handoff contract (plan §14) — D3
// imports this type and renders it; D2 never touches MapView. Additive-only.
// ---------------------------------------------------------------------------

export type WatchType =
  | "weather"
  | "wave_height"
  | "lightning"
  | "cyclone"
  | "geofence_approach"
  | "pfz_shift";

export type Severity = "info" | "advisory" | "warning" | "danger";
export type NotificationStatus = "sent" | "simulated" | "failed";

export type Watch = {
  id: string;
  watch_type: WatchType;
  lat: number | null;
  lon: number | null;
  radius_km: number | null;
  vessel_id: string | null;
  thresholds: Record<string, number>;
  channels: string[];
  enabled: boolean;
  last_fired_at: string | null;
  created_at: string;
};

export type WatchIn = {
  watch_type: WatchType;
  lat?: number | null;
  lon?: number | null;
  radius_km?: number | null;
  thresholds?: Record<string, number>;
  channels?: string[];
  enabled?: boolean;
};

export type OrcaNotification = {
  id: string;
  watch_id: string | null;
  query_id: string | null;
  severity: Severity;
  title: string;
  body: string;
  channel: string;
  status: NotificationStatus;
  rendered_payload: Record<string, unknown>;
  read: boolean;
  created_at: string;
};

// The map watch-badge payload D3 consumes. Kept deliberately small and stable.
export type WatchBadge = {
  watch_id: string;
  lat: number | null;
  lon: number | null;
  watch_type: WatchType;
  status: "clear" | "active";
  severity: Severity;
  enabled: boolean;
  unread_count: number;
  last_fired_at: string | null;
  updated_at: string | null;
  label: string;
};

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

export async function listWatches(): Promise<Watch[]> {
  const r = await authFetch("/api/watches");
  if (!r.ok) throw new Error(`watches ${r.status}`);
  return r.json();
}

export async function createWatch(body: WatchIn): Promise<Watch> {
  const r = await authFetch("/api/watches", { method: "POST", body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`create watch ${r.status}`);
  return r.json();
}

export async function updateWatch(id: string, body: WatchIn): Promise<Watch> {
  const r = await authFetch(`/api/watches/${id}`, { method: "PUT", body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`update watch ${r.status}`);
  return r.json();
}

export async function deleteWatch(id: string): Promise<void> {
  const r = await authFetch(`/api/watches/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error(`delete watch ${r.status}`);
}

export async function watchHistory(id: string): Promise<OrcaNotification[]> {
  const r = await authFetch(`/api/watches/${id}/history`);
  if (!r.ok) throw new Error(`history ${r.status}`);
  return r.json();
}

// The badge feed for D3's map layer. D3 calls this and renders; nothing here
// touches the map.
export async function watchBadges(): Promise<{ badges: WatchBadge[]; map_layer: unknown }> {
  const r = await authFetch("/api/watches/badges");
  if (!r.ok) throw new Error(`badges ${r.status}`);
  return r.json();
}

export async function listNotifications(unreadOnly = false): Promise<OrcaNotification[]> {
  const r = await authFetch(`/api/notifications?unread_only=${unreadOnly}`);
  if (!r.ok) throw new Error(`notifications ${r.status}`);
  return r.json();
}

export async function unreadCount(): Promise<number> {
  const r = await authFetch("/api/notifications/unread_count");
  if (!r.ok) return 0;
  return (await r.json()).count ?? 0;
}

export async function markRead(id: string): Promise<void> {
  await authFetch(`/api/notifications/${id}/read`, { method: "POST" });
}

export async function markAllRead(): Promise<void> {
  await authFetch("/api/notifications/read_all", { method: "POST" });
}

// SSE — EventSource can't set headers, so the token rides as a query param
// (validated server-side exactly like the bearer header).
export function notificationStream(): EventSource | null {
  const token = getToken();
  if (!token) return null;
  return new EventSource(`${API_BASE}/api/notifications/stream?token=${encodeURIComponent(token)}`);
}

export async function submitFeedback(body: {
  query_id: string;
  kind: "helpful" | "not_accurate" | "report_issue";
  advisory_ref?: string;
  comment?: string;
}): Promise<{ trace_route: string }> {
  const r = await authFetch("/api/feedback", { method: "POST", body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`feedback ${r.status}`);
  return r.json();
}
