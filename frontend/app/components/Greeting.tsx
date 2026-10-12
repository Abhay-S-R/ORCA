"use client";

// Greeting component for the Ask landing view.
// Shows a stable, creative summary of conditions at the user's home port
// (calm / moderate / rough, wave height, good to venture out) followed by an
// invitation to ask questions. Caches conditions across page navigations to
// prevent flickering or displaying different messages when returning to the page.
import { useEffect, useState } from "react";
import type { Verdict } from "./Badge";
import { API_BASE } from "../lib/apiBase";
import { useT } from "../i18n/useT";
import { useLanguage } from "../language/context";
import { translatePortName } from "../i18n/entities";

type QuickConditions = {
  go_no_go: Verdict;
  reason: string;
  wave_height_m: number | null;
  wind_speed_ms: number | null;
};

const VERDICT_COLOR: Record<Verdict, string> = {
  GO: "text-go font-medium",
  CAUTION: "text-caution font-medium",
  NO_GO: "text-no-go font-medium",
};

function timeOfDayGreetingKey(d: Date): string {
  // Fixed to IST (UTC+5:30) — product-wide standard
  const istHour = (d.getUTCHours() + 5 + Math.floor((d.getUTCMinutes() + 30) / 60)) % 24;
  if (istHour < 5) return "greeting.night";
  if (istHour < 12) return "greeting.morning";
  if (istHour < 17) return "greeting.afternoon";
  return "greeting.evening";
}

// Module-level in-memory cache to guarantee instant, zero-flicker re-renders
// when navigating across tabs or pages.
const conditionsCache = new Map<string, QuickConditions>();

function getCacheKey(homePort: { lat: number; lon: number } | null | undefined): string | null {
  if (!homePort) return null;
  return `${homePort.lat.toFixed(2)},${homePort.lon.toFixed(2)}`;
}

export function useGreeting(
  homePort: { lat: number; lon: number } | null | undefined,
  homePortName?: string | null
) {
  const [now] = useState(() => new Date());
  const cacheKey = getCacheKey(homePort);

  // Synchronously seed from cache if available so there is no layout jump or text flicker
  const [conditions, setConditions] = useState<QuickConditions | null>(() => {
    if (!cacheKey) return null;
    return conditionsCache.get(cacheKey) ?? null;
  });

  useEffect(() => {
    if (!homePort || !cacheKey) return;

    // If already in cache, conditions is already seeded; still fetch in background to keep fresh
    const controller = new AbortController();
    fetch(`${API_BASE}/api/quick-conditions?lat=${homePort.lat}&lon=${homePort.lon}`, {
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: QuickConditions | null) => {
        if (data && data.wave_height_m != null) {
          conditionsCache.set(cacheKey, data);
          setConditions(data);
        }
      })
      .catch(() => {});

    return () => controller.abort();
  }, [homePort, cacheKey]);

  return {
    greetingKey: timeOfDayGreetingKey(now),
    conditions,
    placeName: homePortName ?? null,
  };
}

export function Greeting({
  homePort,
  homePortName,
}: {
  homePort: { lat: number; lon: number } | null | undefined;
  homePortName?: string | null;
  fallback?: string;
}) {
  const t = useT();
  const { language } = useLanguage();
  const { greetingKey, conditions, placeName } = useGreeting(homePort, homePortName);
  const greeting = t(greetingKey);

  // If user has a registered home port with conditions
  if (homePort && conditions && conditions.wave_height_m != null) {
    const wave = conditions.wave_height_m;
    const waveStr = wave.toFixed(1);
    const rawPort = placeName || "your home port";
    const port = translatePortName(rawPort, language);

    if (conditions.go_no_go === "GO") {
      const seaFeel = wave <= 0.8 ? t("greeting.calm") : t("greeting.favourable");
      return (
        <p className="text-sm sm:text-base leading-relaxed text-ink-muted text-center max-w-2xl mx-auto">
          {greeting}. {t("greeting.seasOff")} <strong className="font-semibold text-ink">{port}</strong> {seaFeel} ({waveStr} m) —{" "}
          <span className={VERDICT_COLOR.GO}>{t("greeting.goVerdict")}</span>. {t("greeting.goPrompt")}
        </p>
      );
    }

    if (conditions.go_no_go === "CAUTION") {
      return (
        <p className="text-sm sm:text-base leading-relaxed text-ink-muted text-center max-w-2xl mx-auto">
          {greeting}. {t("greeting.seasOff")} <strong className="font-semibold text-ink">{port}</strong> {t("greeting.moderate")} ({waveStr} m) —{" "}
          <span className={VERDICT_COLOR.CAUTION}>{t("greeting.cautionVerdict")}</span>. {t("greeting.cautionPrompt")}
        </p>
      );
    }

    // NO_GO
    return (
      <p className="text-sm sm:text-base leading-relaxed text-ink-muted text-center max-w-2xl mx-auto">
        {greeting}. {t("greeting.seasOff")} <strong className="font-semibold text-ink">{port}</strong> {t("greeting.rough")} ({waveStr} m) —{" "}
        <span className={VERDICT_COLOR.NO_GO}>{t("greeting.noGoVerdict")}</span>. {t("greeting.noGoPrompt")}
      </p>
    );
  }

  // If home port is set but conditions are still loading on first-ever mount
  if (homePort && placeName) {
    const port = translatePortName(placeName, language);
    return (
      <p className="text-sm sm:text-base leading-relaxed text-ink-muted text-center max-w-2xl mx-auto">
        {greeting}. {t("greeting.seasOff")} <strong className="font-semibold text-ink">{port}</strong> {t("greeting.monitored")}
      </p>
    );
  }

  // Signed out / guest / no home port set
  return (
    <p className="text-sm sm:text-base leading-relaxed text-ink-muted text-center max-w-2xl mx-auto">
      {greeting}. {t("greeting.defaultSignedOut")}
    </p>
  );
}
