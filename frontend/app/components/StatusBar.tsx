"use client";

// The bezel's top edge: high-precision maritime bridge telemetry console strip.
// Displays coverage status, datalink telemetry, IST chronometer, and active
// persona command station. No fixed coordinates here — the chart's own
// "Your Location" marker (MapView) is the one place a real position ever
// shows, and only once the browser actually grants a GPS fix.
import { useEffect, useState } from "react";
import { Radio } from "lucide-react";
import { SystemStatusStrip } from "./SystemStatusStrip";
import { AccountMenu } from "./AccountMenu";
import { API_BASE } from "../lib/apiBase";

export function StatusBar() {
  return (
    <header className="relative z-40 flex h-10 shrink-0 items-center justify-between border-b border-hairline bg-shelf-1/70 px-4 text-[11px] backdrop-blur-md">
      <div className="flex items-center gap-3.5">
        <div className="flex items-center gap-2">
          <span className="font-bold tracking-wider text-ink">ORCA</span>
          <span className="rounded bg-shelf-3/80 px-1.5 py-0.5 text-[9px] font-mono tracking-widest text-ocean-cyan uppercase border border-ocean-cyan/30">
            ECDIS v2.4
          </span>
        </div>

        <div className="hidden h-3.5 w-px bg-hairline md:block" />

        {/* Coverage status — deliberately no coordinates here; a real
            position only ever appears once the chart's own GPS fix grants. */}
        <div className="hidden items-center gap-2 text-ink-dim md:flex">
          <span className="size-1.5 rounded-full bg-ocean-cyan beacon-pulse" aria-hidden="true" />
          <span className="text-[10px] text-ink-dim tracking-wider uppercase">
            Pan-India Coastal Coverage
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <SystemStatusStrip />
        <div className="hidden h-3.5 w-px bg-hairline sm:block" />
        <DataCurrency />
        <AccountMenu />
      </div>
    </header>
  );
}

type SourceObservation = {
  id: string;
  observed_last_refresh_utc?: string | null;
  observed_age_minutes?: number | null;
};

function humanAge(minutes: number): string {
  if (minutes < 60) return `${minutes} min old`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h old`;
  return `${Math.round(minutes / (60 * 24))} d old`;
}

// P4.2: a wall clock changes no decision. What matters is how current the data
// behind the app is — so this shows the most recently refreshed dataset on disk,
// not the time of day. Never fabricated: with nothing observed yet, it says so.
function DataCurrency() {
  const [state, setState] = useState<"loading" | "unavailable" | { asOf: string; age: number }>(
    "loading",
  );

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/sources`)
      .then((r) => r.json())
      .then((data: { sources?: SourceObservation[] }) => {
        if (cancelled) return;
        const freshest = (data.sources ?? [])
          .filter((s) => s.observed_last_refresh_utc && s.observed_age_minutes != null)
          .sort((a, b) => (a.observed_age_minutes ?? Infinity) - (b.observed_age_minutes ?? Infinity))[0];
        setState(
          freshest
            ? { asOf: freshest.observed_last_refresh_utc as string, age: freshest.observed_age_minutes as number }
            : "unavailable",
        );
      })
      .catch(() => !cancelled && setState("unavailable"));
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "loading") {
    return (
      <div className="flex items-center gap-1.5 text-ink-dim" data-readout>
        <Radio className="size-3 text-ocean-cyan/70 animate-pulse" aria-hidden="true" />
        <span className="text-[10px]">Checking data currency…</span>
      </div>
    );
  }

  if (state === "unavailable") {
    return (
      <div className="flex items-center gap-1.5 text-ink-dim" data-readout>
        <Radio className="size-3 text-data-limited" aria-hidden="true" />
        <span className="text-[10px] uppercase tracking-wide">Data currency unverified</span>
      </div>
    );
  }

  const asOfIst = new Date(state.asOf).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
    hour12: false,
  });

  return (
    <div
      className="flex items-center gap-1.5 text-ink-muted"
      data-readout
      title="Freshest dataset ORCA holds on disk right now"
    >
      <Radio className="size-3 text-ocean-cyan/70" aria-hidden="true" />
      <span className="font-mono text-ink">Data as of {asOfIst} IST</span>
      <span className="text-[9px] font-semibold text-ink-dim tracking-wider">
        · {humanAge(state.age)}
      </span>
    </div>
  );
}
