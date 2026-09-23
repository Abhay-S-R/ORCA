"use client";

// "Try again" on an answer card, plus the switcher for the runs it replaced.
//
// Re-running is not free here the way it is in a plain chat product: it puts
// ten agents back through real datasets. So the control is quiet — a ghost
// icon in the card's top-right corner, not a button competing with the
// answer — and it says what it does on hover, because "regenerate" would not
// tell a fisherman that the boundary distance is about to be recomputed.
//
// The answer it replaces is never thrown away; the "2/2" stepper beside it
// walks back through every run of the same question. Deliberately absent on a
// distress answer — the caller decides that, not this component.
import { useState } from "react";
import { Check, ChevronLeft, ChevronRight, Copy, RotateCcw } from "lucide-react";

const ghostBtn =
  "grid size-6 place-items-center rounded-md text-ink-dim transition-colors hover:bg-shelf-2 hover:text-ink disabled:pointer-events-none disabled:opacity-35";

// P4.10 (`R-UX-3`) — "the one missing per-turn action on /ask" (re-ask,
// open trace and re-render already existed). A quiet ghost icon, same
// family as the rerun control beside it.
export function CopyControl({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className={ghostBtn}
      onClick={() => {
        void navigator.clipboard
          .writeText(text)
          .then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          })
          .catch(() => {
            /* clipboard unavailable — nothing else to fall back to */
          });
      }}
      title={copied ? "Copied" : "Copy this answer"}
      aria-label={copied ? "Copied" : "Copy this answer"}
    >
      {copied ? <Check className="size-3.5" aria-hidden="true" /> : <Copy className="size-3.5" aria-hidden="true" />}
    </button>
  );
}

export function RerunControl({
  versionCount,
  versionIndex,
  streaming,
  onRerun,
  onShowVersion,
}: {
  versionCount: number;
  versionIndex: number;
  streaming: boolean;
  onRerun: () => void;
  onShowVersion: (index: number) => void;
}) {
  const ghost = ghostBtn;

  return (
    <span className="flex items-center gap-0.5">
      {versionCount > 1 && (
        <span className="mr-0.5 flex items-center gap-0.5">
          <button
            type="button"
            className={ghost}
            onClick={() => onShowVersion(versionIndex - 1)}
            disabled={versionIndex <= 0}
            aria-label="Previous answer to this question"
          >
            <ChevronLeft className="size-3.5" aria-hidden="true" />
          </button>
          <span className="font-mono text-[10px] tabular-nums text-ink-dim" aria-live="polite">
            {versionIndex + 1}/{versionCount}
          </span>
          <button
            type="button"
            className={ghost}
            onClick={() => onShowVersion(versionIndex + 1)}
            disabled={versionIndex >= versionCount - 1}
            aria-label="Next answer to this question"
          >
            <ChevronRight className="size-3.5" aria-hidden="true" />
          </button>
        </span>
      )}
      <button
        type="button"
        className={ghost}
        onClick={onRerun}
        disabled={streaming}
        title="Try again — runs every agent again on fresh data, and keeps this answer"
        aria-label="Try again — runs every agent again on fresh data, and keeps this answer"
      >
        <RotateCcw className={`size-3.5 ${streaming ? "animate-spin" : ""}`} aria-hidden="true" />
      </button>
    </span>
  );
}
