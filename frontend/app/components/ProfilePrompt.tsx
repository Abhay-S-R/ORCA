"use client";

// P3.4 (`R-UX-6`) — the conversational half of the setup wizard: "you're
// asking about tomorrow morning — what boat are you taking?" Answering
// writes straight to the account (via the same PUT/POST endpoints the
// wizard and the profile pages use) — no separate save step, no form.
// Dismissing just hides it for this turn; the backend re-offers it on the
// next question that would use the same missing field, since nothing was
// answered.
import { useState } from "react";
import { X } from "lucide-react";
import { authFetch, invalidateProfile } from "../lib/auth";
import { fontClassForLanguage } from "../i18n/languages";
import { useT } from "../i18n/useT";
import type { FinalResponse } from "../ask/useAskThread";

type Prompt = NonNullable<FinalResponse["profile_prompt"]>;

export function ProfilePrompt({
  prompt,
  location,
  language,
}: {
  prompt: Prompt;
  // The CURRENT answer's own resolved position — what "save this as home
  // port" actually saves. Never the regional default (the backend only
  // sends this prompt when the position was real — see profile_prompts.py).
  location: { lat: number; lon: number; place_name?: string | null } | null | undefined;
  language?: string | null;
}) {
  const t = useT();
  const [dismissed, setDismissed] = useState(false);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  if (dismissed || done) return null;

  async function chooseVessel(vesselClass: string) {
    setPending(true);
    try {
      const res = await authFetch("/api/vessels", {
        method: "POST",
        body: JSON.stringify({ vessel_class: vesselClass }),
      });
      if (res.ok) {
        const vessel = await res.json();
        await authFetch("/api/profile/active-vessel", {
          method: "PUT",
          body: JSON.stringify({ vessel_id: vessel.id }),
        });
        invalidateProfile();
        setDone(true);
      }
    } catch {
      /* best-effort — the question can be asked again next time */
    } finally {
      setPending(false);
    }
  }

  async function confirmHomePort() {
    if (!location) return;
    setPending(true);
    try {
      const res = await authFetch("/api/profile/home-port", {
        method: "PUT",
        body: JSON.stringify({ lat: location.lat, lon: location.lon, name: location.place_name ?? null }),
      });
      if (res.ok) {
        invalidateProfile();
        setDone(true);
      }
    } catch {
      /* best-effort */
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mt-3 flex items-start gap-2 rounded-xl border border-accent/40 bg-accent/5 p-3 text-xs">
      <div className="min-w-0 flex-1">
        <p className={`text-ink ${fontClassForLanguage(language)}`}>{prompt.question}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {prompt.input_type === "choice" &&
            prompt.options?.map((opt) => (
              <button
                key={opt.value}
                type="button"
                disabled={pending}
                onClick={() => void chooseVessel(opt.value)}
                className="rounded-full border border-hairline/80 bg-shelf-1/80 px-3 py-1 text-xs font-medium text-ink-dim hover:border-accent hover:text-accent disabled:opacity-50"
              >
                {opt.label}
              </button>
            ))}
          {prompt.input_type === "confirm" && (
            <>
              <button
                type="button"
                disabled={pending || !location}
                onClick={() => void confirmHomePort()}
                className="rounded-full border border-accent/60 bg-accent/10 px-3 py-1 text-xs font-semibold text-accent hover:bg-accent/20 disabled:opacity-50"
              >
                {t("profilePrompt.yesSaveIt")}
              </button>
              <button
                type="button"
                disabled={pending}
                onClick={() => setDismissed(true)}
                className="rounded-full border border-hairline/80 px-3 py-1 text-xs text-ink-dim hover:text-ink"
              >
                {t("profilePrompt.notNow")}
              </button>
            </>
          )}
        </div>
      </div>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => setDismissed(true)}
        className="shrink-0 rounded-full p-1 text-ink-dim hover:bg-shelf-2 hover:text-ink"
      >
        <X className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
