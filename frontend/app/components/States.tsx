// Skeleton / EmptyState / ErrorState (§4.1 primitive list).
//
// Copy rule applied here: an empty screen is an invitation to act, and an
// error says what went wrong and what to do — neither apologises, and
// neither is decorative. That is why each takes an `action`.
import type { ReactNode } from "react";
import { AlertCircle } from "lucide-react";

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-sm bg-shelf-2/70 ${className}`}
      style={{ animationDuration: "1.8s" }}
    />
  );
}

export function EmptyState({
  title,
  body,
  action,
  icon,
}: {
  title: string;
  body: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-md border border-dashed border-hairline p-6">
      {icon && <div className="text-ink-dim">{icon}</div>}
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="max-w-[52ch] text-sm text-ink-muted">{body}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div role="alert" className="rounded-md border border-no-go/35 bg-no-go/5 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-no-go">
        <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
        {title}
      </p>
      <p className="mt-1.5 max-w-[52ch] text-sm text-ink-muted">{body}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
