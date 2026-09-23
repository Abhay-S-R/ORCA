"use client";

// P3.3/P3.12/P3.13 — the active UI/answer language, same hydration-safe
// localStorage pattern as ../persona/context.tsx. Signed out: localStorage
// only. Signed in: the account's `users.language` is the source of truth,
// pushed to `PUT /api/profile/language` on every change so it survives a
// reload or a different device — this context does not itself fetch the
// profile (useAuth already does; a page that has both syncs them, see
// SyncLanguageFromProfile below).
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { authFetch, getToken, invalidateProfile } from "../lib/auth";
import { isLangCode, type LangCode } from "../i18n/languages";

const STORAGE_KEY = "orca.language";

type LanguageContextValue = {
  language: LangCode;
  setLanguage: (lang: LangCode, opts?: { persist?: boolean }) => void;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

function browserDefaultLanguage(): LangCode {
  try {
    const locale = window.navigator.language.toLowerCase();
    const match = locale.split("-")[0];
    if (isLangCode(match)) return match;
  } catch {
    /* navigator.language unavailable — English default below */
  }
  return "en";
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  // "en" on the server pass and first client render (hydration-safe, same
  // reasoning as PersonaProvider); synced from localStorage/device locale
  // right after mount, and from the account profile once it loads.
  const [language, setLanguageState] = useState<LangCode>("en");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored && isLangCode(stored)) setLanguageState(stored);
    else setLanguageState(browserDefaultLanguage());
  }, []);

  function setLanguage(lang: LangCode, opts: { persist?: boolean } = {}) {
    setLanguageState(lang);
    try {
      window.localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      /* private mode / storage disabled — the choice still applies this session */
    }
    if (opts.persist !== false && getToken()) {
      void authFetch("/api/profile/language", {
        method: "PUT",
        body: JSON.stringify({ language: lang }),
      })
        .then(() => invalidateProfile()) // same stale-cache bug as persona (see auth.ts)
        .catch(() => {
          /* best-effort — the local choice already applied */
        });
    }
  }

  return <LanguageContext.Provider value={{ language, setLanguage }}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within a LanguageProvider");
  return ctx;
}
