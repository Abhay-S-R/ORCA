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
    <header className="mb-5 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {lede && <p className="mt-1 max-w-[60ch] text-sm text-ink-muted">{lede}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}

// Standard padded page body. The chart surfaces opt out of this and go
// edge-to-edge instead.
export function PageBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`p-5 ${className}`}>{children}</div>;
}
