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
    <div className="relative flex items-center w-full">
      <label htmlFor="persona-select" className="sr-only">
        Viewing as
      </label>
      <select
        id="persona-select"
        value={persona}
        onChange={(e) => setPersona(e.target.value as typeof persona)}
        className="w-full cursor-pointer appearance-none rounded-lg border border-hairline bg-shelf-2/90 py-1.5 pr-8 pl-3 text-[11px] font-semibold tracking-wide text-ink transition-all hover:border-ocean-cyan/60 hover:bg-shelf-3 focus:border-ocean-cyan focus-visible:outline-none shadow-xs"
      >
        {PERSONAS.map((p) => (
          <option key={p.id} value={p.id} className="bg-shelf-2 text-ink">
            {p.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-ink-dim"
      />
    </div>
  );
}
