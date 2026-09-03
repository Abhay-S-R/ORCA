"use client";

// Persona is a rendering hint, never a routing input (§5.4) — which is why
// it lives in the status bar as a view control rather than anywhere that
// looks like it configures the answer.
import { ChevronDown } from "lucide-react";
import { PERSONAS } from "./config";
import { usePersona } from "./context";

export function PersonaSelector() {
  const { persona, setPersona } = usePersona();

  return (
    <div className="relative">
      <label htmlFor="persona-select" className="sr-only">
        Viewing as
      </label>
      {/* appearance-none: the native arrow doesn't match the dark theme and
          renders at a fixed OS size that reads oversized next to the 11px
          label — same reason the global focus-visible ring (2px, 2px
          offset, sized for full-width inputs) needs a tighter override on a
          control this compact. */}
      <select
        id="persona-select"
        value={persona}
        onChange={(e) => setPersona(e.target.value as typeof persona)}
        className="cursor-pointer appearance-none rounded-sm border border-hairline bg-shelf-2/70 py-0.5 pr-5 pl-1.5 text-[11px] text-ink-muted transition-colors hover:border-hairline-strong hover:text-ink focus:border-accent/60 focus-visible:outline-offset-1"
      >
        {PERSONAS.map((p) => (
          <option key={p.id} value={p.id} className="bg-shelf-2 text-ink">
            {p.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-1.5 size-3 -translate-y-1/2 text-ink-dim"
      />
    </div>
  );
}
