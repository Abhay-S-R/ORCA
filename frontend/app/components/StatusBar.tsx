"use client";

// The bezel's top edge: high-precision maritime bridge telemetry console strip.
// Displays coverage status, IST chronometer, language and account.
// No fixed coordinates here — the chart's own
// "Your Location" marker (MapView) is the one place a real position ever
// shows, and only once the browser actually grants a GPS fix.
import { useEffect, useState } from "react";
import { LanguageSelector } from "./LanguageSelector";
import { Clock } from "lucide-react";
import { AccountMenu } from "./AccountMenu";

export function StatusBar() {
  return (
    <header className="relative z-40 flex h-10 shrink-0 items-center justify-between border-b border-hairline bg-shelf-1/70 px-4 text-[11px] backdrop-blur-md">
      <div className="flex items-center gap-3.5">
        <div className="flex items-center gap-2">
          <span className="font-bold tracking-wider text-ink">SAGAR SARATHI</span>
          <span className="rounded bg-shelf-3/80 px-1.5 py-0.5 text-[9px] font-mono tracking-widest text-ocean-cyan uppercase border border-ocean-cyan/30">
            ECDIS v2.4
          </span>
        </div>

        <div className="hidden h-3.5 w-px bg-hairline md:block" />

        {/* Coverage status */}
        <div className="hidden items-center gap-2 text-ink-dim md:flex">
          <span className="size-1.5 rounded-full bg-ocean-cyan beacon-pulse" aria-hidden="true" />
          <span className="text-[10px] text-ink-dim tracking-wider uppercase">
            Pan-India Coastal Coverage
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <ClockIST />
        <LanguageSelector />
        <AccountMenu />
      </div>
    </header>
  );
}

function ClockIST() {
  const [timeStr, setTimeStr] = useState<string>("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const formatted = now.toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Kolkata",
        hour12: false,
      });
      setTimeStr(`${formatted} IST`);
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  if (!timeStr) return null;

  return (
    <div
      className="flex items-center gap-1.5 text-ink-muted"
      data-readout
      title="Current Indian Standard Time (IST)"
    >
      <Clock className="size-3 text-ocean-cyan/80" aria-hidden="true" />
      <span className="font-mono text-ink font-semibold">{timeStr}</span>
    </div>
  );
}
