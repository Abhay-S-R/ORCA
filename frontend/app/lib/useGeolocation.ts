"use client";

// Shared browser geolocation source (item 3 of the ocean/map revamp): the
// chart's "Your Location" marker and the status bar's live fix both read
// from this one hook so there is exactly one permission prompt and one
// place that decides what "no GPS" means, rather than two components each
// guessing.
import { useEffect, useState } from "react";

export type GeoStatus = "loading" | "granted" | "denied" | "unavailable";

const GEO_STORAGE_KEY = "orca.geoFix";

function readCachedFix(): [number, number] | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(GEO_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      Array.isArray(parsed) &&
      parsed.length === 2 &&
      typeof parsed[0] === "number" &&
      typeof parsed[1] === "number"
    ) {
      return parsed as [number, number];
    }
  } catch {
    /* ignore */
  }
  return null;
}

function writeCachedFix(pos: [number, number]) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(GEO_STORAGE_KEY, JSON.stringify(pos));
  } catch {
    /* ignore */
  }
}

export function useGeolocation() {
  const [position, setPosition] = useState<[number, number] | null>(null);
  const [status, setStatus] = useState<GeoStatus>("loading");

  useEffect(() => {
    // Attempt instant hydrate from sessionStorage so subsequent chats/reloads don't start empty
    const cached = readCachedFix();
    if (cached) {
      setPosition(cached);
      setStatus("granted");
    }

    if (!navigator.geolocation) {
      setStatus("unavailable");
      return;
    }

    let cancelled = false;

    function handleSuccess(pos: GeolocationPosition) {
      if (cancelled) return;
      const coords: [number, number] = [pos.coords.longitude, pos.coords.latitude];
      setPosition(coords);
      setStatus("granted");
      writeCachedFix(coords);
    }

    // Try high accuracy first (5s timeout), falling back to standard accuracy (network/Wi-Fi)
    // if high accuracy times out or is unavailable (critical on laptops/PCs without hardware GPS).
    navigator.geolocation.getCurrentPosition(
      handleSuccess,
      (err) => {
        if (cancelled) return;
        if (err.code === err.TIMEOUT || err.code === err.POSITION_UNAVAILABLE) {
          navigator.geolocation.getCurrentPosition(
            handleSuccess,
            () => {
              if (!cancelled && !cached) setStatus("denied");
            },
            { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
          );
        } else {
          if (!cached) setStatus("denied");
        }
      },
      { enableHighAccuracy: true, timeout: 5_000, maximumAge: 60_000 },
    );

    return () => {
      cancelled = true;
    };
  }, []);

  return { position, status };
}
