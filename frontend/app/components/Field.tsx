// Form primitive. The render-prop hands the control the label's `id`, so an
// accessible name is inherited rather than re-derived at six call sites.
"use client";

import { useId, type ReactNode } from "react";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="mb-3">
      <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-ink-muted">
        {label}
      </label>
      {children(id)}
      {hint && <p className="mt-1 text-[11px] text-ink-dim">{hint}</p>}
    </div>
  );
}

// Shared input skin — so an <input>, a <select> and a <textarea> cannot drift
// apart across six surfaces built by six people.
export const inputClass =
  "w-full rounded-sm border border-hairline bg-shelf-1/80 px-2.5 py-2 text-sm text-ink placeholder:text-ink-dim transition-colors hover:border-hairline-strong focus:border-accent/60";
