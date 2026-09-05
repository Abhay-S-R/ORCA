// Page heading. One h1 per surface, with a single line saying what the
// surface is for — written from the user's side ("what you can decide here"),
// not the system's ("Agent 5 output viewer").
import type { ReactNode } from "react";

export function PageHeader({
  title,
  lede,
  action,
}: {
  title: string;
  lede?: string;
  action?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4 border-b border-hairline/60 pb-5">
      <div>
        <div className="mb-1.5 flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-ocean-cyan" aria-hidden="true" />
          <span className="font-mono text-[10px] tracking-widest text-ocean-cyan uppercase">
            ORCA CONSOLE // OPERATIONAL SURFACE
          </span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">{title}</h1>
        {lede && <p className="mt-1.5 max-w-[64ch] text-sm leading-relaxed text-ink-muted">{lede}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}

// Standard padded page body. The chart surfaces opt out of this and go
// edge-to-edge instead.
export function PageBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`p-5 lg:p-7 ${className}`}>{children}</div>;
}
