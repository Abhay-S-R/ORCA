"use client";

// The loudest object in the product (plan §4.1): "must be legible in direct
// sunlight on a phone at sea; nothing else in the UI may compete with it".
//
// Which is why this is not a pill. It is a slab: a 5px severity rule, the
// verdict word at display size in the safety colour, and an icon. The three
// safety tokens are used here and in hazard severity — nowhere else.
import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, CheckCircle2, OctagonX, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import { type ConfidenceTier, type Verdict } from "./Badge";

const VERDICT: Record<Verdict, { label: string; cls: string; rule: string; Icon: typeof CheckCircle2 }> = {
  GO: { label: "Go", cls: "text-go", rule: "bg-go", Icon: CheckCircle2 },
  CAUTION: { label: "Caution", cls: "text-caution", rule: "bg-caution", Icon: AlertTriangle },
  NO_GO: { label: "No go", cls: "text-no-go", rule: "bg-no-go", Icon: OctagonX },
};

export function VerdictBadge({
  verdict,
  summary,
  confidenceTier,
  children,
}: {
  verdict: Verdict;
  summary?: string;
  // Architecture §2.6: on LOW_DATA, the verdict itself stays true (Ground
  // Rule 3 — the word and colour never change), but the badge grows a
  // distinct amber "data limited" band underneath it. Identical for every
  // persona because this prop is the only thing that turns it on.
  confidenceTier?: ConfidenceTier;
  children?: ReactNode;
}) {
  const { label, cls, rule, Icon } = VERDICT[verdict];
  const reduce = useReducedMotion();
  const lowData = confidenceTier === "LOW_DATA";

  return (
    <div className="flex flex-col gap-0">
      <div
        // role=status so a verdict arriving is announced, not just painted.
        role="status"
        className={`glass relative flex items-stretch gap-4 overflow-hidden shadow-xl border border-hairline ${
          lowData ? "rounded-t-xl" : "rounded-xl"
        }`}
      >
        {/* The severity rule. On NO_GO it breathes — but the word, the colour
            and the icon all already say it, so motion is never load-bearing. */}
        <motion.div
          aria-hidden="true"
          className={`w-2 shrink-0 ${rule} shadow-[0_0_12px_currentColor]`}
          animate={verdict === "NO_GO" && !reduce ? { opacity: [1, 0.4, 1] } : { opacity: 1 }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        />
        <div className="flex flex-1 items-center gap-4 py-5 pr-5">
          <div className={`grid size-14 shrink-0 place-items-center rounded-xl border border-current/30 bg-shelf-2/60 ${cls}`}>
            <Icon className="size-8" strokeWidth={2} aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono tracking-widest text-ink-dim uppercase">
                SAFETY TELEGRAPH
              </span>
            </div>
            <p className={`text-3xl leading-tight font-extrabold tracking-tight sm:text-4xl ${cls}`}>
              {label}
            </p>
            {summary && <p className="mt-1 text-sm font-medium leading-relaxed text-ink-muted">{summary}</p>}
            {children}
          </div>
        </div>
      </div>
      {lowData && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-b-xl border border-t-0 border-data-limited/45 bg-data-limited/15 px-4 py-2.5 text-xs font-semibold text-data-limited"
        >
          <ShieldAlert className="size-4 shrink-0" strokeWidth={2} aria-hidden="true" />
          Data limited — verify locally before deciding
        </div>
      )}
    </div>
  );
}
