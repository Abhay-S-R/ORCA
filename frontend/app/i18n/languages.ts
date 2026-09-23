// P3.3/P3.12 — the ten core languages, each named in its OWN script (never
// transliterated into another), plus the BCP-47 tag the browser's
// SpeechSynthesis API needs to pronounce that name aloud (P3.3: "a speaker
// icon that pronounces the language name aloud so a user who cannot read
// can choose by listening"). `voice` code list here is a superset a browser
// might match against — the Web Speech API has no guaranteed India-locale
// voice, so `speakLanguageName` (below) degrades to silence rather than
// mispronouncing through the wrong voice.
export type LangCode = "en" | "ta" | "hi" | "te" | "ml" | "kn" | "bn" | "mr" | "gu" | "or";

export type LanguageMeta = {
  code: LangCode;
  native: string; // the language's own name, in its own script
  english: string; // for screens that are still English-only
  bcp47: string;
};

export const LANGUAGES: LanguageMeta[] = [
  { code: "en", native: "English", english: "English", bcp47: "en-IN" },
  { code: "ta", native: "தமிழ்", english: "Tamil", bcp47: "ta-IN" },
  { code: "hi", native: "हिन्दी", english: "Hindi", bcp47: "hi-IN" },
  { code: "te", native: "తెలుగు", english: "Telugu", bcp47: "te-IN" },
  { code: "ml", native: "മലയാളം", english: "Malayalam", bcp47: "ml-IN" },
  { code: "kn", native: "ಕನ್ನಡ", english: "Kannada", bcp47: "kn-IN" },
  { code: "bn", native: "বাংলা", english: "Bengali", bcp47: "bn-IN" },
  { code: "mr", native: "मराठी", english: "Marathi", bcp47: "mr-IN" },
  { code: "gu", native: "ગુજરાતી", english: "Gujarati", bcp47: "gu-IN" },
  { code: "or", native: "ଓଡ଼ିଆ", english: "Odia", bcp47: "or-IN" },
];

export const LANGUAGE_CODES = LANGUAGES.map((l) => l.code);

// P3.12 — which Tailwind `font-*` utility (globals.css `@theme`, one Noto
// family per script) a piece of text in this language needs. Hindi and
// Marathi share Devanagari (same script, `language.py`'s own documented
// limitation); English needs none of these — the base UI font already
// covers Latin.
const FONT_CLASS: Record<LangCode, string> = {
  en: "",
  ta: "font-tamil",
  hi: "font-devanagari",
  mr: "font-devanagari",
  te: "font-telugu",
  ml: "font-malayalam",
  kn: "font-kannada",
  bn: "font-bengali",
  gu: "font-gujarati",
  or: "font-oriya",
};

export function fontClassForLanguage(lang: string | null | undefined): string {
  if (!lang || !isLangCode(lang)) return "";
  return FONT_CLASS[lang];
}

export function isLangCode(value: string): value is LangCode {
  return (LANGUAGE_CODES as string[]).includes(value);
}

export function languageMeta(code: string): LanguageMeta {
  return LANGUAGES.find((l) => l.code === code) ?? LANGUAGES[0];
}

// Best-effort pronunciation via the browser's own SpeechSynthesis — no
// network, no Bhashini dependency, works the moment the language chooser is
// on screen. Silently does nothing where the API or a matching voice is
// unavailable (older Safari, some Android WebViews) rather than throwing.
export function speakLanguageName(meta: LanguageMeta): void {
  try {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const utterance = new SpeechSynthesisUtterance(meta.native);
    utterance.lang = meta.bcp47;
    const voices = window.speechSynthesis.getVoices();
    const match = voices.find((v) => v.lang === meta.bcp47) ?? voices.find((v) => v.lang.startsWith(meta.code));
    if (match) utterance.voice = match;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  } catch {
    /* no speech synthesis available — the tap still selects the language */
  }
}
