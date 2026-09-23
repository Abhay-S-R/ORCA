"use client";

// P3.3/P3.12/P3.13 — Language selection dropdown in the header status bar.
// Reflects and mutates the active UI/answer language live across all surfaces.
import { ChevronDown, Globe } from "lucide-react";
import { LANGUAGES, type LangCode } from "../i18n/languages";
import { useLanguage } from "../language/context";

export function LanguageSelector() {
  const { language, setLanguage } = useLanguage();

  return (
    <div className="relative inline-flex items-center">
      <label htmlFor="language-select" className="sr-only">
        Select UI & Answer Language
      </label>
      <div className="pointer-events-none absolute left-2 flex items-center text-ocean-cyan/80">
        <Globe className="size-3 text-ocean-cyan" aria-hidden="true" />
      </div>
      <select
        id="language-select"
        value={language}
        onChange={(e) => setLanguage(e.target.value as LangCode)}
        className="cursor-pointer appearance-none rounded border border-hairline bg-shelf-2/80 py-1 pr-6 pl-6 text-[11px] font-medium tracking-wide text-ink transition-all hover:border-ocean-cyan/50 hover:bg-shelf-3/80 focus:border-ocean-cyan focus-visible:outline-offset-1 shadow-sm"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code} className="bg-shelf-2 text-ink py-1">
            {l.code === "en" ? "English" : `${l.native} (${l.english})`}
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
