"use client";

// P3.3 (`R-NEW-12`) + P3.4 (`R-UX-6`) — the two MANDATORY setup screens:
// language, then role with home port & vessel type. Full screen, not skippable,
// not buried in settings.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Anchor, Check, Ship, Volume2 } from "lucide-react";
import { Button } from "../components/Button";
import { Field, inputClass } from "../components/Field";
import { OrcaMark } from "../nav";
import { authFetch, invalidateProfile, setHomePort, useAuth } from "../lib/auth";
import { useLanguage } from "../language/context";
import { LANGUAGES, fontClassForLanguage, speakLanguageName, type LangCode } from "../i18n/languages";
import { PERSONAS, type Persona } from "../persona/config";
import { usePersona } from "../persona/context";
import { useT } from "../i18n/useT";
import { PRESET_HOME_PORTS } from "../profile/page";

type Step = "language" | "role";

const VESSEL_OPTIONS = [
  { value: "fibreglass", label: "Fibreglass boat" },
  { value: "catamaran", label: "Catamaran" },
  { value: "mechanised", label: "Mechanised boat" },
  { value: "trawler", label: "Trawler" },
  { value: "cargo", label: "Cargo vessel" },
] as const;

export default function OnboardingPage() {
  const router = useRouter();
  const auth = useAuth();
  const { language, setLanguage } = useLanguage();
  const { setPersona } = usePersona();
  const t = useT();
  const [step, setStep] = useState<Step>("language");
  const [chosenLanguage, setChosenLanguage] = useState<LangCode>(language);
  const [chosenRole, setChosenRole] = useState<Persona | null>("fisherman");

  // Home port selection state
  const [selectedPortPreset, setSelectedPortPreset] = useState("Thoothukudi (Tuticorin)");
  const [customLat, setCustomLat] = useState("");
  const [customLon, setCustomLon] = useState("");
  const [customPortName, setCustomPortName] = useState("");

  // Vessel selection state
  const [chosenVesselClass, setChosenVesselClass] = useState("fibreglass");
  const [vesselName, setVesselName] = useState("");

  const [saving, setSaving] = useState(false);

  // A signed-out visitor, or one whose profile already resolved a persona,
  // has nothing to do here.
  useEffect(() => {
    if (auth.status === "signed_out") router.replace("/login");
    else if (auth.status === "signed_in" && auth.profile && auth.profile.default_persona !== "unresolved") {
      router.replace("/ask");
    }
  }, [auth.status, auth.profile, router]);

  useEffect(() => {
    setChosenLanguage(language);
  }, [language]);

  function chooseLanguage(code: LangCode) {
    setChosenLanguage(code);
    setLanguage(code);
    speakLanguageName(LANGUAGES.find((l) => l.code === code)!);
  }

  function handlePortPresetChange(val: string) {
    setSelectedPortPreset(val);
    if (val !== "custom") {
      setCustomLat("");
      setCustomLon("");
      setCustomPortName("");
    }
  }

  async function finish() {
    if (!chosenRole) return;
    setSaving(true);
    setPersona(chosenRole);

    try {
      // 1. Save persona
      await authFetch("/api/profile/persona", {
        method: "PUT",
        body: JSON.stringify({ default_persona: chosenRole }),
      });

      // 2. Save home port
      if (selectedPortPreset === "custom") {
        const lat = parseFloat(customLat);
        const lon = parseFloat(customLon);
        if (!isNaN(lat) && !isNaN(lon)) {
          await setHomePort(lat, lon, customPortName.trim() || undefined);
        }
      } else if (selectedPortPreset) {
        const preset = PRESET_HOME_PORTS.find((p) => p.name === selectedPortPreset);
        if (preset) {
          await setHomePort(preset.lat, preset.lon, preset.name);
        }
      }

      // 3. Save vessel & make active
      if (chosenVesselClass) {
        const vRes = await authFetch("/api/vessels", {
          method: "POST",
          body: JSON.stringify({
            vessel_class: chosenVesselClass,
            ...(vesselName.trim() ? { name: vesselName.trim() } : {}),
          }),
        }).catch(() => null);

        if (vRes?.ok) {
          const created = await vRes.json();
          await authFetch("/api/profile/active-vessel", {
            method: "PUT",
            body: JSON.stringify({ vessel_id: created.id }),
          }).catch(() => {});
        }
      }
    } catch {
      /* best-effort */
    } finally {
      invalidateProfile();
    }

    setSaving(false);
    window.location.href = "/ask";
  }

  return (
    <div className="mx-auto flex h-full max-w-lg flex-col justify-center gap-5 p-5">
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

          {/* 1. Persona Selection */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {PERSONAS.filter((p) => p.id !== "unresolved").map((p) => {
              const selected = chosenRole === p.id;
              const roleId = p.id as Exclude<Persona, "unresolved">;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setChosenRole(p.id)}
                  aria-pressed={selected}
                  className={`glass flex items-start justify-between gap-2.5 rounded-xl border p-3 text-left transition-all ${
                    selected ? "border-accent bg-accent/5 shadow-sm" : "border-hairline/80 hover:border-hairline-strong"
                  }`}
                >
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-ink">{t(`role.${roleId}`)}</div>
                    <div className="mt-0.5 text-[11px] text-ink-muted line-clamp-2">{t(`role.${roleId}.desc`)}</div>
                  </div>
                  {selected && <Check className="size-3.5 shrink-0 text-accent mt-0.5" aria-hidden="true" />}
                </button>
              );
            })}
          </div>

          {/* 2. Home Port Selection */}
          <div className="glass flex flex-col gap-2 rounded-xl border border-hairline/80 p-3.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-ink">
              <Anchor className="size-3.5 text-ocean-cyan" aria-hidden="true" />
              <span>{t("profile.selectPort")}</span>
            </div>
            <select
              className={inputClass}
              value={selectedPortPreset}
              onChange={(e) => handlePortPresetChange(e.target.value)}
            >
              <option value="">-- {t("profile.selectPort")} --</option>
              {PRESET_HOME_PORTS.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.lat > 0 ? `${p.lat.toFixed(2)}°N` : `${Math.abs(p.lat).toFixed(2)}°S`}, {p.lon.toFixed(2)}°E)
                </option>
              ))}
              <option value="custom">-- {t("profile.customPort")} --</option>
            </select>

            {selectedPortPreset === "custom" && (
              <div className="mt-1 grid grid-cols-2 gap-2">
                <input
                  className={inputClass}
                  placeholder="Latitude (e.g. 8.77)"
                  value={customLat}
                  onChange={(e) => setCustomLat(e.target.value)}
                  inputMode="decimal"
                />
                <input
                  className={inputClass}
                  placeholder="Longitude (e.g. 78.23)"
                  value={customLon}
                  onChange={(e) => setCustomLon(e.target.value)}
                  inputMode="decimal"
                />
                <input
                  className={`col-span-2 ${inputClass}`}
                  placeholder="Port / Place name (optional)"
                  value={customPortName}
                  onChange={(e) => setCustomPortName(e.target.value)}
                />
              </div>
            )}
          </div>

          {/* 3. Vessel Type Selection */}
          <div className="glass flex flex-col gap-2 rounded-xl border border-hairline/80 p-3.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-ink">
              <Ship className="size-3.5 text-ocean-cyan" aria-hidden="true" />
              <span>{t("profile.vesselType")}</span>
            </div>
            <select
              className={inputClass}
              value={chosenVesselClass}
              onChange={(e) => setChosenVesselClass(e.target.value)}
            >
              {VESSEL_OPTIONS.map((v) => (
                <option key={v.value} value={v.value}>
                  {v.label}
                </option>
              ))}
            </select>
            <input
              className={inputClass}
              placeholder="Vessel name (optional, e.g. Sagar-1)"
              value={vesselName}
              onChange={(e) => setVesselName(e.target.value)}
            />
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

