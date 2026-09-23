"use client";

// P4.3 (`R-UX-1`) — the greeting carries the forecast. Replaces the static
// heading that read the same at 04:00 and 16:00 for every persona.
//
// Signed out, or signed in with no home port on file: degrades to time of
// day only — never an invented position (principle 1). Signed in with a
// home port: a real cheap-check verdict for that position, so the line
// carries a confidence tier and provenance the same as any other number on
// screen, because it *is* a verdict, not decoration.
import { useEffect, useState } from "react";
import { confidenceClass, confidenceLabel, type ConfidenceTier, type Verdict } from "./Badge";
import { ProvenanceBadge } from "./Provenance";
import { API_BASE } from "../lib/apiBase";

type QuickConditions = {
  go_no_go: Verdict;
  reason: string;
  wave_height_m: number | null;
  wind_speed_ms: number | null;
  confidence: ConfidenceTier;
};

const VERDICT_CLASS: Record<Verdict, string> = {
  GO: "text-go",
  CAUTION: "text-caution",
  NO_GO: "text-no-go",
};

function timeOfDayGreeting(d: Date): string {
  // Fixed to IST (UTC+5:30) — the product's one timezone, same convention
  // SourceChip's timestamps use, never the visitor's local clock.
  const istHour = (d.getUTCHours() + 5 + Math.floor((d.getUTCMinutes() + 30) / 60)) % 24;
  if (istHour < 5) return "Good night";
  if (istHour < 12) return "Good morning";
  if (istHour < 17) return "Good afternoon";
  return "Good evening";
}

export function useGreeting(homePort: { lat: number; lon: number } | null | undefined, homePortName?: string | null) {
  const [now] = useState(() => new Date());
  const [conditions, setConditions] = useState<QuickConditions | null>(null);

  useEffect(() => {
    if (!homePort) return;
    const controller = new AbortController();
    fetch(`${API_BASE}/api/quick-conditions?lat=${homePort.lat}&lon=${homePort.lon}`, {
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => data && setConditions(data))
      .catch(() => {});
    return () => controller.abort();
  }, [homePort]);

  return { greeting: timeOfDayGreeting(now), conditions, placeName: homePortName ?? null };
}

export function Greeting({
  homePort,
  homePortName,
  fallback,
}: {
  homePort: { lat: number; lon: number } | null | undefined;
  homePortName?: string | null;
  // National-picture line for signed-out / no-home-port visitors — never a
  // guessed position.
  fallback: string;
}) {
  const { greeting, conditions, placeName } = useGreeting(homePort, homePortName);

  if (!homePort || !conditions || conditions.wave_height_m == null) {
    return (
      <p className="text-sm sm:text-base leading-relaxed text-ink-muted">
        {greeting}. {fallback}
      </p>
    );
  }

  return (
    <p className="flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1 text-sm sm:text-base leading-relaxed text-ink-muted">
      <span>
        {greeting}. Seas off {placeName ?? "your home port"} are {conditions.wave_height_m.toFixed(1)} m — looks{" "}
        <span className={`font-semibold ${VERDICT_CLASS[conditions.go_no_go]}`}>
          {conditions.go_no_go.replace("_", " ")}
        </span>
        .
      </span>
      <span className={confidenceClass(conditions.confidence)}>{confidenceLabel(conditions.confidence)}</span>
      <ProvenanceBadge tier="DERIVED" />
    </p>
  );
}
