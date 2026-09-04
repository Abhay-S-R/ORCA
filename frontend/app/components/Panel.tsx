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
    <section
      className={`glass tactical-frame relative rounded-xl border border-hairline/90 ${
        dense ? "p-3.5" : "p-5"
      } shadow-lg ${className}`}
    >
      {title && (
        <header className="mb-3.5 flex items-center justify-between gap-3 border-b border-hairline/50 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="size-1.5 rounded-full bg-ocean-cyan/70" aria-hidden="true" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-ink">{title}</h2>
          </div>
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
    <section
      className={`relative rounded-xl border border-hairline bg-shelf-1/80 p-5 shadow-lg backdrop-blur-sm ${className}`}
    >
      {title && (
        <header className="mb-3.5 flex items-center justify-between gap-3 border-b border-hairline/50 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="size-1.5 rounded-full bg-ocean-cyan/70" aria-hidden="true" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-ink">{title}</h2>
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
