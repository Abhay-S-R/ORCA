"use client";

import { LifeBuoy, Maximize2, Phone, ShieldAlert } from "lucide-react";
import type { FinalResponse } from "../ask/useAskThread";
import type { DistressOverlayData } from "./DistressAlertOverlay";
import { useLanguage } from "../language/context";
import { fontClassForLanguage, isLangCode, type LangCode } from "../i18n/languages";
import {
  tDistress,
  resolveDistressCategoryKey,
  translateSurvivalCategory,
  translateAuthorityName,
  translateEmergencyUnit,
  translateSurvivalStep,
} from "./DistressAlertOverlay";

interface DistressChatCardProps {
  answer: FinalResponse;
  onOpenOverlay?: (data: DistressOverlayData) => void;
  actions?: React.ReactNode;
}

export function DistressChatCard({ answer, onOpenOverlay, actions }: DistressChatCardProps) {
  const { language: contextLang } = useLanguage();
  const lang: LangCode = isLangCode(answer.detected_language ?? "")
    ? (answer.detected_language as LangCode)
    : contextLang;

  const fontClass = fontClassForLanguage(lang);

  const mrcc = answer.mrcc_contact;
  const mrccPhone = mrcc?.primary?.phone ?? "1554";
  const auth = answer.target_authority;
  const rawAuthName = auth?.display_name ?? auth?.authority_name ?? (auth?.port_name ? `${auth.port_name} Coastal Authority` : "Coastal Authority");
  const translatedAuthName = translateAuthorityName(rawAuthName, lang);
  const authPhone = auth?.phone ?? "1093";
  const rawAuthUnit = auth?.emergency_unit ?? "Port Control & Marine Police";
  const translatedAuthUnit = translateEmergencyUnit(rawAuthUnit, lang);

  // Parse survival steps from structured data or text
  let steps: string[] = answer.survival_suggestions ?? answer.survival_advice?.steps ?? [];
  const rawCategoryTitle = answer.survival_advice?.category ?? "Emergency Maritime Survival Actions";

  if (steps.length === 0 && answer.final_english_response) {
    const lines = answer.final_english_response.split("\n");
    const extracted: string[] = [];
    for (const l of lines) {
      const match = l.match(/^\s*\d+\.\s*(.+)/);
      if (match) {
        extracted.push(match[1].trim());
      }
    }
    if (extracted.length > 0) {
      steps = extracted;
    }
  }

  if (steps.length === 0) {
    steps = [
      "DON LIFE JACKETS IMMEDIATELY: Ensure every person aboard fastens a certified life vest (PFD) with whistle attached.",
      "ACTIVATE BILGE PUMPS & CONTAIN LEAK: Start all electric and manual bilge pumps immediately; attempt emergency hull breach plugging.",
      "BROADCAST MAYDAY ON VHF CH 16: Transmit 'MAYDAY MAYDAY MAYDAY', state vessel name, exact GPS coordinates, souls aboard, and nature of emergency.",
      "PREPARE GRAB BAG & LIFE RAFT: Keep flares, fresh water, handheld VHF radio, and EPIRB ready. Deploy life raft if water ingress is uncontrollable.",
      "STAY WITH VESSEL HULL: Remain aboard or alongside the boat. The vessel is far more visible to incoming search and rescue craft.",
      "COLD WATER SURVIVAL: If in water, huddle in Heat Escape Lessening Posture (H.E.L.P.) to protect vital organs against hypothermia.",
    ];
  }

  const categoryKey = resolveDistressCategoryKey(rawCategoryTitle, answer.survival_advice?.category_key, answer.final_english_response);
  const categoryTitle = translateSurvivalCategory(categoryKey, rawCategoryTitle, lang);

  const overlayPayload: DistressOverlayData = {
    isOpen: true,
    queryId: answer.query_id,
    language: lang,
    mrccContact: answer.mrcc_contact,
    targetAuthority: answer.target_authority,
    survivalAdvice: answer.survival_advice,
    survivalSuggestions: answer.survival_suggestions,
    position: answer.user_location,
    rawText: answer.final_english_response,
  };

  return (
    <div className={`flex flex-col gap-4 rounded-2xl border-2 border-red-500/80 bg-red-950/20 p-4 sm:p-5 shadow-xl ${fontClass}`}>
      {/* Emergency Header with Button to Launch Fullscreen Red Alert */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-red-500/30 pb-3.5">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-xl bg-red-600 text-white shadow-md shadow-red-600/40 animate-pulse">
            <ShieldAlert className="size-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-red-500 animate-ping" />
              <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-red-400">
                {tDistress(lang, "distress_registered")}
              </span>
            </div>
            <h3 className="text-sm sm:text-base font-bold text-white tracking-tight">
              {tDistress(lang, "authorities_dispatched")}
            </h3>
          </div>
        </div>

        {onOpenOverlay && (
          <button
            type="button"
            onClick={() => onOpenOverlay(overlayPayload)}
            className="flex items-center gap-1.5 rounded-xl border-2 border-red-500 bg-red-600/90 px-3.5 py-2 text-xs font-bold text-white shadow-lg shadow-red-600/30 hover:bg-red-500 active:scale-95 transition-all"
          >
            <Maximize2 className="size-3.5" />
            <span>{tDistress(lang, "open_red_alert")}</span>
          </button>
        )}
      </div>

      {/* Dispatched Authorities Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Coast Guard MRCC */}
        <div className="rounded-xl border border-red-500/40 bg-black/40 p-3.5 text-xs text-white">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase font-bold text-red-300">
              {tDistress(lang, "coordinating_rescue_centre")}
            </span>
            <span className="rounded bg-red-500/20 px-2 py-0.5 font-mono text-[10px] font-bold text-red-200 border border-red-500/30">
              {tDistress(lang, "vhf_channel_16")}
            </span>
          </div>
          <p className="mt-1 font-bold text-sm text-white">
            {translateAuthorityName(mrcc?.primary?.name, lang)}
          </p>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <a
              href={`tel:${mrccPhone}`}
              className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-500 shadow transition-colors"
            >
              <Phone className="size-3" />
              <span>{tDistress(lang, "call", { phone: mrccPhone })}</span>
            </a>
            <a
              href="tel:1554"
              className="inline-flex items-center gap-1 rounded-lg border border-red-400/50 bg-white/5 px-2.5 py-1.5 text-xs font-medium text-red-200 hover:bg-white/10"
            >
              <span>{tDistress(lang, "toll_free_1554")}</span>
            </a>
          </div>
        </div>

        {/* Coastal Authority */}
        <div className="rounded-xl border border-red-500/40 bg-black/40 p-3.5 text-xs text-white">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase font-bold text-red-300">
              {tDistress(lang, "local_authority_alerted")}
            </span>
            <span className="rounded bg-red-500/20 px-2 py-0.5 font-mono text-[10px] font-bold text-red-200 border border-red-500/30">
              {tDistress(lang, "active")}
            </span>
          </div>
          <p className="mt-1 font-bold text-sm text-white">{translatedAuthName}</p>
          <p className="mt-0.5 text-[11px] text-red-200/80">{translatedAuthUnit}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <a
              href={`tel:${authPhone}`}
              className="inline-flex items-center gap-1.5 rounded-lg bg-red-700/80 border border-red-500/60 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-600 transition-colors"
            >
              <Phone className="size-3" />
              <span>{tDistress(lang, "call_authority", { phone: authPhone })}</span>
            </a>
          </div>
        </div>
      </div>

      {/* CRITICAL SURVIVAL ACTIONS WHILE AUTHORITIES REACH YOU */}
      <div className="rounded-xl border border-red-500/50 bg-black/50 p-4">
        <div className="flex items-center justify-between border-b border-red-500/30 pb-2.5 mb-3">
          <div className="flex items-center gap-2">
            <LifeBuoy className="size-4 text-red-400 animate-spin" style={{ animationDuration: "10s" }} />
            <div>
              <h4 className="text-xs sm:text-sm font-black uppercase tracking-wide text-white">
                {tDistress(lang, "critical_actions_heading")}
              </h4>
              <p className="text-[11px] text-red-200 font-medium">
                {tDistress(lang, "category_subhead", { category: categoryTitle })}
              </p>
            </div>
          </div>
          <span className="rounded-full bg-red-600/40 border border-red-400 px-2 py-0.5 text-[10px] font-mono font-bold text-white">
            {tDistress(lang, "steps_count", { count: steps.length })}
          </span>
        </div>

        <div className="space-y-2">
          {steps.map((step, idx) => {
            const translatedItem = translateSurvivalStep(step, idx, categoryKey, lang);

            return (
              <div
                key={idx}
                className="flex items-start gap-3 rounded-lg border border-red-500/30 bg-red-950/40 p-2.5 text-left text-xs text-white"
              >
                <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-red-600 font-bold text-xs text-white">
                  {idx + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-bold text-red-100 uppercase text-xs">
                    {translatedItem.title}
                  </p>
                  <p className="mt-0.5 text-xs text-red-200/90 leading-relaxed font-normal">
                    {translatedItem.details}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Simulation note and action row */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-red-500/20 text-[11px] text-red-300/80">
        <p>{tDistress(lang, "simulated_note")}</p>
        <div className="-ml-2">{actions}</div>
      </div>
    </div>
  );
}
