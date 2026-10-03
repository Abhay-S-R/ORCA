// Stale-data policy (docs/data/ORCA_Stale_Data_Policy.md): the shared shape and
// label for "how old is this" across every page that shows a dated item —
// `/zones` (PFZ advisories) and `/trends` (SST/chlorophyll granules) so far.
export type Recency = {
  age_days: number | null;
  band: "fresh" | "hint" | "history" | null;
  expired: boolean | null;
};

// "issued 19 Sep · 5 days old" — null while the item is within its fresh
// band, since a plainly-current item needs no age caveat at all.
export function ageLabel(validFor: string | null | undefined, r: Recency): string | null {
  if (!validFor || r.band === "fresh" || r.age_days == null) return null;
  return `issued ${validFor} · ${r.age_days} day${r.age_days === 1 ? "" : "s"} old`;
}
