// A single numeric fact: label, value, unit. Every depth, bearing, wave
// height and coordinate in the product goes through this.
//
// The rule from plan §4.1 — "chrome may be beautiful, data may not be
// decorated" — is enforced structurally here: a Readout has no colour prop,
// no gradient and no accent. Values render in mono tabular figures so a
// streaming number does not reflow its own column. If a value needs to look
// alarming, that is the hazard layer's job, not the number's.
import type { ReactNode } from "react";

export function Readout({
  label,
  value,
  unit,
  hint,
  compact = false,
  className = "",
  wrap = false,
  row = false, // label+value left, hint right (for short full-width cards)
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
  compact?: boolean;
  className?: string;
  wrap?: boolean;
  row?: boolean;
}) {
  return (
    <div
      className={`min-w-0 rounded-lg border border-hairline/60 bg-shelf-2/40 p-3 transition-colors hover:border-hairline-strong ${
        row ? "flex items-center justify-between gap-3" : ""
      } ${className}`}
    >
      <div className="min-w-0">
        <dt className="truncate font-mono text-[10px] font-semibold uppercase tracking-wider text-ink-dim" title={label}>
          {label}
        </dt>
        <dd className={compact ? "mt-1 flex min-w-0 flex-col" : "mt-1 flex min-w-0 items-baseline gap-1.5"}>
          <span
            data-readout
            title={typeof value === "string" ? value : undefined}
            className={`min-w-0 truncate font-mono font-bold tracking-tight text-ink ${compact ? "text-lg" : "text-lg sm:text-xl"}`}
          >
            {value}
          </span>
          {unit && (
            <span className={`font-mono font-medium text-ink-dim ${compact ? "text-[10px] leading-tight" : "shrink-0 text-xs"}`}>
              {unit}
            </span>
          )}
        </dd>
      </div>
      {hint && (
        <p
          className={
            row
              ? "max-w-[45%] text-right font-mono text-[11px] leading-snug text-ink-dim break-words"
              : `mt-1.5 border-t border-hairline/40 pt-1 font-mono text-[11px] text-ink-dim ${wrap ? "break-words" : "truncate"}`
          }
          title={typeof hint === "string" ? hint : undefined}
        >
          {hint}
        </p>
      )}
    </div>
  );
}

// Readouts are a description list, not a grid of divs — the label/value
// pairing is real semantics and screen readers use it.
export function ReadoutGrid({ children, cols = 2 }: { children: ReactNode; cols?: 2 | 3 | 4 | 5 }) {
  const c = {
    2: "grid-cols-1 sm:grid-cols-2",
    3: "grid-cols-1 sm:grid-cols-3",
    4: "grid-cols-2 sm:grid-cols-4",
    5: "grid-cols-2 sm:grid-cols-5",
  }[cols];
  return <dl className={`grid ${c} gap-3`}>{children}</dl>;
}
