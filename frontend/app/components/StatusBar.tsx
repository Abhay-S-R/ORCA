"use client";

// The bezel's top edge. On a bridge console the strip above the chart carries
// the things that are true regardless of what you are looking at: where you
// are, what time it is, and whether the feed is live. Same job here.
import { useEffect, useState } from "react";
import { PersonaSelector } from "../persona/PersonaSelector";

export function StatusBar() {
  return (
    <header className="flex h-9 shrink-0 items-center gap-4 border-b border-hairline bg-shelf-1/40 px-3 text-[11px]">
      <span className="font-semibold tracking-wide text-ink">ORCA</span>
      <span className="hidden text-ink-dim sm:inline">South Tamil Nadu · Gulf of Mannar</span>
      <div className="flex-1" />
      <FeedStatus />
      <Clock />
      <PersonaSelector />
    </header>
  );
}

function Clock() {
  const [now, setNow] = useState<string | null>(null);

  // Rendered null-then-value rather than from `new Date()` at first render:
  // the server has a different clock than the client and hydration would
  // mismatch. The dash is what the server and the first client pass agree on.
  useEffect(() => {
    const tick = () =>
      setNow(
        new Date().toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "UTC",
        }),
      );
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <span data-readout className="text-ink-muted" title="Coordinated Universal Time">
      {now ?? "--:--"} UTC
    </span>
  );
}

function FeedStatus() {
  // Placeholder until Phase 2 wires real staleness off the degraded-response
  // contract. Deliberately not green-by-default: a status light that is
  // always green teaches people to stop reading it.
  return (
    <span className="hidden items-center gap-1.5 text-ink-dim sm:inline-flex">
      <span aria-hidden="true" className="size-1.5 rounded-full bg-go" />
      Feeds live
    </span>
  );
}
