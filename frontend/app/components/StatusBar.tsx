"use client";

// The bezel's top edge: high-precision maritime bridge telemetry console strip.
// Displays live geospatial fix (Thoothukudi / Gulf of Mannar), datalink telemetry,
// UTC chronometer, and active persona command station.
import { useEffect, useState } from "react";
import { PersonaSelector } from "../persona/PersonaSelector";
import { Radio, Satellite } from "lucide-react";

export function StatusBar() {
  return (
    <header className="flex h-10 shrink-0 items-center justify-between border-b border-hairline bg-shelf-1/70 px-4 text-[11px] backdrop-blur-md">
      <div className="flex items-center gap-3.5">
        <div className="flex items-center gap-2">
          <span className="font-bold tracking-wider text-ink">ORCA</span>
          <span className="rounded bg-shelf-3/80 px-1.5 py-0.5 text-[9px] font-mono tracking-widest text-ocean-cyan uppercase border border-ocean-cyan/30">
            ECDIS v2.4
          </span>
        </div>

        <div className="hidden h-3.5 w-px bg-hairline md:block" />

        {/* Live Marine Coordinates Fix */}
        <div className="hidden items-center gap-2 text-ink-dim md:flex">
          <span className="size-1.5 rounded-full bg-ocean-cyan beacon-pulse" aria-hidden="true" />
          <span data-readout className="font-mono text-ink-muted">
            08°48.0&apos;N · 078°09.0&apos;E
          </span>
          <span className="text-[10px] text-ink-dim tracking-wider uppercase">
            Gulf of Mannar
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <FeedStatus />
        <div className="hidden h-3.5 w-px bg-hairline sm:block" />
        <Clock />
        <PersonaSelector />
      </div>
    </header>
  );
}

function Clock() {
  const [now, setNow] = useState<string | null>(null);

  useEffect(() => {
    const tick = () =>
      setNow(
        new Date().toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          timeZone: "UTC",
        }),
      );
    tick();
    const id = setInterval(tick, 1_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex items-center gap-1.5 text-ink-muted" title="Coordinated Universal Time">
      <Radio className="size-3 text-ocean-cyan/70" aria-hidden="true" />
      <span data-readout className="font-mono text-ink">
        {now ?? "--:--:--"}
      </span>
      <span className="text-[9px] font-semibold text-ink-dim tracking-wider">UTC</span>
    </div>
  );
}

function FeedStatus() {
  return (
    <div className="hidden items-center gap-2 text-ink-dim sm:inline-flex">
      <Satellite className="size-3 text-go" aria-hidden="true" />
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden="true" className="size-1.5 rounded-full bg-go shadow-sm shadow-go/50" />
        <span className="text-[10px] font-medium tracking-wide uppercase text-ink-muted">
          Feeds Live
        </span>
      </span>
    </div>
  );
}
