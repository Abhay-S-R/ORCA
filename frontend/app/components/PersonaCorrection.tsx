"use client";

// Persona-correction control (parent plan §4.5 differentiator 7 / Phase 3
// D1 Day 20): "I'm actually a ___" re-renders the SAME already-computed
// answer under a different persona via POST /render — zero /query call,
// zero specialist agent re-invoked (orca/api/trace_routes.py render_persona).
// The numbers never change here; only the wording does.
import { useState } from "react";
import { Button } from "./Button";
import { type Persona } from "../persona/config";
import { API_BASE } from "../lib/apiBase";

const CORRECTABLE: { id: Persona; label: string }[] = [
  { id: "fisherman", label: "Fisherman" },
  { id: "commercial_navigator", label: "Navigator" },
  { id: "researcher", label: "Researcher" },
  { id: "coastal_authority", label: "Authority" },
];

export type RenderResult = {
  final_english_response: string;
  confidence_tier: string;
  citations: { agent_name: string; dataset: string; acquisition_timestamp: string }[];
};

export function PersonaCorrection({
  queryId,
  currentPersona,
  onRendered,
  onPersonaChange,
}: {
  queryId: string | undefined;
  currentPersona: Persona;
  onRendered: (result: RenderResult) => void;
  onPersonaChange: (p: Persona) => void;
}) {
  const [pending, setPending] = useState<Persona | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!queryId) return null;

  async function correct(persona: Persona) {
    setPending(persona);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query_id: queryId, persona }),
      });
      if (!res.ok) throw new Error(`render failed: ${res.status}`);
      const data = await res.json();
      onRendered(data);
      onPersonaChange(persona);
    } catch {
      setError("Could not re-render for that persona — the original answer is still shown.");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="mt-3 border-t border-hairline pt-3">
      <p className="mb-1.5 text-xs font-medium text-ink-dim">I&apos;m actually a…</p>
      <div className="flex flex-wrap gap-1.5">
        {CORRECTABLE.filter((p) => p.id !== currentPersona).map((p) => (
          <Button
            key={p.id}
            variant="ghost"
            className="px-2.5 py-1.5 text-xs"
            disabled={pending !== null}
            onClick={() => correct(p.id)}
          >
            {pending === p.id ? "Rendering…" : p.label}
          </Button>
        ))}
      </div>
      {error && <p className="mt-1.5 text-xs text-no-go">{error}</p>}
    </div>
  );
}
