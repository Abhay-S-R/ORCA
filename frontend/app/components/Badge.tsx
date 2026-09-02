// Design system primitive (plan §3.2). Severity is never carried by colour
// alone — `children` is always the visible text token (GO/CAUTION/DANGER,
// or a confidence tier); `tone` only reinforces it with colour.
export type BadgeTone = "go" | "caution" | "danger" | "neutral";

const TONE_CLASSES: Record<BadgeTone, string> = {
  go: "bg-safety-go-bg text-safety-go-text",
  caution: "bg-safety-caution-bg text-safety-caution-text",
  danger: "bg-safety-danger-bg text-safety-danger-text",
  neutral: "bg-black/5 text-current",
};

export function Badge({ tone, children }: { tone: BadgeTone; children: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}

// Verdict and confidence tiers share the same tone mapping across every
// surface that renders either (plan §3.2 — one dialect, not six).
export function verdictTone(verdict: "GO" | "CAUTION" | "NO_GO"): BadgeTone {
  return verdict === "GO" ? "go" : verdict === "CAUTION" ? "caution" : "danger";
}

export function confidenceTone(tier: "HIGH" | "MEDIUM" | "LOW_DATA"): BadgeTone {
  // LOW_DATA renders amber, never red (plan §4 S2 — "verify the LOW-DATA
  // amber path renders for every persona"). It's a caveat on the verdict,
  // not itself a danger signal.
  return tier === "HIGH" ? "go" : "caution";
}
