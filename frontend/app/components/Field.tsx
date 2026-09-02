// Design system primitive (plan §3.2). Render-prop child gets the label's
// `id` so every control gets an accessible name without each call site
// re-deriving one (accessibility baseline lives in the primitive, not six
// surfaces remembering it).
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
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      {children(id)}
      {hint && <p className="mt-1 text-xs text-black/50">{hint}</p>}
    </div>
  );
}
