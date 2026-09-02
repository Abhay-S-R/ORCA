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
  "/",
  "/safety",
  "/map",
  "/zones",
  "/voyage",
  "/trends",
  "/data",
  "/ops",
  "/watches",
  "/reasoning",
] as const;

type Route = (typeof NAV_ROUTES)[number];

// ✅ primary · ◐ secondary · ✗ hidden (parent plan §4.3 table, verbatim).
// NOTE: The plan annotates some cells as "✅ simplified" (fisherman Map,
// fisherman Watches). "Simplified" is a rendering-complexity note — fewer
// default layers, simpler charts — NOT a separate nav-visibility tier.
// The visibility matrix controls what appears in the NavRail; how complex
// the content renders is a per-surface concern handled inside the page.
const VISIBILITY_MATRIX: Record<Route, Record<Persona, Visibility>> = {
  "/": { fisherman: "primary", commercial_navigator: "primary", researcher: "primary", coastal_authority: "primary", unresolved: "primary" },
  "/safety": { fisherman: "primary", commercial_navigator: "primary", researcher: "secondary", coastal_authority: "primary", unresolved: "primary" },
  "/map": { fisherman: "primary", commercial_navigator: "primary", researcher: "primary", coastal_authority: "primary", unresolved: "primary" },
  "/zones": { fisherman: "primary", commercial_navigator: "primary", researcher: "secondary", coastal_authority: "hidden", unresolved: "primary" },
  "/voyage": { fisherman: "hidden", commercial_navigator: "primary", researcher: "hidden", coastal_authority: "secondary", unresolved: "hidden" },
  "/trends": { fisherman: "hidden", commercial_navigator: "secondary", researcher: "primary", coastal_authority: "primary", unresolved: "hidden" },
  "/data": { fisherman: "hidden", commercial_navigator: "hidden", researcher: "primary", coastal_authority: "secondary", unresolved: "hidden" },
  "/ops": { fisherman: "hidden", commercial_navigator: "hidden", researcher: "hidden", coastal_authority: "primary", unresolved: "hidden" },
  "/watches": { fisherman: "primary", commercial_navigator: "primary", researcher: "secondary", coastal_authority: "primary", unresolved: "primary" },
  "/reasoning": { fisherman: "hidden", commercial_navigator: "secondary", researcher: "primary", coastal_authority: "secondary", unresolved: "hidden" },
};

export function visibilityFor(route: Route, persona: Persona): Visibility {
  return VISIBILITY_MATRIX[route][persona];
}
