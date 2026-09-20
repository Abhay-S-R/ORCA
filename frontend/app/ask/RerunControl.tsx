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
import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";

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
  const ghost =
    "grid size-6 place-items-center rounded-md text-ink-dim transition-colors hover:bg-shelf-2 hover:text-ink disabled:pointer-events-none disabled:opacity-35";

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
