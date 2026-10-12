"use client";

// One subscription row on /watches. Design-system only: Card + Badge +
// Readout + the shared button skin. Supports all 10 official ORCA languages.
import { useEffect, useState } from "react";
import { Bell, BellOff, Trash2 } from "lucide-react";
import { Badge, type BadgeTone } from "./Badge";
import { Readout, ReadoutGrid } from "./Readout";
import { deleteWatch, updateWatch, watchHistory, type OrcaNotification, type Watch } from "../lib/watches";
import { useAuth } from "../lib/auth";
import { resolveWatchLocation } from "../lib/ports";
import { useWatchesT } from "../watches/translations";

const GEOFENCE_BANDS: { name: string; cut: string; tone: BadgeTone }[] = [
  { name: "Advisory", cut: "12–6 nm", tone: "accent" },
  { name: "Watch", cut: "6–3 nm", tone: "cyan" },
  { name: "Warning", cut: "3–1 nm", tone: "caution" },
  { name: "Critical", cut: "≤1 nm", tone: "no-go" },
];

function bandTone(band: string | undefined): BadgeTone {
  if (band === "CRITICAL") return "no-go";
  if (band === "WARNING") return "caution";
  if (band === "WATCH") return "cyan";
  if (band === "ADVISORY") return "accent";
  return "neutral";
}

const DEFAULT_ALL_THRESHOLDS: Record<string, number> = {
  wave_height_m: 2.5,
  wind_kt: 25,
  wind_gust_kt: 32,
  current_kt: 2.2,
  visibility_nm: 3.0,
  lightning_km: 15,
};

export function WatchCard({ watch, onChange }: { watch: Watch; onChange: () => void }) {
  const { t, watchType, portLocation, title: tTitle, body: tBody, language } = useWatchesT();
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<OrcaNotification[] | null>(null);
  const [showHistory, setShowHistory] = useState(true);

  useEffect(() => {
    let active = true;
    watchHistory(watch.id)
      .then((data) => {
        if (active) setHistory(data);
      })
      .catch(() => {
        if (active) setHistory([]);
      });
    return () => {
      active = false;
    };
  }, [watch.id, watch.last_fired_at]);

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

  async function toggleHistory() {
    if (!showHistory && history === null) {
      try {
        const data = await watchHistory(watch.id);
        setHistory(data);
      } catch {
        setHistory([]);
      }
    }
    setShowHistory((v) => !v);
  }

  const baseThresholds = watch.watch_type === "all" ? DEFAULT_ALL_THRESHOLDS : {};
  const mergedThresholds = { ...baseThresholds, ...(watch.thresholds ?? {}) };
  const thresholdEntries = Object.entries(mergedThresholds);

  const auth = useAuth();
  const locationInfo = resolveWatchLocation(
    watch.lat,
    watch.lon,
    auth.profile?.home_port,
    auth.profile?.home_port_name
  );

  const translatedChannels = (watch.channels ?? []).map((ch) => t(ch)).join(", ") || t("in_app");

  return (
    <section className="rounded-md border border-hairline bg-shelf-1/70 p-4">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
            {watchType(watch.watch_type)}
            <Badge tone={watch.enabled ? "go" : "neutral"}>
              {watch.enabled ? t("Active") : t("Paused")}
            </Badge>
          </h3>
          <p className="mt-0.5 text-[11px] text-ink-dim">
            {t("Channels:")} {translatedChannels}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={toggle}
            disabled={busy}
            aria-label={watch.enabled ? t("Pause this watch") : t("Resume this watch")}
            className="rounded-sm border border-hairline p-1.5 text-ink-muted hover:border-hairline-strong hover:text-ink disabled:opacity-50"
          >
            {watch.enabled ? <Bell className="size-4" aria-hidden="true" /> : <BellOff className="size-4" aria-hidden="true" />}
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={busy}
            aria-label={t("Delete this watch")}
            className="rounded-sm border border-hairline p-1.5 text-ink-muted hover:border-no-go/50 hover:text-no-go disabled:opacity-50"
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </button>
        </div>
      </header>

      <ReadoutGrid cols={3}>
        <Readout
          label={t("Location")}
          value={portLocation(locationInfo.portName)}
          hint={locationInfo.coords}
        />
        <Readout label={t("Radius")} value={watch.radius_km ?? "—"} unit={watch.radius_km ? t("km") : undefined} />
        <Readout
          label={t("Last fired")}
          value={
            watch.last_fired_at
              ? new Date(watch.last_fired_at).toLocaleDateString(language === "en" ? "en-IN" : `${language}-IN`, { timeZone: "Asia/Kolkata" })
              : t("never")
          }
        />
      </ReadoutGrid>

      {watch.watch_type === "geofence_approach" && (
        <div className="mt-3 rounded-lg border border-hairline/60 bg-shelf-2/30 p-2.5">
          <p className="mb-1.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
            {t("Fires on entering — or clearing — any band")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {GEOFENCE_BANDS.map((b) => (
              <Badge key={b.name} tone={b.tone}>
                {t(b.name)} <span className="font-normal opacity-80">{b.cut}</span>
              </Badge>
            ))}
          </div>
        </div>
      )}

      {thresholdEntries.length > 0 && (
        <dl className="mt-3 flex flex-wrap gap-2 text-[11px]">
          {thresholdEntries.map(([k, v]) => (
            <div key={k} className="rounded-sm border border-hairline bg-shelf-2/50 px-2 py-1">
              <dt className="inline text-ink-dim">{t(k)}</dt> <dd className="inline font-semibold ml-1 text-ink" data-readout>{v}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="mt-3 flex items-center justify-between">
        <button
          type="button"
          onClick={toggleHistory}
          className="text-[11px] text-accent underline cursor-pointer"
          aria-expanded={showHistory}
        >
          {showHistory ? t("Hide alert history") : t("Show alert history")}
        </button>
      </div>

      {showHistory && (
        <ul className="mt-2 flex flex-col gap-1.5">
          {history === null ? (
            <li className="text-[11px] text-ink-dim">{t("Loading alerts...")}</li>
          ) : history.length === 0 ? (
            <li className="text-[11px] text-ink-dim">{t("No alerts have fired for this watch.")}</li>
          ) : (
            history.map((n) => {
              const snapshot = (n.rendered_payload as { snapshot?: { band?: string } } | undefined)?.snapshot;
              return (
                <li key={n.id} className="rounded-sm border border-hairline bg-shelf-1/60 p-2 text-[11px]">
                  <p className="flex items-center gap-1.5 font-medium text-ink">
                    {tTitle(n.title)}
                    {snapshot?.band && <Badge tone={bandTone(snapshot.band)}>{t(snapshot.band)}</Badge>}
                  </p>
                  <p className="text-ink-muted">{tBody(n.body)}</p>
                  <p className="mt-0.5 text-ink-dim" data-readout>
                    {new Date(n.created_at).toLocaleString(language === "en" ? "en-IN" : `${language}-IN`, { timeZone: "Asia/Kolkata" })} IST
                    {n.status !== "sent" && <span className="ml-2 text-caution font-semibold">{t("SIMULATED")}</span>}
                  </p>
                </li>
              );
            })
          )}
        </ul>
      )}
    </section>
  );
}
