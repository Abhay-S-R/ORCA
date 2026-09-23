"use client";

// P3.12 (orca_final §14.4, §15.2) — one plain JSON dictionary per language,
// no i18n framework (no plurals/formatting needed for this string set —
// `next-intl` only earns its keep if that changes). A missing key falls
// back to the English string, visibly logged once in dev so a gap is
// noticed while it's cheap to fix, never silently.
import { useLanguage } from "../language/context";
import bn from "./bn.json";
import en from "./en.json";
import gu from "./gu.json";
import hi from "./hi.json";
import kn from "./kn.json";
import ml from "./ml.json";
import mr from "./mr.json";
import or from "./or.json";
import ta from "./ta.json";
import te from "./te.json";
import type { LangCode } from "./languages";

type Dict = Record<string, string>;

const DICTIONARIES: Record<LangCode, Dict> = { en, ta, hi, te, ml, kn, bn, mr, gu, or };

const warned = new Set<string>();

// `vars` is a small `{name}` substitution, not a plural/format engine — the
// module docstring's "no i18n framework" call still holds; this is the one
// piece of string-building P3.12's later coverage (turn counts, source
// names) needed, so it's an extension of the same ~20-line hook rather than
// a reason to reach for next-intl.
export function translate(lang: LangCode, key: string, vars?: Record<string, string | number>): string {
  const dict = DICTIONARIES[lang] ?? DICTIONARIES.en;
  const value = dict[key];
  if (value === undefined) {
    const fallback = DICTIONARIES.en[key];
    if (process.env.NODE_ENV !== "production") {
      const warnKey = `${lang}:${key}`;
      if (!warned.has(warnKey)) {
        warned.add(warnKey);
        console.warn(`[i18n] missing key "${key}" for "${lang}" — falling back to English`);
      }
    }
    return _sub(fallback ?? key, vars);
  }
  return _sub(value, vars);
}

function _sub(str: string, vars?: Record<string, string | number>): string {
  return vars ? str.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : str;
}

export function useT(): (key: string, vars?: Record<string, string | number>) => string {
  const { language } = useLanguage();
  return (key: string, vars?: Record<string, string | number>) => translate(language, key, vars);
}
