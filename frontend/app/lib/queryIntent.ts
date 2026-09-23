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

// P3.12 — these used to be the literal label text; now they're the i18n keys
// that hold it (`i18n/*.json`), so `intentLabel` below takes the same `t()`
// every other piece of UI chrome does instead of returning fixed English.
export const INTENT_LABEL_KEY: Record<QueryIntent, string> = {
  fishing: "intentLabel.fishing",
  boundary: "intentLabel.boundary",
  safety: "intentLabel.safety",
  current: "intentLabel.current",
  wave: "intentLabel.wave",
  general: "intentLabel.general",
};

// Two of those labels claim the map is showing the reader's own surroundings.
// That is only true when the answer resolved to a position — at the pilot
// default it is the same misattribution Agent 9 is forbidden from making in
// the sentence directly below it on the page.
const AT_DEFAULT_LABEL_KEY: Partial<Record<QueryIntent, string>> = {
  fishing: "intentLabel.fishingAtDefault",
  general: "intentLabel.generalAtDefault",
};

export function intentLabel(t: (key: string) => string, intent: QueryIntent, atRegionalDefault: boolean): string {
  const key = (atRegionalDefault && AT_DEFAULT_LABEL_KEY[intent]) || INTENT_LABEL_KEY[intent];
  return t(key);
}

// A place named in the query (plan item 8: "location-specific query"),
// matched against the chart's own coastal-sector vocabulary so a mentioned
// region can move the camera there directly. Kept as plain keyword lookup —
// good enough to catch "near Chennai" or "off the Kerala coast", not a full
// geocoder.
// Each alias below is a port or town that genuinely sits inside that
// sector's own frame (roughly within 150 km of its centre), so naming it puts
// the chart somewhere the reader would recognise. Places with no sector close
// enough are deliberately absent — a wrong "near enough" region is worse than
// falling back to the reader's own position.
const REGION_KEYWORDS: { id: string; pattern: RegExp }[] = [
  { id: "gulf_mannar", pattern: /thoothukudi|tuticorin|gulf of mannar|rameswaram|rameshwaram|pamban|mandapam|kanyakumari|kanniyakumari/i },
  { id: "gujarat", pattern: /gujarat|kutch|saurashtra|porbandar|veraval|dwarka|okha|jamnagar|kandla|mundra/i },
  { id: "mumbai", pattern: /mumbai|bombay|konkan|alibag|uran|jnpt|vasai|thane/i },
  { id: "goa", pattern: /\bgoa\b|karwar|panaji|panjim|vasco|mormugao|malvan/i },
  { id: "kochi", pattern: /kochi|cochin|malabar|kerala|alappuzha|alleppey|kollam|kozhikode|calicut|munambam|beypore/i },
  { id: "lakshadweep", pattern: /lakshadweep|kavaratti|minicoy/i },
  { id: "chennai", pattern: /chennai|madras|coromandel|tamil nadu|ennore|mahabalipuram|mamallapuram|puducherry|pondicherry/i },
  { id: "vizag", pattern: /visakhapatnam|vizag|andhra pradesh|kakinada|bheemunipatnam|bhimunipatnam|srikakulam/i },
  { id: "kolkata", pattern: /odisha|sundarbans|kolkata|west bengal|paradip|paradeep|digha|haldia/i },
  { id: "andaman", pattern: /andaman|nicobar|port blair/i },
];

export function matchRegionInQuery(query: string): string | undefined {
  return REGION_KEYWORDS.find((r) => r.pattern.test(query))?.id;
}
