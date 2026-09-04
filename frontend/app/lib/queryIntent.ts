// Cheap client-side classification of a query's spatial intent, so the Ask
// page's chart can react (which layer to emphasise, where to look) without
// waiting on a backend field that doesn't exist — Agent 9 returns facts, not
// a map-focus hint. Keyword matching only: good enough to pick an emphasis,
// not a routing decision anything depends on for correctness.
export type QueryIntent = "fishing" | "boundary" | "safety" | "general";

const FISHING = /\bfish(ing)?\b|\bpfz\b|\btrawl|\bcatch\b|landing centre|landing center/i;
const BOUNDARY = /\bboundary\b|\bimbl\b|\bborder\b|\beez\b|international maritime/i;
const SAFETY = /\bsafe\b|\bsafety\b|go out|\bcaution\b|\bstorm\b|\bcyclone\b|\bwave/i;

export function classifyQueryIntent(query: string): QueryIntent {
  if (FISHING.test(query)) return "fishing";
  if (BOUNDARY.test(query)) return "boundary";
  if (SAFETY.test(query)) return "safety";
  return "general";
}

export const INTENT_LABEL: Record<QueryIntent, string> = {
  fishing: "fishing zones near your position",
  boundary: "the maritime boundary standoff",
  safety: "local sea conditions",
  general: "the pilot sector",
};
