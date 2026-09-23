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
import { LANGUAGES, fontClassForLanguage, type LangCode } from "../i18n/languages";
import { useLanguage } from "../language/context";
import { useT } from "../i18n/useT";

const CORRECTABLE: { id: Persona; labelKey: string }[] = [
  { id: "fisherman", labelKey: "personaCorrection.fisherman" },
  { id: "commercial_navigator", labelKey: "personaCorrection.navigator" },
  { id: "researcher", labelKey: "personaCorrection.researcher" },
  { id: "coastal_authority", labelKey: "personaCorrection.authority" },
];

export type RenderResult = {
  final_english_response: string;
  // P3.13 — set only when the render request carried a `language`; absent
  // (or null, when Bhashini/IndicTrans2 couldn't reach it) means the
  // caller should keep showing the English text, not blank it out.
  final_vernacular_response?: string | null;
  language?: string | null;
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
  const t = useT();
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
      setError(t("personaCorrection.error"));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="mt-3 border-t border-hairline pt-3">
      <p className="mb-1.5 text-xs font-medium text-ink-dim">{t("personaCorrection.imActually")}</p>
      <div className="flex flex-wrap gap-1.5">
        {CORRECTABLE.filter((p) => p.id !== currentPersona).map((p) => (
          <Button
            key={p.id}
            variant="ghost"
            className="px-2.5 py-1.5 text-xs"
            disabled={pending !== null}
            onClick={() => correct(p.id)}
          >
            {pending === p.id ? t("personaCorrection.rendering") : t(p.labelKey)}
          </Button>
        ))}
      </div>
      {error && <p className="mt-1.5 text-xs text-no-go">{error}</p>}
    </div>
  );
}

// P3.13 (orca_final §15.2) — "speak to me in Telugu" as a tap, not just a
// typed command: same zero-re-query contract as PersonaCorrection above,
// through the same `/render` endpoint, now extended to take a `language`.
export function LanguageSwitch({
  queryId,
  persona,
  currentLanguage,
  onRendered,
}: {
  queryId: string | undefined;
  persona: Persona;
  currentLanguage: string | null | undefined;
  onRendered: (result: RenderResult) => void;
}) {
  const { setLanguage } = useLanguage();
  const t = useT();
  const [pending, setPending] = useState<LangCode | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!queryId) return null;

  async function switchTo(lang: LangCode) {
    setPending(lang);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query_id: queryId, persona, language: lang }),
      });
      if (!res.ok) throw new Error(`render failed: ${res.status}`);
      const data: RenderResult = await res.json();
      onRendered(data);
      setLanguage(lang);
    } catch {
      setError(t("personaCorrection.languageError"));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="mt-3 border-t border-hairline pt-3">
      <p className="mb-1.5 text-xs font-medium text-ink-dim">{t("personaCorrection.speakToMeIn")}</p>
      <div className="flex flex-wrap gap-1.5">
        {LANGUAGES.filter((l) => l.code !== currentLanguage).map((l) => (
          <Button
            key={l.code}
            variant="ghost"
            className={`px-2.5 py-1.5 text-xs ${fontClassForLanguage(l.code)}`}
            disabled={pending !== null}
            onClick={() => switchTo(l.code)}
          >
            {pending === l.code ? "…" : l.native}
          </Button>
        ))}
      </div>
      {error && <p className="mt-1.5 text-xs text-no-go">{error}</p>}
    </div>
  );
}
