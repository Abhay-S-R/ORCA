"use client";

// Map layer control (§4.7). Two things the plain checkbox would lose and the
// budget needs: a `heavy` marker, because mobile allows only two concurrent
// heavy layers, and a swatch, so the legend IS the control rather than a
// second thing to cross-reference.
import { Lock } from "lucide-react";

export function LayerToggle({
  label,
  checked,
  onChange,
  swatch,
  heavy = false,
  disabled = false,
  disabledReason,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  swatch?: string;
  heavy?: boolean;
  disabled?: boolean;
  disabledReason?: string;
}) {
  return (
    <label
      className={`flex cursor-pointer items-center gap-2.5 rounded-sm px-2 py-1.5 text-xs transition-colors ${
        disabled ? "cursor-not-allowed opacity-45" : "hover:bg-shelf-2/70"
      }`}
      title={disabled ? disabledReason : undefined}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="size-3.5 shrink-0 accent-[var(--color-accent)]"
      />
      {swatch && (
        <span
          aria-hidden="true"
          className="size-2.5 shrink-0 rounded-[2px] ring-1 ring-inset ring-white/20"
          style={{ background: swatch }}
        />
      )}
      <span className={`flex-1 ${checked ? "text-ink" : "text-ink-muted"}`}>{label}</span>
      {heavy && (
        <span className="text-[10px] text-ink-dim" title="Heavy layer — counts against the mobile limit of 2">
          heavy
        </span>
      )}
      {disabled && <Lock className="size-3 text-ink-dim" aria-hidden="true" />}
    </label>
  );
}
