"use client";

// P3.10 (orca_final §15.3, PS §1 "tailored") — named places a signed-in (or
// signed-out — localStorage, same pattern as ../ask/chatStore.ts) user
// bookmarks, one tap above the composer for today's verdict at that spot.
// Distinct from `users.home_port` (exactly one, set at setup) and a
// Sentinel watch (P5.17 promotes one of these; it does not replace this).
import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { authFetch, getToken } from "../lib/auth";
import { useT } from "../i18n/useT";

export type SavedLocation = { id: string; name: string; lat: number; lon: number };

const LOCAL_KEY = "orca.savedLocations";

function readLocal(): SavedLocation[] {
  try {
    const raw = window.localStorage.getItem(LOCAL_KEY);
    return raw ? (JSON.parse(raw) as SavedLocation[]) : [];
  } catch {
    return [];
  }
}

function writeLocal(locations: SavedLocation[]) {
  try {
    window.localStorage.setItem(LOCAL_KEY, JSON.stringify(locations));
  } catch {
    /* private mode / storage disabled — the chip still worked this session */
  }
}

export function SavedLocationChips({
  onSelect,
  addFrom,
  hideAdd = false,
}: {
  onSelect: (loc: SavedLocation) => void;
  // The position "+" saves — the last answered turn's resolved location.
  // `null` before anything has been answered yet (nothing to bookmark).
  addFrom: { lat: number; lon: number } | null;
  hideAdd?: boolean;
}) {
  const t = useT();
  const [locations, setLocations] = useState<SavedLocation[]>([]);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    const token = getToken();
    // Reading getToken() needs the client mount, same hydration-safe
    // pattern as persona/context.tsx and language/context.tsx.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSignedIn(!!token);
    if (token) {
      authFetch("/api/locations")
        .then((r) => (r.ok ? (r.json() as Promise<SavedLocation[]>) : []))
        .then(setLocations)
        .catch(() => {});
    } else {
      setLocations(readLocal());
    }
  }, []);

  async function add() {
    const trimmed = name.trim();
    if (!addFrom || !trimmed) return;
    if (signedIn) {
      const res = await authFetch("/api/locations", {
        method: "POST",
        body: JSON.stringify({ name: trimmed, lat: addFrom.lat, lon: addFrom.lon }),
      }).catch(() => null);
      if (res?.ok) {
        const created = (await res.json()) as SavedLocation;
        setLocations((prev) => [...prev, created]);
      }
    } else {
      const loc: SavedLocation = { id: crypto.randomUUID(), name: trimmed, lat: addFrom.lat, lon: addFrom.lon };
      setLocations((prev) => {
        const next = [...prev, loc];
        writeLocal(next);
        return next;
      });
    }
    setName("");
    setAdding(false);
  }

  async function remove(id: string) {
    if (signedIn) await authFetch(`/api/locations/${id}`, { method: "DELETE" }).catch(() => {});
    setLocations((prev) => {
      const next = prev.filter((l) => l.id !== id);
      if (!signedIn) writeLocal(next);
      return next;
    });
  }

  if (locations.length === 0 && (!addFrom || hideAdd)) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {locations.map((loc) => (
        <span
          key={loc.id}
          className="group inline-flex items-center gap-1 rounded-full border border-hairline/80 bg-shelf-1/70 py-1 pr-1 pl-3 text-xs text-ink-dim"
        >
          <button type="button" onClick={() => onSelect(loc)} className="hover:text-accent">
            {loc.name}
          </button>
          <button
            type="button"
            onClick={() => void remove(loc.id)}
            aria-label={`Remove ${loc.name}`}
            className="rounded-full p-0.5 opacity-0 group-hover:opacity-100 hover:bg-shelf-2"
          >
            <X className="size-3" aria-hidden="true" />
          </button>
        </span>
      ))}
      {!hideAdd &&
        addFrom &&
        (adding ? (
          <span className="inline-flex items-center gap-1">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void add();
                if (e.key === "Escape") setAdding(false);
              }}
              placeholder={t("savedLocations.namePrompt")}
              className="w-32 rounded-full border border-hairline bg-shelf-0 px-2.5 py-1 text-xs text-ink"
            />
            <button type="button" onClick={() => void add()} className="text-xs font-semibold text-accent">
              {t("common.save")}
            </button>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-hairline/80 px-2.5 py-1 text-xs text-ink-dim hover:border-accent hover:text-accent"
          >
            <Plus className="size-3" aria-hidden="true" /> {t("savedLocations.add")}
          </button>
        ))}
    </div>
  );
}
