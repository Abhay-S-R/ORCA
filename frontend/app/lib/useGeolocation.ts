"use client";

// Shared browser geolocation source (item 3 of the ocean/map revamp): the
// chart's "Your Location" marker and the status bar's live fix both read
// from this one hook so there is exactly one permission prompt and one
// place that decides what "no GPS" means, rather than two components each
// guessing.
import { useEffect, useState } from "react";

export type GeoStatus = "loading" | "granted" | "denied" | "unavailable";

export function useGeolocation() {
  const [position, setPosition] = useState<[number, number] | null>(null);
  // Availability is knowable synchronously (no navigator.geolocation ==
  // never going to work), so it's the initial state itself rather than a
  // setState call inside the effect below — the effect only ever sets state
  // from an async callback, never directly in its own body.
  const [status, setStatus] = useState<GeoStatus>(() =>
    typeof navigator !== "undefined" && navigator.geolocation ? "loading" : "unavailable",
  );

  useEffect(() => {
    if (status !== "loading") return;
    let cancelled = false;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (cancelled) return;
        setPosition([pos.coords.longitude, pos.coords.latitude]);
        setStatus("granted");
      },
      () => {
        if (!cancelled) setStatus("denied");
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 },
    );
    return () => {
      cancelled = true;
    };
  }, [status]);

  return { position, status };
}
