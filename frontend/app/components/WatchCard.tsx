"use client";

// One subscription row on /watches. Design-system only: Card + Badge +
// Readout + the shared button skin. Severity/state never colour-only — the
// enabled state is a text token AND the toggle position.
import { useState } from "react";
import { Bell, BellOff, Trash2 } from "lucide-react";
import { Badge } from "./Badge";
import { Readout, ReadoutGrid } from "./Readout";
import { deleteWatch, updateWatch, watchHistory, type OrcaNotification, type Watch } from "../lib/watches";

const TYPE_LABEL: Record<string, string> = {
  weather: "Weather",
  wave_height: "Wave height",
  lightning: "Lightning",
  cyclone: "Cyclone",
  geofence_approach: "Boundary approach",
  pfz_shift: "Fishing-zone shift",
};

export function WatchCard({ watch, onChange }: { watch: Watch; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<OrcaNotification[] | null>(null);

  async function toggle() {
    setBusy(true);
    try {
      await updateWatch(watch.id, {
        watch_type: watch.watch_type,
        lat: watch.lat,
        lon: watch.lon,
        radius_km: watch.radius_km,
        thresholds: watch.thresholds,
        channels: watch.channels,
        enabled: !watch.enabled,
      });
      onChange();
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteWatch(watch.id);
      onChange();
    } finally {
      setBusy(false);
    }
  }

  async function loadHistory() {
    setHistory(await watchHistory(watch.id));
  }

  const thresholdEntries = Object.entries(watch.thresholds ?? {});

  return (
    <section className="rounded-md border border-hairline bg-shelf-1/70 p-4">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
            {TYPE_LABEL[watch.watch_type] ?? watch.watch_type}
            <Badge tone={watch.enabled ? "go" : "neutral"}>{watch.enabled ? "Active" : "Paused"}</Badge>
          </h3>
          <p className="mt-0.5 text-[11px] text-ink-dim">
            Channels: {(watch.channels ?? []).join(", ") || "in_app"}
          </p>
        </div>
        <div className="flex gap-1.5">
          <button
            type="button"
            onClick={toggle}
            disabled={busy}
            aria-label={watch.enabled ? "Pause this watch" : "Resume this watch"}
            className="rounded-sm border border-hairline p-1.5 text-ink-muted hover:border-hairline-strong hover:text-ink disabled:opacity-50"
          >
            {watch.enabled ? <Bell className="size-4" aria-hidden="true" /> : <BellOff className="size-4" aria-hidden="true" />}
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={busy}
            aria-label="Delete this watch"
            className="rounded-sm border border-hairline p-1.5 text-ink-muted hover:border-no-go/50 hover:text-no-go disabled:opacity-50"
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </button>
        </div>
      </header>

      <ReadoutGrid cols={3}>
        <Readout
          label="Location"
          value={watch.lat != null && watch.lon != null ? `${watch.lat.toFixed(3)}, ${watch.lon.toFixed(3)}` : "area"}
        />
        <Readout label="Radius" value={watch.radius_km ?? "—"} unit={watch.radius_km ? "km" : undefined} />
        <Readout
          label="Last fired"
          value={watch.last_fired_at ? new Date(watch.last_fired_at).toLocaleDateString("en-GB", { timeZone: "UTC" }) : "never"}
        />
      </ReadoutGrid>

      {thresholdEntries.length > 0 && (
        <dl className="mt-3 flex flex-wrap gap-2 text-[11px]">
          {thresholdEntries.map(([k, v]) => (
            <div key={k} className="rounded-sm border border-hairline bg-shelf-2/50 px-2 py-1">
              <dt className="inline text-ink-dim">{k}</dt> <dd className="inline" data-readout>{v}</dd>
            </div>
          ))}
        </dl>
      )}

      <button
        type="button"
        onClick={loadHistory}
        className="mt-3 text-[11px] text-accent underline"
        aria-expanded={history !== null}
      >
        {history === null ? "Show alert history" : `${history.length} alert(s)`}
      </button>

      {history !== null && (
        <ul className="mt-2 flex flex-col gap-1.5">
          {history.length === 0 && <li className="text-[11px] text-ink-dim">No alerts have fired for this watch.</li>}
          {history.map((n) => (
            <li key={n.id} className="rounded-sm border border-hairline bg-shelf-1/60 p-2 text-[11px]">
              <p className="font-medium text-ink">{n.title}</p>
              <p className="text-ink-muted">{n.body}</p>
              <p className="mt-0.5 text-ink-dim" data-readout>
                {new Date(n.created_at).toLocaleString("en-GB", { timeZone: "UTC" })} UTC
                {n.status !== "sent" && <span className="ml-2 text-caution">SIMULATED</span>}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
