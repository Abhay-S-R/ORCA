// Design system primitive (plan §4.1).
//
// Severity is never carried by colour alone — `children` is always a visible
// text token; `tone` only reinforces it. On the dark base a badge is glass
// with a tinted rule, not a light pill: filled light badges were the single
// loudest thing on the old light theme and competed with the verdict.
import type { ReactNode } from "react";

export type BadgeTone = "go" | "caution" | "no-go" | "neutral" | "accent";

const TONE: Record<BadgeTone, string> = {
  go: "text-go border-go/40 bg-go/10",
  caution: "text-caution border-caution/40 bg-caution/10",
  "no-go": "text-no-go border-no-go/45 bg-no-go/10",
  neutral: "text-ink-muted border-hairline bg-shelf-2/60",
  accent: "text-accent border-accent/40 bg-accent/10",
};

export function Badge({
  tone = "neutral",
  children,
  icon,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-[11px] font-semibold tracking-wide ${TONE[tone]}`}
    >
      {icon}
      {children}
    </span>
  );
}

export type Verdict = "GO" | "CAUTION" | "NO_GO";
export type ConfidenceTier = "HIGH" | "MEDIUM" | "LOW_DATA";

export function verdictTone(verdict: Verdict): BadgeTone {
  return verdict === "GO" ? "go" : verdict === "CAUTION" ? "caution" : "no-go";
}

// Confidence is deliberately OUTSIDE the safety triad. A LOW_DATA caveat is
// not a hazard, and rendering it in the danger colour would overstate it
// (Ground Rule 3). It gets its own cool ramp so the eye reads it as metadata.
const CONFIDENCE: Record<ConfidenceTier, string> = {
  HIGH: "text-confidence-high",
  MEDIUM: "text-confidence-medium",
  LOW_DATA: "text-confidence-low",
};

export function confidenceClass(tier: ConfidenceTier): string {
  return CONFIDENCE[tier];
}

export function confidenceLabel(tier: ConfidenceTier): string {
  return tier === "LOW_DATA" ? "Low data" : tier === "MEDIUM" ? "Medium" : "High";
}
