"use client";

// Watches (§4.2 `/watches`) — the Sentinel subscriber surface. A watch
// belongs to someone, so this needs identity; the fisherman variant is
// simplified, not crippled ("watch my home port" is one tap with sane
// default thresholds; the full editor is behind "Advanced").
import { useCallback, useEffect, useState } from "react";
import { Eye } from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { Field, inputClass } from "../components/Field";
import { Button } from "../components/Button";
import { WatchCard } from "../components/WatchCard";
import { usePersona } from "../persona/context";
import { getToken, signIn, signOut } from "../lib/auth";
import { createWatch, listWatches, type Watch, type WatchType } from "../lib/watches";

const HOME_PORT = { lat: 8.8, lon: 78.14 }; // Thoothukudi pilot reference — TODO(D1): user's registered home port
const DEFAULT_WAVE_THRESHOLD = 2.5;

export default function WatchesPage() {
  const { persona } = usePersona();
  const [signedIn, setSignedIn] = useState(false);
  const [watches, setWatches] = useState<Watch[] | null>(null);
  const [error, setError] = useState(false);
  const [advanced, setAdvanced] = useState(false);

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
    await createWatch({
      watch_type: "wave_height",
      lat: HOME_PORT.lat,
      lon: HOME_PORT.lon,
      radius_km: 10,
      thresholds: { wave_height_m: DEFAULT_WAVE_THRESHOLD },
      channels: ["in_app"],
    });
    load();
  }

  if (!signedIn) return <SignInGate />;

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="Watches"
        lede="Standing alerts on a place you care about — Sentinel checks it on a schedule and tells you when conditions cross your thresholds."
        action={
          <Button variant="ghost" onClick={() => signOut()}>
            Sign out
          </Button>
        }
      />

      <Panel title="Add a watch" className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={quickAddHomePort}>
            Watch my home port
          </Button>
          <span className="text-[11px] text-ink-dim">
            Wave height over {DEFAULT_WAVE_THRESHOLD} m within 10 km, in-app alerts.
          </span>
          <button
            type="button"
            className="ml-auto text-[11px] text-accent underline"
            aria-expanded={advanced}
            onClick={() => setAdvanced((v) => !v)}
          >
            {advanced ? "Hide advanced" : "Advanced"}
          </button>
        </div>
        {advanced && <AdvancedWatchForm onCreated={load} />}
      </Panel>

      {error && <ErrorState title="Could not load your watches" body="The server did not answer. Try reloading." />}
      {!error && watches === null && <Skeleton className="h-40" />}
      {!error && watches !== null && watches.length === 0 && (
        <EmptyState
          icon={<Eye className="size-6" />}
          title="No watches yet"
          body="Add your home port above, or use Advanced to watch a specific point with your own thresholds."
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
        Viewing as <span className="text-ink-muted">{persona.replace(/_/g, " ")}</span>. SMS / IVR delivery is not built —
        those channels are shown as SIMULATED with the exact message that would be sent.
      </p>
    </PageBody>
  );
}

function AdvancedWatchForm({ onCreated }: { onCreated: () => void }) {
  const [type, setType] = useState<WatchType>("wave_height");
  const [lat, setLat] = useState(String(HOME_PORT.lat));
  const [lon, setLon] = useState(String(HOME_PORT.lon));
  const [radius, setRadius] = useState("10");
  const [wave, setWave] = useState(String(DEFAULT_WAVE_THRESHOLD));
  const [wind, setWind] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const thresholds: Record<string, number> = {};
      if (wave) thresholds.wave_height_m = Number(wave);
      if (wind) thresholds.wind_kt = Number(wind);
      await createWatch({
        watch_type: type,
        lat: Number(lat),
        lon: Number(lon),
        radius_km: radius ? Number(radius) : null,
        thresholds,
        channels: ["in_app"],
      });
      onCreated();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-4 border-t border-hairline pt-4">
      <Field label="Watch type">
        {(id) => (
          <select id={id} className={inputClass} value={type} onChange={(e) => setType(e.target.value as WatchType)}>
            <option value="wave_height">Wave height</option>
            <option value="weather">Weather (any worsening)</option>
            <option value="lightning">Lightning</option>
            <option value="cyclone">Cyclone</option>
            <option value="geofence_approach">Boundary approach</option>
            <option value="pfz_shift">Fishing-zone shift</option>
          </select>
        )}
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Latitude">{(id) => <input id={id} className={inputClass} value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" />}</Field>
        <Field label="Longitude">{(id) => <input id={id} className={inputClass} value={lon} onChange={(e) => setLon(e.target.value)} inputMode="decimal" />}</Field>
        <Field label="Radius (km)">{(id) => <input id={id} className={inputClass} value={radius} onChange={(e) => setRadius(e.target.value)} inputMode="decimal" />}</Field>
        <Field label="Wave threshold (m)">{(id) => <input id={id} className={inputClass} value={wave} onChange={(e) => setWave(e.target.value)} inputMode="decimal" />}</Field>
        <Field label="Wind threshold (kt)" hint="optional">{(id) => <input id={id} className={inputClass} value={wind} onChange={(e) => setWind(e.target.value)} inputMode="decimal" />}</Field>
      </div>
      <Button type="submit" variant="primary" disabled={busy}>
        {busy ? "Adding…" : "Add watch"}
      </Button>
    </form>
  );
}

function SignInGate() {
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
      <PageHeader title="Watches" lede="Sign in to set standing alerts on the places you care about." />
      <Panel title="Sign in">
        <form onSubmit={submit}>
          <Field label="Phone or email">
            {(id) => (
              <input id={id} className={inputClass} value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" />
            )}
          </Field>
          <Field label="Password">
            {(id) => (
              <input
                id={id}
                type="password"
                className={inputClass}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            )}
          </Field>
          {failed && (
            <p role="alert" className="mb-2 text-[11px] text-no-go">
              Sign-in failed — check your details and try again.
            </p>
          )}
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Panel>
      <p className="mt-3 text-[11px] text-ink-dim">
        Accounts are created through registration (D1). This surface reuses that identity.
      </p>
    </PageBody>
  );
}
