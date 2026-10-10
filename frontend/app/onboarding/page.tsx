"use client";

// P3.3 (`R-NEW-12`) + P3.4 (`R-UX-6`) — the two MANDATORY setup screens:
// language, then role. Full screen, not skippable, not buried in settings.
// Everything else the wizard would ask (home port, vessel, crew, phone/SMS
// consent, reading comfort, units) is deliberately NOT here — the DLC's own
// rule is "ask at the moment it first matters", in conversation, which is
// Ask's job, not a wizard's. Reached from `AppChrome`'s onboarding gate
// (`default_persona === "unresolved"`), for any signed-in account, not only
// a fresh signup.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Volume2 } from "lucide-react";
import { Button } from "../components/Button";
import { OrcaMark } from "../nav";
import { authFetch, invalidateProfile, useAuth } from "../lib/auth";
import { useLanguage } from "../language/context";
import { LANGUAGES, fontClassForLanguage, speakLanguageName, type LangCode } from "../i18n/languages";
import { PERSONAS, type Persona } from "../persona/config";
import { usePersona } from "../persona/context";
import { useT } from "../i18n/useT";

type Step = "language" | "role";

// Role descriptions are now sourced from i18n via useT() below (P3.4/P3.12),
// so they render in whichever language the user just selected on step 1.

export default function OnboardingPage() {
  const router = useRouter();
  const auth = useAuth();
  const { language, setLanguage } = useLanguage();
  const { setPersona } = usePersona();
  const t = useT();
  const [step, setStep] = useState<Step>("language");
  const [chosenLanguage, setChosenLanguage] = useState<LangCode>(language);
  const [chosenRole, setChosenRole] = useState<Persona | null>(null);
  const [saving, setSaving] = useState(false);

  // A signed-out visitor, or one whose profile already resolved a persona,
  // has nothing to do here.
  useEffect(() => {
    if (auth.status === "signed_out") router.replace("/login");
    else if (auth.status === "signed_in" && auth.profile && auth.profile.default_persona !== "unresolved") {
      router.replace("/ask");
    }
  }, [auth.status, auth.profile, router]);

  function chooseLanguage(code: LangCode) {
    setChosenLanguage(code);
    setLanguage(code);
    speakLanguageName(LANGUAGES.find((l) => l.code === code)!);
  }

  async function finish() {
    if (!chosenRole) return;
    setSaving(true);
    setPersona(chosenRole);
    try {
      await authFetch("/api/profile/persona", {
        method: "PUT",
        body: JSON.stringify({ default_persona: chosenRole }),
      });
    } catch {
      /* best-effort — the local choice still takes effect this session */
    } finally {
      // Bug found in browser testing: without this, AppChrome's onboarding
      // gate re-read the pre-mutation cached profile ("unresolved") on the
      // very next render and bounced straight back here.
      invalidateProfile();
    }
    setSaving(false);
    router.replace("/ask");
  }

  return (
    <div className="mx-auto flex h-full max-w-md flex-col justify-center gap-6 p-5">
      <div className="flex flex-col items-center gap-2 text-center">
        <OrcaMark className="size-8" />
        <div className="flex items-center gap-1.5" aria-hidden="true">
          <span className={`h-1.5 w-6 rounded-full ${step === "language" ? "bg-accent" : "bg-go"}`} />
          <span className={`h-1.5 w-6 rounded-full ${step === "role" ? "bg-accent" : "bg-hairline"}`} />
        </div>
      </div>

      {step === "language" ? (
        <>
          <div className="text-center">
            <h1 className="text-lg font-semibold tracking-tight text-ink">{t("onboarding.languageTitle")}</h1>
            <p className="mt-1 text-xs text-ink-muted">{t("onboarding.languageHint")}</p>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            {LANGUAGES.map((lang) => {
              const selected = chosenLanguage === lang.code;
              return (
                <button
                  key={lang.code}
                  type="button"
                  onClick={() => chooseLanguage(lang.code)}
                  aria-pressed={selected}
                  className={`glass relative flex min-h-[76px] flex-col items-center justify-center gap-1 rounded-xl border p-3 text-center transition-all ${
                    selected ? "border-accent shadow-md" : "border-hairline/80 hover:border-hairline-strong"
                  }`}
                >
                  <span className={`text-base font-semibold text-ink ${fontClassForLanguage(lang.code)}`}>{lang.native}</span>
                  <span className="text-[10px] text-ink-dim">{lang.english}</span>
                  <span
                    role="button"
                    aria-label={`Hear ${lang.english} pronounced`}
                    onClick={(e) => {
                      e.stopPropagation();
                      speakLanguageName(lang);
                    }}
                    className="mt-0.5 inline-flex size-6 items-center justify-center rounded-full text-ink-dim hover:bg-shelf-2 hover:text-accent"
                  >
                    <Volume2 className="size-3.5" aria-hidden="true" />
                  </span>
                  {selected && <Check className="absolute top-2 right-2 size-3.5 text-accent" aria-hidden="true" />}
                </button>
              );
            })}
          </div>
          <Button variant="primary" className="w-full" onClick={() => setStep("role")}>
            {t("common.continue")}
          </Button>
        </>
      ) : (
        <>
          <div className="text-center">
            <h1 className="text-lg font-semibold tracking-tight text-ink">{t("onboarding.roleTitle")}</h1>
            <p className="mt-1 text-xs text-ink-muted">{t("onboarding.roleHint")}</p>
          </div>
          <div className="flex flex-col gap-2.5">
            {PERSONAS.filter((p) => p.id !== "unresolved").map((p) => {
              const selected = chosenRole === p.id;
              const roleId = p.id as Exclude<Persona, "unresolved">;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setChosenRole(p.id)}
                  aria-pressed={selected}
                  className={`glass flex items-center justify-between gap-3 rounded-xl border p-4 text-left transition-all ${
                    selected ? "border-accent shadow-md" : "border-hairline/80 hover:border-hairline-strong"
                  }`}
                >
                  <div>
                    {/* P3.4 / P3.12 — role label and description translated into the chosen language */}
                    <div className="text-sm font-semibold text-ink">{t(`role.${roleId}`)}</div>
                    <div className="mt-0.5 text-xs text-ink-muted">{t(`role.${roleId}.desc`)}</div>
                  </div>
                  {selected && <Check className="size-4 shrink-0 text-accent" aria-hidden="true" />}
                </button>
              );
            })}
          </div>
          <div className="flex gap-2.5">
            <Button variant="ghost" className="flex-1" onClick={() => setStep("language")}>
              {t("common.back")}
            </Button>
            <Button variant="primary" className="flex-1" onClick={finish} disabled={!chosenRole || saving}>
              {saving ? "…" : t("onboarding.finish")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
