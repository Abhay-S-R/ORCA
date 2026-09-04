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
    <div className="mb-4">
      <label htmlFor={id} className="mb-1.5 block text-[11px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
        {label}
      </label>
      {children(id)}
      {hint && <p className="mt-1 text-[11px] font-mono text-ink-dim">{hint}</p>}
    </div>
  );
}

// Shared input skin — so an <input>, a <select> and a <textarea> cannot drift
// apart across six surfaces built by six people.
export const inputClass =
  "w-full rounded-lg border border-hairline bg-shelf-1/90 px-3 py-2 text-sm text-ink placeholder:text-ink-dim/60 transition-all hover:border-hairline-strong focus:border-ocean-cyan/70 focus:bg-shelf-2/90 shadow-inner";
