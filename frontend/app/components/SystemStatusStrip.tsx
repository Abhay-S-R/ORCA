"use client";

// SIH finale P0 #3 — disclose live vs. fallback vs. simulated in the product
// itself, next to the persona selector, so a judge finds this before they
// find the gap on their own. Same click-to-toggle popover pattern as
// SourceChip's ProvenancePopover, reused rather than inventing a second one.
import { useEffect, useRef, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { API_BASE } from "../lib/apiBase";
import { ProvenanceLegend } from "./Provenance";

type Feature = { feature: string; status: "live" | "fallback" | "simulated"; detail: string };

const DOT_CLASS: Record<Feature["status"], string> = {
  live: "bg-go",
  fallback: "bg-caution",
  simulated: "bg-data-limited",
};

export function SystemStatusStrip() {
  const [features, setFeatures] = useState<Feature[] | null>(null);
  const [open, setOpen] = useState(false);
  const stripRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/system-status`)
      .then((r) => r.json())
      .then((data) => !cancelled && setFeatures(data.features ?? []))
      .catch(() => !cancelled && setFeatures([]));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (stripRef.current && !stripRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  if (!features || features.length === 0) return null;
  const liveCount = features.filter((f) => f.status === "live").length;

  return (
    <span ref={stripRef} className="relative hidden sm:inline-flex">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-sm border border-hairline px-1.5 py-0.5 text-ink-dim transition-colors hover:border-hairline-strong hover:text-ink-muted"
        title="What's live vs. fallback vs. simulated"
      >
        <ShieldCheck className="size-3" aria-hidden="true" />
        <span className="text-[10px] font-medium tracking-wide uppercase">
          {liveCount} of {features.length} live
        </span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="System status"
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
          className="glass absolute top-full right-0 z-50 mt-1.5 w-80 rounded-md p-3 text-xs shadow-2xl shadow-black/50"
        >
          <p className="font-semibold text-ink">What&apos;s live right now</p>
          <ul className="mt-2 space-y-2">
            {features.map((f) => (
              <li key={f.feature} className="flex items-start gap-2">
                <span aria-hidden="true" className={`mt-1 size-1.5 shrink-0 rounded-full ${DOT_CLASS[f.status]}`} />
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-ink-muted">
                    <span className="font-medium text-ink">{f.feature}</span>
                    <span className="text-[10px] uppercase tracking-wide text-ink-dim">{f.status}</span>
                  </p>
                  <p className="text-ink-dim">{f.detail}</p>
                </div>
              </li>
            ))}
          </ul>

          {/* P4.6 — a second, orthogonal axis from the list above: not
              whether a feature is live, but where a number on screen came
              from. Same popover, since a status bar has no room to spare
              for a second control. */}
          <p className="mt-3 border-t border-hairline pt-2 font-semibold text-ink">Data provenance</p>
          <ProvenanceLegend className="mt-2" />
        </div>
      )}
    </span>
  );
}
