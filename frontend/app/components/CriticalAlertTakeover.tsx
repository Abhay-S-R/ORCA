"use client";

// P4.12 (orca_final §6.3, §11.5) — the ≤1 nm boundary band and a cyclone Red
// take the full screen on ANY route: a shared component in the app shell,
// not a page. Repeats the spoken alert until acknowledged, keeps SOS
// visible, traps focus. The Warning band (3-1 nm) stays a persistent banner
// elsewhere (already rendered inline on the answer card) — this is only the
// hard-block band, so it never fires on the common case.
import { useEffect, useRef } from "react";
import { AlertOctagon } from "lucide-react";
import Link from "next/link";
import { useCriticalAlert } from "../lib/criticalAlert";

const REPEAT_MS = 12_000;

export function CriticalAlertTakeover() {
  const { condition, acknowledge } = useCriticalAlert();
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!condition || typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const message =
      condition.kind === "boundary"
        ? `Warning. Maritime boundary breach imminent. ${
            condition.distanceNm != null ? `${condition.distanceNm.toFixed(1)} nautical miles.` : ""
          } Turn back now.`
        : "Warning. Cyclone red alert. Return to port immediately.";
    const speak = () => {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(message));
    };
    speak();
    const id = setInterval(speak, REPEAT_MS);
    return () => {
      clearInterval(id);
      window.speechSynthesis.cancel();
    };
  }, [condition]);

  useEffect(() => {
    if (condition) dialogRef.current?.focus();
  }, [condition]);

  if (!condition) return null;

  const title = condition.kind === "boundary" ? "Imminent Boundary or MPA Breach" : "Cyclone Red Alert";

  return (
    <div
      ref={dialogRef}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="critical-alert-title"
      aria-live="assertive"
      tabIndex={-1}
      onKeyDown={(e) => {
        // Focus trap: this is the only interactive surface while it is up.
        if (e.key === "Tab") e.preventDefault();
      }}
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-5 bg-no-go p-6 text-center text-on-accent"
    >
      <AlertOctagon className="size-16" aria-hidden="true" />
      <h1 id="critical-alert-title" className="text-2xl font-bold tracking-tight">
        {title}
      </h1>
      {condition.kind === "boundary" && (
        <p className="text-lg">
          {condition.distanceNm != null
            ? `${condition.distanceNm.toFixed(2)} nm from the boundary.`
            : "Distance unavailable."}{" "}
          Turn back toward open water now.
        </p>
      )}
      {condition.kind === "cyclone" && <p className="text-lg">Return to port immediately. Do not proceed to sea.</p>}
      {/* Reciprocal heading and time-to-boundary are P5.6 additions to this
          same component — Sentinel's cheap check has no boundary bearing
          today, so this never claims one it does not have. */}
      <p className="max-w-md text-sm text-on-accent/80">
        A precise heading back to clear water is not yet computed on this build — steer away from your last
        heading and consult your chart.
      </p>
      <div className="mt-2 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="tel:1554"
          className="rounded-full border border-on-accent bg-on-accent/10 px-5 py-2.5 text-sm font-semibold hover:bg-on-accent/20"
        >
          Call MRCC · 1554
        </Link>
        <button
          type="button"
          onClick={acknowledge}
          className="rounded-full border border-on-accent px-5 py-2.5 text-sm font-semibold hover:bg-on-accent/10"
        >
          Acknowledge
        </button>
      </div>
    </div>
  );
}
