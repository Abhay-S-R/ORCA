// Cheap client-side classification of a query's spatial intent, so the Ask
// page's chart can react (which layer to emphasise, where to look) without
// waiting on a backend field that doesn't exist — Agent 9 returns facts, not
// a map-focus hint. Keyword matching only: good enough to pick an emphasis,
// not a routing decision anything depends on for correctness.
export type QueryIntent = "fishing" | "boundary" | "safety" | "current" | "wave" | "general";

const FISHING = /\bfish(ing)?\b|\bpfz\b|\btrawl|\bcatch\b|landing centre|landing center|\bsst\b|sea surface temp|\btemperature\b|thermal front|chlorophyll/i;
const BOUNDARY = /\bboundary\b|\bimbl\b|\bborder\b|\beez\b|international maritime/i;
const CURRENT = /\bcurrents?\b|\bdrift\b|\bset and drift\b/i;
const WAVE = /\bwaves?\b|\bswell\b|\bwave height\b/i;
const SAFETY = /\bsafe\b|\bsafety\b|go out|\bcaution\b|\bstorm\b|\bcyclone\b/i;

export function classifyQueryIntent(query: string): QueryIntent {
  if (FISHING.test(query)) return "fishing";
  if (BOUNDARY.test(query)) return "boundary";
  if (CURRENT.test(query)) return "current";
  if (WAVE.test(query)) return "wave";
  if (SAFETY.test(query)) return "safety";
  return "general";
}

export const INTENT_LABEL: Record<QueryIntent, string> = {
  fishing: "fishing zones near your position",
  boundary: "the maritime boundary standoff",
  safety: "local sea conditions",
  current: "surface current speed and direction",
  wave: "wave height and swell",
  general: "your area",
};

// A place named in the query (plan item 8: "location-specific query"),
// matched against the chart's own coastal-sector vocabulary so a mentioned
// region can move the camera there directly. Kept as plain keyword lookup —
// good enough to catch "near Chennai" or "off the Kerala coast", not a full
// geocoder.
const REGION_KEYWORDS: { id: string; pattern: RegExp }[] = [
  { id: "gulf_mannar", pattern: /thoothukudi|tuticorin|gulf of mannar/i },
  { id: "gujarat", pattern: /gujarat|kutch|saurashtra/i },
  { id: "mumbai", pattern: /mumbai|bombay|konkan/i },
  { id: "goa", pattern: /\bgoa\b|karwar/i },
  { id: "kochi", pattern: /kochi|cochin|malabar|kerala/i },
  { id: "lakshadweep", pattern: /lakshadweep/i },
  { id: "chennai", pattern: /chennai|madras|coromandel|tamil nadu/i },
  { id: "vizag", pattern: /visakhapatnam|vizag|andhra pradesh/i },
  { id: "kolkata", pattern: /odisha|sundarbans|kolkata|west bengal/i },
  { id: "andaman", pattern: /andaman|nicobar/i },
];

export function matchRegionInQuery(query: string): string | undefined {
  return REGION_KEYWORDS.find((r) => r.pattern.test(query))?.id;
}
