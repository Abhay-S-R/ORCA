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
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium text-ink-dim truncate" title={label}>{label}</dt>
      <dd className="mt-0.5 flex min-w-0 items-baseline gap-1">
        <span data-readout className="min-w-0 break-words text-lg font-semibold text-ink">
          {value}
        </span>
        {unit && <span className="text-xs text-ink-muted shrink-0">{unit}</span>}
      </dd>
      {hint && (
        <p
          className="mt-0.5 text-[11px] text-ink-dim truncate"
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
export function ReadoutGrid({ children, cols = 2 }: { children: ReactNode; cols?: 2 | 3 | 4 }) {
  const c = { 2: "grid-cols-2", 3: "grid-cols-3", 4: "grid-cols-2 sm:grid-cols-4" }[cols];
  return <dl className={`grid ${c} gap-x-4 gap-y-3`}>{children}</dl>;
}
