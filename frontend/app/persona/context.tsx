"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { type Persona } from "./config";

const STORAGE_KEY = "orca.persona";

type PersonaContextValue = {
  persona: Persona;
  setPersona: (p: Persona) => void;
};

const PersonaContext = createContext<PersonaContextValue | null>(null);

export function PersonaProvider({ children }: { children: ReactNode }) {
  // "unresolved" until inference/explicit choice lands (state.py's
  // stakeholder_persona_source: "explicit" | "inferred_high" | "inferred_low").
  // Phase 1 has no server-side inference, so this is explicit-or-unresolved only.
  const [persona, setPersonaState] = useState<Persona>("unresolved");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) setPersonaState(stored as Persona);
  }, []);

  function setPersona(p: Persona) {
    setPersonaState(p);
    window.localStorage.setItem(STORAGE_KEY, p);
  }

  return <PersonaContext.Provider value={{ persona, setPersona }}>{children}</PersonaContext.Provider>;
}

export function usePersona(): PersonaContextValue {
  const ctx = useContext(PersonaContext);
  if (!ctx) throw new Error("usePersona must be used within a PersonaProvider");
  return ctx;
}
