"use client";

// P6.8 (orca_final §23) — the Cyclone Gaja historical replay surface. The
// backend (`orca/replay/gaja.py`, `GET /api/replay/gaja`) already existed
// with its own tests; this is the UI it never had. Every row here is a real
// `evaluate_marine_safety()` call against real IBTrACS/ERA5 fields — nothing
// on this page is scripted, including the verdict colour sequence.
import { useState } from "react";
import { AlertTriangle, Loader2, Play } from "lucide-react";
import { Badge, verdictTone, type Verdict } from "../components/Badge";
import { Button } from "../components/Button";
import { ErrorState } from "../components/States";
import { API_BASE } from "../lib/apiBase";

type CascadeFrame = {
  timestamp: string;
  track_wind_kts: number | null;
  wind_speed_kmh: number;
  wave_height_m: number | null;
  cyclone_alert: string | null;
  go_no_go: Verdict;
  status: string;
  reason: string;
};

type GajaPayload = {
  storm: { name: string; year: number; landfall: string; source: string; source_url: string };
  hazard_cascade: CascadeFrame[];
  provenance_class: string;
};

function warningHours(cascade: CascadeFrame[]): number | null {
  const firstNoGo = cascade.find((c) => c.go_no_go === "NO_GO");
  if (!firstNoGo) return null;
  const peak = cascade.reduce((best, c) => ((c.track_wind_kts ?? 0) > (best.track_wind_kts ?? 0) ? c : best), cascade[0]);
  const hours = (new Date(peak.timestamp.replace(" ", "T") + "Z").getTime() - new Date(firstNoGo.timestamp.replace(" ", "T") + "Z").getTime()) / 3_600_000;
  return Math.round(hours);
}

export function GajaReplay() {
  const [data, setData] = useState<GajaPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function load() {
    setLoading(true);
    setError(false);
    try {
      const res = await fetch(`${API_BASE}/api/replay/gaja`);
      if (!res.ok) throw new Error(String(res.status));
      setData(await res.json());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  if (error) {
    return (
      <ErrorState
        title="Replay data not found"
        body="data/cyclone_gaja/ is not present on this machine — this is a labelled 404, never an invented replay."
        action={
          <Button variant="primary" icon={<Play className="size-3.5" />} onClick={load}>
            Retry
          </Button>
        }
      />
    );
  }

  if (!data) {
    return (
      <Button variant="primary" icon={loading ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />} disabled={loading} onClick={load}>
        Run the replay
      </Button>
    );
  }

  const hours = warningHours(data.hazard_cascade);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
        <Badge tone="neutral">{data.storm.name} · {data.storm.year}</Badge>
        <span>Landfall: {data.storm.landfall}</span>
        <span className="text-ink-dim">— {data.provenance_class}</span>
      </div>

      {hours !== null && (
        <div className="rounded-lg border border-caution/40 bg-caution/10 p-3 text-sm text-caution">
          <AlertTriangle className="mr-1.5 inline size-4" aria-hidden="true" />
          <strong>{hours} hours</strong> of warning between ORCA&apos;s first NO-GO on this track and the storm&apos;s recorded peak
          intensity — a proxy for landfall itself, since the track&apos;s own <code>landfall</code> field is free text, not a
          timestamp. Computed from this run&apos;s own data, not asserted.
        </div>
      )}

      <div className="max-h-96 overflow-y-auto rounded-lg border border-hairline/60">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-shelf-2 text-[10px] uppercase tracking-wide text-ink-dim">
            <tr>
              <th className="px-3 py-2">Time (IST)</th>
              <th className="px-3 py-2">Cyclone alert</th>
              <th className="px-3 py-2">Wind</th>
              <th className="px-3 py-2">Wave height</th>
              <th className="px-3 py-2">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {data.hazard_cascade.map((frame) => {
              const d = new Date(frame.timestamp.includes("Z") ? frame.timestamp : frame.timestamp.replace(" ", "T") + "Z");
              const istLabel = Number.isNaN(d.getTime())
                ? frame.timestamp
                : `${d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false })} IST`;
              return (
                <tr key={frame.timestamp} className="border-t border-hairline/40">
                  <td className="px-3 py-1.5 font-mono">{istLabel}</td>
                  <td className="px-3 py-1.5">{frame.cyclone_alert ?? "—"}</td>
                  <td className="px-3 py-1.5">{frame.wind_speed_kmh.toFixed(1)} km/h</td>
                  {/* Ground Rule 3, rendered: ERA5 masks wave height as NaN at this
                      shallow strait point for the entire event — every row says
                      MISSING, never a smoothed or interpolated number. */}
                  <td className="px-3 py-1.5">{frame.wave_height_m === null ? <span className="text-ink-dim">MISSING</span> : `${frame.wave_height_m.toFixed(2)} m`}</td>
                  <td className="px-3 py-1.5">
                    <Badge tone={verdictTone(frame.go_no_go)}>{frame.go_no_go.replace("_", " ")}</Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
