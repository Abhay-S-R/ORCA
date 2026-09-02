// The glass panel (plan §4.1). Panels float over the chart rather than boxing
// it in — that is the whole layout thesis, so the blur and the hairline live
// here once and every docked readout inherits them.
//
// Semantic <section> with a heading, so a screen reader gets the same panel
// structure a sighted user gets from the hairline.
import type { ReactNode } from "react";

export function Panel({
  title,
  action,
  children,
  className = "",
  dense = false,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  dense?: boolean;
}) {
  return (
    <section className={`glass rounded-md ${dense ? "p-3" : "p-4"} ${className}`}>
      {title && (
        <header className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

// Card is the opaque sibling: used in scrolling page content where a blurred
// panel over another panel would muddy. Same hairline, no backdrop cost.
export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-md border border-hairline bg-shelf-1/70 p-4 ${className}`}>
      {title && (
        <header className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
