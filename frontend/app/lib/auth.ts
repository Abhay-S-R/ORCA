"use client";

// Minimal bearer-token helper for the D2 surfaces (/watches, notification
// feed, /ops). D1 owns the real identity system; until a shared auth context
// lands, this reads the access token from localStorage["orca.token"] — the
// obvious key D1's /login flow will write — and adds it to fetches.
//
// TODO(D1): replace with the shared auth context / useAuth() hook when it
// exists. This file is the single swap point.

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const TOKEN_KEY = "orca.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
    window.dispatchEvent(new Event("orca:auth"));
  } catch {
    /* private mode / storage disabled — the surface degrades to signed-out */
  }
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

// Dev/demo sign-in — POST /api/login, store the returned access token.
export async function signIn(identifier: string, password: string): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifier, password }),
  });
  if (!res.ok) return false;
  const data = await res.json();
  setToken(data.access_token ?? null);
  return true;
}

export function signOut(): void {
  setToken(null);
}
