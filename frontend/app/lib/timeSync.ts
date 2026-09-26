// Time-slider honesty (P4.15, orca_final §10). A snapshot layer (one valid
// time, its own step) is drawn normally only while the slider sits within
// half of that layer's step of its valid time; otherwise it greys out and the
// legend says when it was really sampled. Nothing is ever extrapolated.

export type LayerTiming = { validTime: string; stepHours: number };

export function inSync(sliderIso: string, timing: LayerTiming | null): boolean {
  if (!timing) return false; // a layer with no valid time can't claim to match any hour
  const gapHours = Math.abs(Date.parse(sliderIso) - Date.parse(timing.validTime)) / 3_600_000;
  return Number.isFinite(gapHours) && gapHours <= timing.stepHours / 2;
}

export function syncNote(name: string, sliderIso: string, timing: LayerTiming | null): string {
  if (!timing) return `${name}: valid time unknown — greyed, not extrapolated`;
  const sampled = formatIst(timing.validTime);
  return inSync(sliderIso, timing)
    ? `${name}: sampled ${sampled} (${timing.stepHours} h step)`
    : `${name}: sampled ${sampled}, slider at ${formatIst(sliderIso)} — greyed, not extrapolated`;
}

function formatIst(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toLocaleString("en-IN", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" })} IST`;
}
