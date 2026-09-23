"use client";

// P4.9 (R-UX-5) — "each step runs a real query and shows the real answer."
// This card never freezes the screen or spotlights a fake element; it sits
// beside the real thread and narrates what is actually happening. The
// orchestration (running queries, tracking the query_id) lives in
// ask/page.tsx, which is the one place that already holds the thread state
// all five steps need.
import { motion } from "framer-motion";
import { Volume2, Workflow, X } from "lucide-react";
import Link from "next/link";
import { type Persona } from "../persona/config";

export const TOUR_PRESET: Record<Persona, string> = {
  fisherman: "Is it safe to go out tomorrow morning?",
  commercial_navigator: "Is the passage from Thoothukudi to Chennai safe this week?",
  researcher: "What are the current SST and chlorophyll trends off the Kerala coast?",
  coastal_authority: "What is the risk level across all sectors today?",
  unresolved: "Is it safe to go out tomorrow morning?",
};

// A real follow-up in Tamil — the backend's own language detection (Phase 3)
// routes and answers it; nothing here translates it client-side.
export const TOUR_FOLLOWUP = "நாளை மாலை எப்படி இருக்கும்?"; // "What about tomorrow evening?"

export const TOUR_NEXT_STEP: Record<Persona, { label: string; href: string }> = {
  fisherman: { label: "Watch your home port", href: "/watches" },
  commercial_navigator: { label: "Plan a voyage", href: "/voyage" },
  researcher: { label: "Export the data", href: "/data" },
  coastal_authority: { label: "Open district ops", href: "/ops" },
  unresolved: { label: "Watch a location", href: "/watches" },
};

const STEP_COPY: Record<1 | 2 | 3 | 4 | 5, { title: string; body: string }> = {
  1: { title: "Step 1 of 5 — Ask your first question", body: "This is the question most people ask ORCA first. Run it and watch a real verdict arrive." },
  2: { title: "Step 2 of 5 — Watch the agents work", body: "Each one streams in below as it finishes — this is the actual pipeline running, not a recording." },
  3: { title: "Step 3 of 5 — Open a citation", body: "Every number on the answer card names its source. Tap a source chip above to see its dataset, timestamp and freshness." },
  4: { title: "Step 4 of 5 — Ask a follow-up, in another language", body: "ORCA answers in whatever language you ask in. This follow-up is in Tamil." },
  5: { title: "Step 5 of 5 — Why, and what's next", body: "See the full reasoning trace behind that answer, then move on to what you'd actually do next." },
};

export function TourCard({
  step,
  persona,
  waiting,
  queryId,
  onRunPreset,
  onNext,
  onRunFollowUp,
  onFinish,
  onSkip,
}: {
  step: 1 | 2 | 3 | 4 | 5;
  persona: Persona;
  waiting: boolean;
  queryId: string | null;
  onRunPreset: () => void;
  onNext: () => void;
  onRunFollowUp: () => void;
  onFinish: () => void;
  onSkip: () => void;
}) {
  const copy = STEP_COPY[step];
  const nextStep = TOUR_NEXT_STEP[persona];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 16 }}
      role="dialog"
      aria-label="ORCA tour"
      className="glass fixed bottom-4 right-4 z-40 w-[min(22rem,calc(100vw-2rem))] rounded-2xl border border-hairline-strong/80 p-4 shadow-2xl"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-[10px] font-bold tracking-widest text-ocean-cyan uppercase">{copy.title}</span>
        <button type="button" onClick={onSkip} aria-label="Skip tour" className="text-ink-dim hover:text-ink">
          <X className="size-3.5" />
        </button>
      </div>

      <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{copy.body}</p>

      <div className="mt-3 flex flex-col gap-2">
        {step === 1 && (
          <>
            <p className="rounded-lg border border-hairline/70 bg-shelf-2/50 px-2.5 py-2 text-xs italic text-ink">
              &ldquo;{TOUR_PRESET[persona]}&rdquo;
            </p>
            <button type="button" onClick={onRunPreset} disabled={waiting} className={PRIMARY_BTN}>
              {waiting ? "Asking…" : "Run it"}
            </button>
          </>
        )}

        {step === 2 && (
          <div className="flex items-center gap-2 text-xs text-ink-dim">
            <span className="size-2 rounded-full bg-ocean-cyan beacon-pulse" aria-hidden="true" />
            {waiting ? "Streaming…" : "Answer received."}
          </div>
        )}

        {step === 3 && (
          <button type="button" onClick={onNext} className={PRIMARY_BTN}>
            Next
          </button>
        )}

        {step === 4 && (
          <>
            <p className="flex items-center gap-1.5 rounded-lg border border-hairline/70 bg-shelf-2/50 px-2.5 py-2 text-xs italic text-ink">
              <Volume2 className="size-3 shrink-0 text-ocean-cyan" aria-hidden="true" />
              &ldquo;{TOUR_FOLLOWUP}&rdquo;
            </p>
            <button type="button" onClick={onRunFollowUp} disabled={waiting} className={PRIMARY_BTN}>
              {waiting ? "Asking…" : "Ask it"}
            </button>
          </>
        )}

        {step === 5 && (
          <>
            {queryId && (
              <Link
                href={`/reasoning?query_id=${queryId}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-hairline/70 bg-shelf-2/50 px-2.5 py-2 text-xs font-medium text-ink hover:border-ocean-cyan/50"
              >
                <Workflow className="size-3.5 text-ocean-cyan" aria-hidden="true" />
                See the reasoning trace
              </Link>
            )}
            <Link
              href={nextStep.href}
              onClick={onFinish}
              className={PRIMARY_BTN}
            >
              {nextStep.label}
            </Link>
            <button type="button" onClick={onFinish} className="self-center text-[11px] text-ink-dim hover:text-ink hover:underline">
              Finish tour
            </button>
          </>
        )}

        {step !== 5 && (
          <button type="button" onClick={onSkip} className="self-center text-[11px] text-ink-dim hover:text-ink hover:underline">
            Skip tour
          </button>
        )}
      </div>
    </motion.div>
  );
}

const PRIMARY_BTN =
  "inline-flex items-center justify-center gap-1.5 rounded-lg border border-ocean-cyan/50 bg-ocean-cyan px-3 py-2 text-xs font-semibold text-on-accent shadow-sm transition-all hover:bg-ocean-cyan/90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50";
