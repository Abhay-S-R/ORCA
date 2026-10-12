"use client";

// The bezel's top edge: high-precision maritime bridge telemetry console strip.
// Displays institutional affiliation (ISRO & INCOIS), coverage status, IST chronometer,
// language selector and account dropdown.
import { useEffect, useState } from "react";
import { LanguageSelector } from "./LanguageSelector";
import { Clock } from "lucide-react";
import { AccountMenu } from "./AccountMenu";

export function StatusBar() {
  return (
    <header className="relative z-40 flex h-10 shrink-0 items-center justify-between border-b border-hairline bg-shelf-1/70 px-4 text-[11px] backdrop-blur-md">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2.5">
          <span className="text-[13px] sm:text-sm font-extrabold tracking-wider text-ink shrink-0">SAGAR SARATHI</span>

          {/* Official Partner Data Feeds: ISRO, INCOIS, IMD (Transparent PNGs, no white background, images alone) */}
          <div className="flex items-center gap-2 pl-1">
            <div
              className="flex h-6 sm:h-7 items-center justify-center transition-transform hover:scale-110 cursor-pointer"
              title="ISRO · Indian Space Research Organisation"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/assets/isro.png"
                alt="ISRO"
                className="h-full w-auto object-contain select-none"
                draggable={false}
              />
            </div>

            <div
              className="flex h-6 sm:h-7 items-center justify-center transition-transform hover:scale-110 cursor-pointer"
              title="INCOIS · Indian National Centre for Ocean Information Services"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/assets/incois.png"
                alt="INCOIS"
                className="h-full w-auto object-contain select-none"
                draggable={false}
              />
            </div>

            <div
              className="flex h-6 sm:h-7 items-center justify-center transition-transform hover:scale-110 cursor-pointer"
              title="IMD · India Meteorological Department"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/assets/imd.png"
                alt="IMD"
                className="h-full w-auto object-contain select-none"
                draggable={false}
              />
            </div>
          </div>
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
      className="hidden sm:flex items-center gap-1.5 text-ink-muted"
      data-readout
      title="Current Indian Standard Time (IST)"
    >
      <Clock className="size-3 text-ocean-cyan/80" aria-hidden="true" />
      <span className="font-mono text-ink font-semibold">{timeStr}</span>
    </div>
  );
}
