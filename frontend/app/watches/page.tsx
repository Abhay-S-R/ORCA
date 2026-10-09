"use client";

// Watches (§4.2 `/watches`) — the Sentinel subscriber surface. A watch
// belongs to someone, so this needs identity; the fisherman variant is
// simplified, not crippled ("watch my home port" is one tap with sane
// default thresholds; the full editor is behind "Advanced").
// P3.12 — all visible strings now sourced from the i18n dictionaries via useT().
// P-HP-1 — "Watch my home port" now reads the user's *registered* home port
// from their profile (auth.useAuth().profile.home_port) instead of the old
// hardcoded Thoothukudi pilot-region coordinates.
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Eye } from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { Field, inputClass } from "../components/Field";
import { PasswordInput } from "../components/PasswordInput";
import { Button } from "../components/Button";
import { WatchCard } from "../components/WatchCard";
import { WatchGeometryPicker } from "../components/WatchGeometryPicker";
import { usePersona } from "../persona/context";
import { getToken, signIn, signOut, useAuth } from "../lib/auth";
import { createWatch, listWatches, type Watch, type WatchType } from "../lib/watches";
import { useT } from "../i18n/useT";

const DEFAULT_WAVE_THRESHOLD = 2.5;

export default function WatchesPage() {
  const { persona } = usePersona();
  const t = useT();
  const auth = useAuth();
  const [signedIn, setSignedIn] = useState(false);
  const [watches, setWatches] = useState<Watch[] | null>(null);
  const [error, setError] = useState(false);
  const [advanced, setAdvanced] = useState(false);

  // Read the user's registered home port from their profile (null until profile
  // loads, or when no home port has been set yet).
  const homePort = auth.status === "signed_in" ? auth.profile?.home_port ?? null : null;
  const homePortName = auth.status === "signed_in" ? auth.profile?.home_port_name ?? null : null;

  const load = useCallback(async () => {
    if (!getToken()) return;
    try {
      const next = await listWatches();
      setWatches(next);
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    const sync = () => setSignedIn(!!getToken());
    sync();
    window.addEventListener("orca:auth", sync);
    return () => window.removeEventListener("orca:auth", sync);
  }, []);

  useEffect(() => {
    if (!signedIn) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- setState happens only in load()'s async continuation, after await
    void load();
  }, [signedIn, load]);

  async function quickAddHomePort() {
    // Use the user's registered home port — never a hardcoded default.
    if (!homePort) return;
    await createWatch({
      watch_type: "wave_height",
      lat: homePort.lat,
      lon: homePort.lon,
      radius_km: 10,
      thresholds: { wave_height_m: DEFAULT_WAVE_THRESHOLD },
      channels: ["in_app"],
      enabled: true,
    });
    load();
  }

  if (!signedIn) return <SignInGate />;

  // The "Watch my home port" button is disabled when no home port is set.
  // We show a nudge linking to /profile so the user knows why.
  const hasHomePort = homePort !== null;

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title={t("watches.title")}
        lede={t("watches.lede")}
        action={
          <Button variant="ghost" onClick={() => signOut()}>
            {t("common.signOut")}
          </Button>
        }
      />

      <Panel title={t("watches.addWatch")} className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={quickAddHomePort} disabled={!hasHomePort}>
            {t("watches.watchHomePort")}
          </Button>
          {hasHomePort ? (
            <span className="text-[11px] text-ink-dim">
              {homePortName ? `${homePortName} — ` : ""}{t("watches.waveDefault")}
            </span>
          ) : (
            <span className="text-[11px] text-ink-dim">
              {t("watches.noHomePortSet")}{" "}
              <Link href="/profile" className="text-accent underline">
                {t("watches.setHomePort")}
              </Link>
            </span>
          )}
          <button
            type="button"
            className="ml-auto text-[11px] text-accent underline"
            aria-expanded={advanced}
            onClick={() => setAdvanced((v) => !v)}
          >
            {advanced ? t("watches.hideAdvanced") : t("watches.advanced")}
          </button>
        </div>
        {advanced && <AdvancedWatchForm onCreated={load} defaultLat={homePort?.lat} defaultLon={homePort?.lon} />}
      </Panel>

      {error && <ErrorState title={t("watches.serverError")} body={t("watches.serverErrorBody")} />}
      {!error && watches === null && <Skeleton className="h-40" />}
      {!error && watches !== null && watches.length === 0 && (
        <EmptyState
          icon={<Eye className="size-6" />}
          title={t("watches.noWatches")}
          body={t("watches.noWatchesBody")}
        />
      )}
      {!error && watches && watches.length > 0 && (
        <div className="flex flex-col gap-3">
          {watches.map((w) => (
            <WatchCard key={w.id} watch={w} onChange={load} />
          ))}
        </div>
      )}

      <p className="mt-4 text-[11px] text-ink-dim">
        {t("common.signOut").charAt(0).toUpperCase()} — <span className="text-ink-muted">{persona.replace(/_/g, " ")}</span>. {t("watches.simulated")}
      </p>
    </PageBody>
  );
}

function AdvancedWatchForm({ onCreated, defaultLat, defaultLon }: { onCreated: () => void; defaultLat?: number; defaultLon?: number }) {
  const t = useT();
  const [type, setType] = useState<WatchType>("wave_height");
  // Pre-fill with the user's home port coordinates when available, otherwise blank.
  const [lat, setLat] = useState(defaultLat !== undefined ? String(defaultLat) : "");
  const [lon, setLon] = useState(defaultLon !== undefined ? String(defaultLon) : "");
  const [radius, setRadius] = useState("10");
  const [wave, setWave] = useState(String(DEFAULT_WAVE_THRESHOLD));
  const [wind, setWind] = useState("");
  const [busy, setBusy] = useState(false);
  // P5.28 — a point-with-radius watch or a drawn area, never both; the DB
  // constraint (`sentinel_has_geometry`) already enforces one geometry.
  const [geometryMode, setGeometryMode] = useState<"point" | "area">("point");
  const [area, setArea] = useState<GeoJSON.Polygon | null>(null);

  // P5.18 — geofence_approach/pfz_shift fire on their own band/advisory
  // logic, never a wave/wind threshold; submitting one anyway left a stray
  // "wave_height_m 2.5" pill on a boundary watch that nothing ever reads.
  const usesThresholds = type !== "geofence_approach" && type !== "pfz_shift";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const thresholds: Record<string, number> = {};
      if (usesThresholds) {
        if (wave) thresholds.wave_height_m = Number(wave);
        if (wind) thresholds.wind_kt = Number(wind);
      }
      await createWatch(
        geometryMode === "area" && area
          ? { watch_type: type, area_geojson: area, thresholds, channels: ["in_app"], enabled: true }
          : { watch_type: type, lat: Number(lat), lon: Number(lon), radius_km: radius ? Number(radius) : null, thresholds, channels: ["in_app"], enabled: true },
      );
      onCreated();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-4 border-t border-hairline pt-4">
      <Field label={t("watches.watchType")}>
        {(id) => (
          <select id={id} className={inputClass} value={type} onChange={(e) => setType(e.target.value as WatchType)}>
            <option value="wave_height">{t("watches.waveHeight")}</option>
            <option value="weather">{t("watches.weather")}</option>
            <option value="lightning">{t("watches.lightning")}</option>
            <option value="cyclone">{t("watches.cyclone")}</option>
            <option value="geofence_approach">{t("watches.boundaryApproach")}</option>
            <option value="pfz_shift">{t("watches.fishingZoneShift")}</option>
          </select>
        )}
      </Field>
      <div className="mb-2 flex items-center gap-2 text-[11px]">
        <span className="text-ink-dim">Geometry:</span>
        <button
          type="button"
          onClick={() => setGeometryMode("point")}
          className={`rounded px-2 py-0.5 ${geometryMode === "point" ? "bg-accent/20 text-accent" : "text-ink-dim underline"}`}
        >
          Point + radius
        </button>
        <button
          type="button"
          onClick={() => setGeometryMode("area")}
          className={`rounded px-2 py-0.5 ${geometryMode === "area" ? "bg-accent/20 text-accent" : "text-ink-dim underline"}`}
        >
          Draw an area
        </button>
      </div>
      <div className="mb-3">
        <WatchGeometryPicker
          mode={geometryMode}
          point={Number.isFinite(Number(lat)) && Number.isFinite(Number(lon)) ? { lat: Number(lat), lon: Number(lon) } : null}
          onPointChange={(clat, clon) => {
            setLat(String(clat));
            setLon(String(clon));
          }}
          area={area}
          onAreaChange={setArea}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        {geometryMode === "point" && (
          <>
            <Field label={t("watches.latitude")}>{(id) => <input id={id} className={inputClass} value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" />}</Field>
            <Field label={t("watches.longitude")}>{(id) => <input id={id} className={inputClass} value={lon} onChange={(e) => setLon(e.target.value)} inputMode="decimal" />}</Field>
            <Field label={t("watches.radius")}>{(id) => <input id={id} className={inputClass} value={radius} onChange={(e) => setRadius(e.target.value)} inputMode="decimal" />}</Field>
          </>
        )}
        {usesThresholds && (
          <>
            <Field label={t("watches.waveThreshold")}>{(id) => <input id={id} className={inputClass} value={wave} onChange={(e) => setWave(e.target.value)} inputMode="decimal" />}</Field>
            <Field label={t("watches.windThreshold")} hint={t("watches.windHint")}>{(id) => <input id={id} className={inputClass} value={wind} onChange={(e) => setWind(e.target.value)} inputMode="decimal" />}</Field>
          </>
        )}
      </div>
      {!usesThresholds && (
        <p className="mb-4 -mt-2 text-[11px] text-ink-dim">
          {type === "geofence_approach" ? t("watches.geofenceHint") : t("watches.pfzShiftHint")}
        </p>
      )}
      <Button type="submit" variant="primary" disabled={busy || (geometryMode === "area" && !area)}>
        {busy ? t("watches.adding") : t("watches.addButton")}
      </Button>
    </form>
  );
}

function SignInGate() {
  const t = useT();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFailed(false);
    const ok = await signIn(identifier.trim(), password);
    setBusy(false);
    if (!ok) setFailed(true);
  }

  return (
    <PageBody className="mx-auto max-w-md">
      <PageHeader title={t("watches.title")} lede={t("watches.signInLede")} />
      <Panel title={t("watches.signInPanel")}>
        <form onSubmit={submit}>
          <Field label={t("watches.phoneOrEmail")}>
            {(id) => (
              <input id={id} className={inputClass} value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" />
            )}
          </Field>
          <Field label={t("watches.password")}>
            {(id) => (
              <PasswordInput
                id={id}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            )}
          </Field>
          {failed && (
            <p role="alert" className="mb-2 text-[11px] text-no-go">
              {t("watches.signInFailed")}
            </p>
          )}
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? t("watches.signingIn") : t("common.signIn")}
          </Button>
        </form>
      </Panel>
      <p className="mt-3 text-[11px] text-ink-dim">
        {t("watches.noAccount")}{" "}
        <Link href="/login?next=/watches" className="font-semibold text-ocean-cyan hover:underline">
          {t("watches.createOne")}
        </Link>{" "}
        {t("watches.sameAccount")}
      </p>
    </PageBody>
  );
}
