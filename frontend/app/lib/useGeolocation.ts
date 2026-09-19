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
  // Always "loading" on the first render: the server has no `navigator`, so
  // deciding availability there rendered "unavailable" on the server and
  // "loading" in the browser — a hydration mismatch on every page with a map.
  // Availability is decided after mount instead.
  const [status, setStatus] = useState<GeoStatus>("loading");

  useEffect(() => {
    if (status !== "loading") return;
    if (!navigator.geolocation) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- navigator only exists after mount
      setStatus("unavailable");
      return;
    }
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
