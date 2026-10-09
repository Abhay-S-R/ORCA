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

export function VesselChip({
  auth,
  vesselClass,
  variant = "chip",
}: {
  auth: AuthState;
  vesselClass?: string | null;
  // "icon": a round ship button for the left of the composer pill (the place ChatGPT keeps its "+"), so the vessel
  // that drives the verdict stays one tap away without a chip floating above the input.
  variant?: "chip" | "icon";
}) {
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
  const unset = !vesselClass;

  return (
    <div ref={ref} className="relative inline-flex">
      {variant === "icon" ? (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={pending}
          aria-expanded={open}
          aria-haspopup="menu"
          aria-label={unset ? "Set your vessel" : `Vessel: ${label}. Change`}
          title={unset ? "Vessel not set: the small fishing boat limits are used. Tap to set yours." : `Vessel: ${label}`}
          className="relative grid size-10 shrink-0 place-items-center rounded-full text-ink-dim transition-colors hover:bg-shelf-2 hover:text-accent disabled:opacity-50"
        >
          <Ship className="size-[18px]" aria-hidden="true" />
          {unset && <span className="absolute top-2 right-2 size-1.5 rounded-full bg-caution" aria-hidden="true" />}
        </button>
      ) : (
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
      )}

      {open && (
        <div
          role="menu"
          aria-label="Choose vessel class"
          className="glass absolute bottom-full left-0 z-30 mb-1.5 w-56 rounded-md p-1.5 text-xs shadow-2xl shadow-black/50"
        >
          <p className="px-2 pt-1 pb-1.5 text-[11px] text-ink-dim">
            {unset ? "Vessel not set: the small fishing boat limits are used." : "Your vessel"}
          </p>
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
