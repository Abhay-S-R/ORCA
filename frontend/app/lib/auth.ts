"use client";

// Identity for every surface (D1, plan §5.4) — the one place a token is read,
// stored, refreshed or dropped. /watches, /ops, the notification feed, the
// chart's watch badges and Ask's chat history all go through here.
//
// Tokens: a 15-minute access token and a 30-day refresh token, both in
// localStorage. The access token used to be stored alone, so every signed-in
// surface quietly signed out after 15 minutes; it is now renewed shortly
// before it expires, and on any 401, via POST /api/refresh (which rotates the
// refresh token — see backend orca/auth/service.py).
//
// Every existing export (getToken, setToken, authFetch, signIn, signOut,
// API_BASE) keeps its signature and meaning.

import { useEffect, useState } from "react";
import { API_BASE } from "./apiBase";

export { API_BASE } from "./apiBase";

const TOKEN_KEY = "orca.token";
const REFRESH_KEY = "orca.refresh";
const AUTH_EVENT = "orca:auth";

export type Profile = {
  id: string;
  identifier: string | null;
  display_name: string | null;
  role: "user" | "authority" | "admin";
  default_persona: string;
  language: string;
  home_port: { lat: number; lon: number } | null;
  home_port_name: string | null;
  active_vessel_id: string | null;
  quiet_hours: { start: string; end: string; tz: string } | null;
  typical_departure_hour: number | null;
};

type TokenPair = { access_token: string; refresh_token: string };

function read(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return read(TOKEN_KEY);
}

function announce() {
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem(REFRESH_KEY);
    }
    announce();
  } catch {
    /* private mode / storage disabled — the surface degrades to signed-out */
  }
}

function storePair(pair: TokenPair) {
  try {
    window.localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  } catch {
    /* setToken below reports the same storage failure path */
  }
  setToken(pair.access_token);
}

// Seconds until the access token expires, from its own `exp` claim. Read only
// to decide *when* to refresh — never trusted for anything the server checks.
function secondsLeft(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.exp - Date.now() / 1000;
  } catch {
    return 0;
  }
}

let refreshing: Promise<boolean> | null = null;

// Single-flight within a tab. Across tabs, two refreshes can still race with
// the same token; the backend refuses the loser without revoking anything
// (a 30-second grace), and the loser then finds the winner's new tokens
// already in shared localStorage — so it counts as success, not sign-out.
export function refreshSession(): Promise<boolean> {
  // Cleared via .finally() on the stored promise, not a finally inside the
  // async body: with no refresh token the body returns synchronously, and an
  // inner finally would run before this assignment — pinning a resolved
  // `false` here for the life of the tab.
  refreshing ??= doRefresh().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

async function doRefresh(): Promise<boolean> {
  const presented = read(REFRESH_KEY);
  if (!presented) return false;
  try {
    const res = await fetch(`${API_BASE}/api/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: presented }),
    });
    if (res.ok) {
      storePair(await res.json());
      return true;
    }
    const current = read(REFRESH_KEY);
    if (current && current !== presented) return true;
    if (res.status === 401 || res.status === 403) setToken(null);
    return false;
  } catch {
    // Backend unreachable: keep the tokens, the next attempt may work.
    return false;
  }
}

// The access token as a URL parameter, for an EventSource — which cannot send
// an Authorization header. Refreshed first on the same rule authFetch uses, so
// a nearly-expired token does not turn a signed-in question anonymous.
// Returns "" when signed out, so callers can append it unconditionally.
export async function tokenParam(): Promise<string> {
  const token = getToken();
  if (token && read(REFRESH_KEY) && secondsLeft(token) < 30) await refreshSession();
  const current = getToken();
  return current ? `&access_token=${encodeURIComponent(current)}` : "";
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  if (token && read(REFRESH_KEY) && secondsLeft(token) < 30) await refreshSession();

  const send = () => {
    const headers = new Headers(init.headers);
    const current = getToken();
    if (current) headers.set("Authorization", `Bearer ${current}`);
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    return fetch(`${API_BASE}${path}`, { ...init, headers });
  };

  const res = await send();
  if (res.status === 401 && read(REFRESH_KEY) && (await refreshSession())) return send();
  return res;
}

export type AuthResult = { ok: true } | { ok: false; error: string };

async function authenticate(path: "/api/login" | "/api/register", body: object): Promise<AuthResult> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, error: "Can't reach Sagar Sarathi right now. Check your connection and try again." };
  }
  if (res.ok) {
    storePair(await res.json());
    return { ok: true };
  }
  if (res.status === 409) return { ok: false, error: "An account with this phone or email already exists. Sign in instead." };
  if (res.status === 403) return { ok: false, error: "This account is not active." };
  if (res.status === 422 && path === "/api/register") {
    const detail = await res.json().catch(() => null);
    const message: string | undefined = detail?.detail?.[0]?.msg;
    return { ok: false, error: message?.replace(/^Value error, /, "") ?? "Check the details and try again." };
  }
  return { ok: false, error: "Wrong phone/email or password." };
}

export function signInWithPassword(identifier: string, password: string): Promise<AuthResult> {
  return authenticate("/api/login", { identifier, password });
}

export function register(identifier: string, password: string, displayName: string): Promise<AuthResult> {
  // P3.13 — a signed-out language choice (../language/context.tsx's
  // localStorage) becomes the new account's `users.language`, so a visitor
  // who already picked Tamil before signing up doesn't have to pick it
  // again from English defaults.
  const language = read("orca.language") ?? undefined;
  return authenticate("/api/register", {
    identifier,
    password,
    display_name: displayName.trim() || null,
    ...(language ? { language } : {}),
  });
}

// Kept for /watches' inline sign-in, which only needs pass/fail.
export async function signIn(identifier: string, password: string): Promise<boolean> {
  return (await signInWithPassword(identifier, password)).ok;
}

export function signOut(): void {
  const refresh = read(REFRESH_KEY);
  if (refresh) {
    // Revoke server-side too, so a copied refresh token dies with the session.
    // Fire-and-forget: signing out locally must never wait on the network.
    fetch(`${API_BASE}/api/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      keepalive: true,
    }).catch(() => {});
  }
  setToken(null);
}

// ---------------------------------------------------------------------------
// useAuth — shared signed-in state for components.

let profileFor: { token: string; promise: Promise<Profile | null> } | null = null;

// P3.4/P3.13 bug found: loadProfile() below caches its result per-token, so
// a profile *mutation* (PUT /api/profile/persona, /language, ...) with no
// token change left every useAuth() consumer reading the stale value —
// the onboarding wizard's own gate (AppChrome) re-read "unresolved" right
// after setting "fisherman" and bounced straight back to /onboarding. Any
// code that PUTs to /api/profile/* must call this afterwards.
export function invalidateProfile(): void {
  profileFor = null;
  announce();
}

function loadProfile(): Promise<Profile | null> {
  const token = getToken();
  if (!token) return Promise.resolve(null);
  if (profileFor?.token !== token) {
    // Keyed on the token, so the many components that call useAuth share one
    // request — but a rotated token for the same user refetches only once.
    profileFor = {
      token,
      promise: authFetch("/api/profile")
        .then((r) => {
          // Still 401 after authFetch's own refresh attempt: the session is
          // over (e.g. a token stored before refresh tokens existed, or a
          // revoked one). Say so, instead of looking signed in while every
          // request fails. Only for that same token — a sign-in that
          // happened meanwhile is left alone.
          if (r.status === 401 && getToken() === token) setToken(null);
          return r.ok ? (r.json() as Promise<Profile>) : null;
        })
        .catch(() => null),
    };
  }
  return profileFor.promise;
}

let refreshTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleRefresh() {
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = null;
  const token = getToken();
  if (!token || !read(REFRESH_KEY)) return;
  const delayMs = Math.max(0, (secondsLeft(token) - 60) * 1000);
  refreshTimer = setTimeout(() => void refreshSession(), delayMs);
}

export type AuthState =
  | { status: "loading"; profile: null }
  | { status: "signed_out"; profile: null }
  | { status: "signed_in"; profile: Profile | null };

export function useAuth(): AuthState {
  // "loading" on the server pass and first client render — the same
  // hydration-safe pattern persona/context.tsx uses for its storage read.
  const [state, setState] = useState<AuthState>({ status: "loading", profile: null });

  useEffect(() => {
    let cancelled = false;
    const sync = () => {
      const token = getToken();
      if (!token) {
        setState({ status: "signed_out", profile: null });
        return;
      }
      scheduleRefresh();
      setState((prev) => ({ status: "signed_in", profile: prev.status === "signed_in" ? prev.profile : null }));
      void loadProfile().then((profile) => {
        if (!cancelled && getToken()) setState({ status: "signed_in", profile });
      });
    };
    // Another tab signing in, out, or rotating tokens.
    const onStorage = (e: StorageEvent) => {
      if (e.key === TOKEN_KEY || e.key === null) announce();
    };
    sync();
    window.addEventListener(AUTH_EVENT, sync);
    window.addEventListener("storage", onStorage);
    return () => {
      cancelled = true;
      window.removeEventListener(AUTH_EVENT, sync);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return state;
}

export function displayNameOf(profile: Profile | null): string {
  return profile?.display_name || profile?.identifier || "Signed in";
}

// Save the user's home port after registration (or profile update).
// Calls PUT /api/profile/home-port, then invalidates the cached profile so
// every useAuth() consumer sees the new port immediately.
export async function setHomePort(lat: number, lon: number, name?: string): Promise<boolean> {
  try {
    const res = await authFetch("/api/profile/home-port", {
      method: "PUT",
      body: JSON.stringify({ lat, lon, ...(name ? { name } : {}) }),
    });
    if (res.ok) {
      invalidateProfile();
      return true;
    }
    return false;
  } catch {
    return false;
  }
}
