"use client";

// Persona is a rendering hint, never a routing input (§5.4) — which is why
// it lives in the status bar as a view control rather than anywhere that
// looks like it configures the answer.
import { PERSONAS } from "./config";
import { usePersona } from "./context";

export function PersonaSelector() {
  const { persona, setPersona } = usePersona();

  return (
    <>
      <label htmlFor="persona-select" className="sr-only">
        Viewing as
      </label>
      <select
        id="persona-select"
        value={persona}
        onChange={(e) => setPersona(e.target.value as typeof persona)}
        className="rounded-sm border border-hairline bg-shelf-2/70 px-1.5 py-0.5 text-[11px] text-ink-muted transition-colors hover:border-hairline-strong hover:text-ink"
      >
        {PERSONAS.map((p) => (
          <option key={p.id} value={p.id} className="bg-shelf-2 text-ink">
            {p.label}
          </option>
        ))}
      </select>
    </>
  );
}
