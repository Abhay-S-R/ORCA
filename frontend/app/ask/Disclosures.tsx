"use client";

// Phase 1's two new answer shapes (P1.2 render, P1.3 render).
//
// `DisclosureBanner` is the sentence that has to be read BEFORE the answer —
// this was computed at a position you did not choose, in a sector that is a
// fallback, off a reading past its staleness ceiling. Putting it under the
// verdict would make it a footnote, and a footnote is how a fallback becomes
// a lie (plan principle 3). So it renders above the answer card, always.
//
// `RefusalCard` is the whole response when ORCA declines: an out-of-scope
// question, a question it cannot place, or one about a time or a position it
// holds nothing for. It carries no verdict badge, no gauges and no numbers,
// deliberately — the point of a first-class refusal is that there is nothing
// on screen to mistake for an answer.
import type React from "react";
import { AlertTriangle, Eraser, HelpCircle, MapPin } from "lucide-react";
import { Panel } from "../components/Panel";
import type { FinalResponse } from "./useAskThread";

export function DisclosureBanner({ disclosures }: { disclosures?: string[] }) {
  if (!disclosures?.length) return null;
  return (
    <div role="note" className="flex flex-col gap-1.5 rounded-xl border border-caution/35 bg-caution/5 p-3">
      {disclosures.map((text, i) => (
        <p key={i} className="flex items-start gap-2 text-[12px] leading-snug text-ink-muted">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-caution" aria-hidden="true" />
          <span className="min-w-0">{text}</span>
        </p>
      ))}
    </div>
  );
}

const HEADING: Record<string, string> = {
  OUT_OF_SCOPE: "Not something ORCA can answer",
  NEEDS_PLACE: "Which place do you mean?",
  OUT_OF_RANGE: "Outside what ORCA holds",
};

export function RefusalCard({
  answer,
  onFollowUp,
  actions,
}: {
  answer: FinalResponse;
  onFollowUp: (q: string) => void;
  // Sits on the heading row rather than in Panel's own header slot, which
  // only renders when the panel has a title — and this card's heading carries
  // an icon that the plain title would drop.
  actions?: React.ReactNode;
}) {
  const outcome = answer.outcome ?? "ANSWERED";
  const candidates = answer.place_resolution?.candidates ?? [];
  const body = answer.final_vernacular_response || answer.final_english_response;
  const Icon = outcome === "NEEDS_PLACE" ? MapPin : HelpCircle;

  return (
    <Panel>
      <div className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-ink">
            <Icon className="size-4 shrink-0 text-caution" aria-hidden="true" />
            {HEADING[outcome] ?? "ORCA did not answer this"}
          </p>
          {actions}
        </div>
        <p className="max-w-[60ch] text-sm leading-relaxed text-ink-muted">{body}</p>

        {/* The redirect. A refusal that dead-ends is just a wall — each chip
            re-asks the question at a place ORCA can actually answer for. */}
        {candidates.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline/50 pt-3">
            <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
              Ask about
            </span>
            {candidates.map((c) => (
              <button
                key={`${c.lat},${c.lon}`}
                type="button"
                onClick={() => onFollowUp(`Conditions at ${c.name}`)}
                className="rounded-lg border border-hairline/60 bg-shelf-2/50 px-2.5 py-1.5 text-[11px] capitalize text-ink-muted transition-colors hover:border-ocean-cyan/60 hover:bg-shelf-2 hover:text-ink"
              >
                {c.name}
              </button>
            ))}
          </div>
        )}

        {outcome === "OUT_OF_SCOPE" && (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline/50 pt-3">
            <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
              Try
            </span>
            {["Is it safe to go to sea tomorrow off Thoothukudi?", "Where is the nearest fishing zone?"].map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onFollowUp(q)}
                className="rounded-lg border border-hairline/60 bg-shelf-2/50 px-2.5 py-1.5 text-[11px] text-ink-muted transition-colors hover:border-ocean-cyan/60 hover:bg-shelf-2 hover:text-ink"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

// P2.14 — "forget that, start fresh". Not an answer and not a refusal: the
// conversation was cleared and this is the one-line confirmation. Deliberately
// quiet — no verdict, no gauges, no follow-up chips that would re-ask the
// question the user just told ORCA to drop.
export function ResetNotice({ answer }: { answer: FinalResponse }) {
  const body = answer.final_vernacular_response || answer.final_english_response;
  return (
    <p
      role="status"
      className="flex items-start gap-2 self-start rounded-xl border border-hairline/60 bg-shelf-2/50 px-3 py-2 text-[12px] leading-snug text-ink-muted"
    >
      <Eraser className="mt-0.5 size-3.5 shrink-0 text-accent" aria-hidden="true" />
      <span className="min-w-0">{body}</span>
    </p>
  );
}
