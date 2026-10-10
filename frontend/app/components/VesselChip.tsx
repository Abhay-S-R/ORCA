"use client";

// P4.1 — the vessel selector `/safety` had, carried onto `/ask` as an editable
// chip / button beside the composer, so the vessel driving the verdict is visible and
// changeable in place. Supports both registered active-vessel switching and
// direct class selection.
import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Loader2, Ship } from "lucide-react";
import { authFetch, invalidateProfile, type AuthState } from "../lib/auth";

type VesselOption = {
  key: string;
  label: string;
  description: string;
  dbClass: string;
};

const VESSEL_OPTIONS: VesselOption[] = [
  {
    key: "small_fishing",
    label: "Small fishing boat",
    description: "Catamaran, Fibreglass, OBM (<10m)",
    dbClass: "fibreglass",
  },
  {
    key: "mechanized_trawler",
    label: "Mechanized trawler",
    description: "Trawler, Inboard diesel (>10m)",
    dbClass: "trawler",
  },
  {
    key: "cargo_vessel",
    label: "Cargo vessel",
    description: "Commercial / Merchant freight",
    dbClass: "cargo",
  },
];

const CANONICAL_LABELS: Record<string, string> = {
  small_fishing: "Small fishing boat",
  mechanized_trawler: "Mechanized trawler",
  cargo_vessel: "Cargo vessel",
  catamaran: "Catamaran",
  fibreglass: "Fibreglass boat",
  mechanised: "Mechanised boat",
  trawler: "Trawler",
  cargo: "Cargo vessel",
};

// Map DB classes back to canonical key for highlighting
function toCanonicalKey(c: string | null | undefined): string | null {
  if (!c) return null;
  if (c === "catamaran" || c === "fibreglass" || c === "mechanised" || c === "small_fishing") return "small_fishing";
  if (c === "trawler" || c === "mechanized_trawler") return "mechanized_trawler";
  if (c === "cargo" || c === "cargo_vessel") return "cargo_vessel";
  return c;
}

type RegisteredVessel = {
  id: string;
  name: string | null;
  vessel_class: string;
};

export function VesselChip({
  auth,
  vesselClass,
  onVesselChange,
  variant = "chip",
}: {
  auth: AuthState;
  vesselClass?: string | null;
  onVesselChange?: (vesselClass: string) => void;
  // "icon": round button for composer pill, "chip": capsule pill
  variant?: "chip" | "icon";
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [userVessels, setUserVessels] = useState<RegisteredVessel[]>([]);
  const [activeVesselClass, setActiveVesselClass] = useState<string | null>(null);
  const [localChoice, setLocalChoice] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  // Fetch registered vessels for signed-in user
  useEffect(() => {
    if (auth.status !== "signed_in") return;
    let cancelled = false;
    authFetch("/api/vessels")
      .then((r) => (r.ok ? r.json() : []))
      .then((list: RegisteredVessel[]) => {
        if (!cancelled && Array.isArray(list)) {
          setUserVessels(list);
          const active = list.find((v) => v.id === auth.profile?.active_vessel_id);
          if (active) {
            setActiveVesselClass(active.vessel_class);
          }
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [auth.status, auth.profile?.active_vessel_id]);

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  // Determine current active vessel class:
  // 1. localChoice (user just clicked)
  // 2. vesselClass (prop passed from latest turn or parent)
  // 3. activeVesselClass (from user profile)
  const currentKey = toCanonicalKey(localChoice || vesselClass || activeVesselClass);
  const label = currentKey ? (CANONICAL_LABELS[currentKey] ?? currentKey) : "Vessel not set";
  const unset = !currentKey;

  async function choose(opt: VesselOption) {
    setPending(true);
    setLocalChoice(opt.key);
    onVesselChange?.(opt.key);

    try {
      if (auth.status === "signed_in") {
        // If user already has a vessel matching this class, make it active
        const existing = userVessels.find(
          (v) => toCanonicalKey(v.vessel_class) === opt.key
        );

        if (existing) {
          const res = await authFetch("/api/profile/active-vessel", {
            method: "PUT",
            body: JSON.stringify({ vessel_id: existing.id }),
          });
          if (res.ok) {
            invalidateProfile();
          }
        } else {
          // Register a new vessel and activate it
          const res = await authFetch("/api/vessels", {
            method: "POST",
            body: JSON.stringify({
              vessel_class: opt.dbClass,
              name: opt.label,
            }),
          });
          if (res.ok) {
            const created = await res.json();
            await authFetch("/api/profile/active-vessel", {
              method: "PUT",
              body: JSON.stringify({ vessel_id: created.id }),
            });
            invalidateProfile();
            setUserVessels((prev) => [...prev, created]);
          }
        }
      }
    } catch (err) {
      console.error("Failed to update vessel", err);
    } finally {
      setPending(false);
      setOpen(false);
    }
  }

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
          title={unset ? "Vessel not set: tap to select your vessel type." : `Vessel: ${label} (Tap to change)`}
          className={`relative grid size-10 shrink-0 place-items-center rounded-full transition-colors hover:bg-shelf-2 hover:text-accent disabled:opacity-50 ${
            unset ? "text-ink-dim" : "text-ocean-cyan"
          }`}
        >
          {pending ? (
            <Loader2 className="size-[18px] animate-spin text-ocean-cyan" />
          ) : (
            <Ship className="size-[18px]" aria-hidden="true" />
          )}
          {unset && <span className="absolute top-2 right-2 size-2 rounded-full bg-amber-400" aria-hidden="true" />}
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
          {pending ? (
            <Loader2 className="size-3 animate-spin text-ocean-cyan" />
          ) : (
            <Ship className="size-3" aria-hidden="true" />
          )}
          {label}
          <ChevronDown className="size-3" aria-hidden="true" />
        </button>
      )}

      {open && (
        <div
          role="menu"
          aria-label="Choose vessel class"
          className="glass absolute bottom-full left-0 z-30 mb-2 w-72 rounded-xl border border-hairline bg-shelf-1/95 p-2 text-xs shadow-2xl backdrop-blur-md"
        >
          <div className="border-b border-hairline/60 px-2 pt-1 pb-2">
            <p className="font-semibold text-ink">Select Vessel Type</p>
            <p className="text-[11px] text-ink-dim">
              Safety alerts &amp; sea limits adapt to your vessel class.
            </p>
          </div>

          <div className="mt-1 space-y-1">
            {VESSEL_OPTIONS.map((opt) => {
              const isSelected = currentKey === opt.key;
              return (
                <button
                  key={opt.key}
                  type="button"
                  role="menuitem"
                  disabled={pending}
                  onClick={() => void choose(opt)}
                  className={`flex w-full items-start justify-between rounded-lg p-2 text-left transition-colors hover:bg-shelf-2 disabled:opacity-50 ${
                    isSelected ? "bg-ocean-cyan/10 font-semibold text-ocean-cyan" : "text-ink"
                  }`}
                >
                  <div className="flex-1 pr-2">
                    <div className="flex items-center gap-1.5">
                      <span>{opt.label}</span>
                      {isSelected && <Check className="size-3.5 text-ocean-cyan" />}
                    </div>
                    <div className="text-[10.5px] font-normal text-ink-dim">{opt.description}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
