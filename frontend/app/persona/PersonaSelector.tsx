"use client";

import { PERSONAS } from "./config";
import { usePersona } from "./context";

export function PersonaSelector() {
  const { persona, setPersona } = usePersona();
  return (
    <div className="mb-4">
      <label htmlFor="persona-select" className="mb-1 block text-xs font-medium text-black/60">
        Viewing as
      </label>
      <select
        id="persona-select"
        value={persona}
        onChange={(e) => setPersona(e.target.value as typeof persona)}
        className="w-full rounded border border-black/20 px-2 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        {PERSONAS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>
    </div>
  );
}
