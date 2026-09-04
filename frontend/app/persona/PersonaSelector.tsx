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
    <div className="relative inline-flex items-center">
      <label htmlFor="persona-select" className="sr-only">
        Viewing as
      </label>
      <div className="pointer-events-none absolute left-2 hidden items-center gap-1 sm:flex">
        <span className="size-1 rounded-full bg-ocean-cyan/70" />
      </div>
      <select
        id="persona-select"
        value={persona}
        onChange={(e) => setPersona(e.target.value as typeof persona)}
        className="cursor-pointer appearance-none rounded border border-hairline bg-shelf-2/80 py-1 pr-6 pl-2 sm:pl-4 text-[11px] font-medium tracking-wide text-ink transition-all hover:border-ocean-cyan/50 hover:bg-shelf-3/80 focus:border-ocean-cyan focus-visible:outline-offset-1 shadow-sm"
      >
        {PERSONAS.map((p) => (
          <option key={p.id} value={p.id} className="bg-shelf-2 text-ink">
            {p.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-2 size-3 -translate-y-1/2 text-ink-dim"
      />
    </div>
  );
}
