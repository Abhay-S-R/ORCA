// Persona visibility matrix (parent plan §4.3), as declarative config — not
// scattered conditionals, so Phase 3 adds surfaces to this table instead of
// hunting down every `if (persona === ...)` in the nav.
//
// IMPORTANT (parent plan §4.3): nav visibility is a rendering concern only,
// never a capability gate. A "hidden" route still renders at its URL — this
// config controls what NavRail shows, nothing else. Never use it to guard
// data fetching or agent execution.
export type Persona = "fisherman" | "commercial_navigator" | "researcher" | "coastal_authority" | "unresolved";

export type Visibility = "primary" | "secondary" | "hidden";

export const PERSONAS: { id: Persona; label: string }[] = [
  { id: "fisherman", label: "Fisherman" },
  { id: "commercial_navigator", label: "Commercial Navigator" },
  { id: "researcher", label: "Researcher" },
  { id: "coastal_authority", label: "Coastal Authority" },
  { id: "unresolved", label: "Unresolved" },
];

export const NAV_ROUTES = [
  "/ask",
  "/alerts",
  "/map",
  "/zones",
  "/voyage",
  "/trends",
  "/data",
  "/ops",
  "/watches",
  "/reasoning",
] as const;

export type Route = (typeof NAV_ROUTES)[number];

// P4.4 (`R-JUDGE-5`) — the local-storage key both `PersonaProvider` and the
// login page's post-sign-in redirect read, so "which persona is this device"
// has exactly one source rather than two copies of the same string.
export const PERSONA_STORAGE_KEY = "orca.persona";

// P4.4 — "opens on ___". Only navigator and authority differ from the
// product's own default landing surface (`/ask`, primary for everyone);
// fisherman and researcher have no reason to leave it.
export const PERSONA_DEFAULT_ROUTE: Record<Persona, Route> = {
  fisherman: "/ask",
  commercial_navigator: "/voyage",
  researcher: "/ask",
  coastal_authority: "/ops",
  unresolved: "/ask",
};

// P4.4 — "per-persona map defaults... come from one extension of the
// existing config table, not scattered conditionals." Same shape as
// `MapView`'s own `initialLayers` prop (kept in sync there, not imported,
// since that type is inline to the component and this table is the one
// place outside it that needs to agree with it).
type MapLayerDefaults = Partial<{
  boundaries: boolean;
  boundaryLines: boolean;
  pfz: boolean;
  seamarks: boolean;
  srvBathymetry: boolean;
  waveForecast: boolean;
  currents: boolean;
  wind: boolean;
  watchBadges: boolean;
  cyclone: boolean;
}>;

export const PERSONA_MAP_PROFILE: Record<Persona, { showLayerPanel: boolean; initialLayers: MapLayerDefaults }> = {
  // Fisherman gets simplified defaults (PFZ + cyclone, no boundaries/wind)
  // but the panel itself stays visible on /map — the "no layer console"
  // rule in the plan applies only to the ask-page mini-map, which already
  // passes showLayerPanel={false} directly. Hiding it here as well makes
  // the "Chart layers" button disappear from the full /map page entirely.
  fisherman: { showLayerPanel: true, initialLayers: { pfz: true, seamarks: false, wind: false, cyclone: true, watchBadges: true } },
  commercial_navigator: { showLayerPanel: true, initialLayers: { boundaries: true, boundaryLines: true, pfz: true, seamarks: true, wind: true, cyclone: true, watchBadges: true } },
  // "Multi-layer map by default" — every layer that costs nothing extra to
  // show turned on, including the two heavy ones (bathymetry, currents) the
  // other personas leave off by default.
  researcher: { showLayerPanel: true, initialLayers: { boundaries: true, boundaryLines: true, pfz: true, seamarks: true, srvBathymetry: true, currents: true, wind: true, cyclone: true, watchBadges: true } },
  coastal_authority: { showLayerPanel: true, initialLayers: { boundaries: true, boundaryLines: true, pfz: true, seamarks: true, wind: true, cyclone: true, watchBadges: true } },
  unresolved: { showLayerPanel: true, initialLayers: {} },
};

// ✅ primary · ◐ secondary · ✗ hidden (parent plan §4.3 table, verbatim).
// NOTE: The plan annotates some cells as "✅ simplified" (fisherman Map,
// fisherman Watches). "Simplified" is a rendering-complexity note — fewer
// default layers, simpler charts — NOT a separate nav-visibility tier.
// The visibility matrix controls what appears in the NavRail; how complex
// the content renders is a per-surface concern handled inside the page.
const VISIBILITY_MATRIX: Record<Route, Record<Persona, Visibility>> = {
  // "/" itself is now the public landing page (outside the nav rail
  // entirely) — the Ask surface this row describes moved to "/ask", the
  // matrix values are unchanged from the plan.
  "/ask": { fisherman: "primary", commercial_navigator: "primary", researcher: "primary", coastal_authority: "primary", unresolved: "primary" },
  // P4.11 — takes `/safety`'s old slot in the nav (P4.1's collapse), same
  // per-persona visibility it had.
  // Alerts are accessible via the persistent bell icon (bottom-left) — the
  // nav rail entry is intentionally removed so the bell is the single entry point.
  "/alerts": { fisherman: "hidden", commercial_navigator: "hidden", researcher: "hidden", coastal_authority: "hidden", unresolved: "hidden" },
  "/map": { fisherman: "primary", commercial_navigator: "primary", researcher: "primary", coastal_authority: "primary", unresolved: "primary" },
  "/zones": { fisherman: "primary", commercial_navigator: "primary", researcher: "secondary", coastal_authority: "hidden", unresolved: "primary" },
  "/voyage": { fisherman: "primary", commercial_navigator: "primary", researcher: "secondary", coastal_authority: "primary", unresolved: "primary" },
  "/trends": { fisherman: "hidden", commercial_navigator: "secondary", researcher: "primary", coastal_authority: "primary", unresolved: "hidden" },
  "/data": { fisherman: "hidden", commercial_navigator: "hidden", researcher: "primary", coastal_authority: "secondary", unresolved: "hidden" },
  "/ops": { fisherman: "hidden", commercial_navigator: "hidden", researcher: "hidden", coastal_authority: "primary", unresolved: "hidden" },
  "/watches": { fisherman: "primary", commercial_navigator: "primary", researcher: "secondary", coastal_authority: "primary", unresolved: "primary" },
  "/reasoning": { fisherman: "secondary", commercial_navigator: "secondary", researcher: "primary", coastal_authority: "secondary", unresolved: "primary" },
};

export function visibilityFor(route: Route, persona: Persona): Visibility {
  return VISIBILITY_MATRIX[route][persona];
}
