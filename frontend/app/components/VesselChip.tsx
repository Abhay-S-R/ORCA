"use client";

// P4.1 — the vessel selector `/safety` had, carried onto `/ask` as an editable
// chip above the composer, so the vessel driving the verdict is visible and
// changeable in place rather than living only inside a one-time setup screen
// or a conversational prompt the user has to wait to be asked. Writes through
// the same two endpoints `ProfilePrompt`'s conversational vessel question
// already uses — one profile, one way to change it.
import { useEffect, useRef, useState } from "react";
import { Ship, ChevronDown } from "lucide-react";
import { authFetch, invalidateProfile, type AuthState } from "../lib/auth";

const VESSEL_LABELS: Record<string, string> = {
  small_fishing: "Small fishing boat",
  mechanized_trawler: "Mechanized trawler",
  cargo_vessel: "Cargo vessel",
};

export function VesselChip({ auth, vesselClass }: { auth: AuthState; vesselClass?: string | null }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  // Anonymous users have no profile to write this to — `/ask` keeps their
  // exact existing path (plan principle: "optional means optional").
  if (auth.status !== "signed_in") return null;

  async function choose(vesselClassValue: string) {
    setPending(true);
    try {
      const res = await authFetch("/api/vessels", {
        method: "POST",
        body: JSON.stringify({ vessel_class: vesselClassValue }),
      });
      if (res.ok) {
        const vessel = await res.json();
        await authFetch("/api/profile/active-vessel", {
          method: "PUT",
          body: JSON.stringify({ vessel_id: vessel.id }),
        });
        invalidateProfile();
      }
    } catch {
      /* best-effort — the chip just keeps showing the previous value */
    } finally {
      setPending(false);
      setOpen(false);
    }
  }

  const label = vesselClass ? (VESSEL_LABELS[vesselClass] ?? vesselClass) : "Vessel not set";

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={pending}
        aria-expanded={open}
        title="The vessel class driving your safety threshold"
        className="inline-flex items-center gap-1.5 rounded-full border border-hairline/80 bg-shelf-1/80 px-3 py-1 text-xs font-medium text-ink-dim transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
      >
        <Ship className="size-3" aria-hidden="true" />
        {label}
        <ChevronDown className="size-3" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Choose vessel class"
          className="glass absolute bottom-full left-0 z-30 mb-1.5 w-56 rounded-md p-1.5 text-xs shadow-2xl shadow-black/50"
        >
          {Object.entries(VESSEL_LABELS).map(([vc, l]) => (
            <button
              key={vc}
              type="button"
              role="menuitem"
              disabled={pending}
              onClick={() => void choose(vc)}
              className={`block w-full rounded px-2 py-1.5 text-left hover:bg-shelf-2 disabled:opacity-50 ${
                vc === vesselClass ? "font-semibold text-accent" : "text-ink-muted"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
