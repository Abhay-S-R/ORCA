"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { PERSONA_STORAGE_KEY as STORAGE_KEY, type Persona } from "./config";
import { isPortAuthority, useAuth } from "../lib/auth";

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
  const auth = useAuth();

  // For Port Authority accounts, the persona is always fixed to coastal_authority.
  // For other accounts, the account's resolved role becomes this device's view too,
  // on first load only: a local override this session is never silently clobbered.
  useEffect(() => {
    if (auth.status !== "signed_in" || !auth.profile) return;
    if (isPortAuthority(auth.profile)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPersonaState("coastal_authority");
      return;
    }
    if (auth.profile.default_persona === "unresolved") return;
    let overridden = false;
    try {
      overridden = window.localStorage.getItem(STORAGE_KEY) !== null;
    } catch {
      /* storage disabled — treat as no local override */
    }
    // Syncing from the external auth store (useAuth), same reasoning as the
    // localStorage sync effect below.
    if (!overridden) setPersonaState(auth.profile.default_persona as Persona);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.status, auth.profile?.default_persona, auth.profile?.role, auth.profile?.is_port_authority]);

  useEffect(() => {
    // Reading localStorage directly in useState's initializer would mismatch
    // the server-rendered HTML (no `window` during SSR) and crash hydration.
    const stored = window.localStorage.getItem(STORAGE_KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored) setPersonaState(stored as Persona);
  }, []);

  function setPersona(p: Persona) {
    if (auth.status === "signed_in" && isPortAuthority(auth.profile)) {
      setPersonaState("coastal_authority");
      return;
    }
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
