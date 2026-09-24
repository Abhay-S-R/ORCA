"use client";

// Profile (P5.22, ADMINISTRATIVE intent row) — the one place an account's
// standing facts live: home port, vessel, quiet hours, language. Every field
// here already had a working API and no screen to reach it from — this is
// that screen, not new backend behaviour.
import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, Anchor, Bell, Check, Globe2, Ship, Sunrise } from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { Field, inputClass } from "../components/Field";
import { Button } from "../components/Button";
import { Badge } from "../components/Badge";
import { Skeleton } from "../components/States";
import { authFetch, invalidateProfile, useAuth, type Profile } from "../lib/auth";
import { LANGUAGES, type LangCode } from "../i18n/languages";
import { PERSONAS } from "../persona/config";
import { useT } from "../i18n/useT";

type Vessel = {
  id: string;
  vessel_class: string;
  name: string | null;
  registration_no: string | null;
  draft_m: number | null;
  length_m: number | null;
  crew_size: number | null;
  cruise_speed_kn: number | null;
  fuel_burn_lph: number | null;
  engine_count: number | null;
};

const VESSEL_CLASS_LABEL: Record<string, string> = {
  catamaran: "Catamaran",
  fibreglass: "Fibreglass boat",
  mechanised: "Mechanised boat",
  trawler: "Trawler",
  cargo: "Cargo vessel",
};

export default function ProfilePage() {
  const auth = useAuth();
  const t = useT();

  // "signed_in" fires before the profile fetch resolves (useAuth's own
  // three-state contract allows `{status: "signed_in", profile: null}` as a
  // real transient) — every panel below seeds its local form state from
  // `profile` exactly once at mount, so mounting them against a still-null
  // profile would freeze quiet hours, home port, etc. at "nothing set"
  // forever. Wait for the real value instead of racing it.
  if (auth.status === "loading" || (auth.status === "signed_in" && auth.profile === null)) {
    return (
      <PageBody className="mx-auto max-w-2xl">
        <Skeleton className="h-10 w-64 mb-6" />
        <Skeleton className="h-40 mb-4" />
        <Skeleton className="h-40" />
      </PageBody>
    );
  }

  if (auth.status === "signed_out") {
    return (
      <PageBody className="mx-auto max-w-md">
        <PageHeader title={t("profile.title")} lede={t("profile.signedOutLede")} />
        <Panel>
          <p className="text-sm text-ink-muted">
            {t("profile.signInPrompt")}{" "}
            <Link href="/login?next=/profile" className="font-semibold text-ocean-cyan hover:underline">
              {t("common.signIn")}
            </Link>
            .
          </p>
        </Panel>
      </PageBody>
    );
  }

  // Keyed by id + a version-ish fingerprint of the fields every panel seeds
  // its local state from, so a save that changes the server value (e.g.
  // `invalidateProfile()` after PUT /quiet-hours) remounts fresh rather than
  // leaving each panel's already-initialized useState stale.
  return <ProfileEditor key={JSON.stringify(auth.profile)} profile={auth.profile} />;
}

function ProfileEditor({ profile }: { profile: Profile | null }) {
  const t = useT();

  return (
    <PageBody className="mx-auto max-w-2xl">
      <PageHeader title={t("profile.title")} lede={t("profile.lede")} />

      <div className="flex flex-col gap-4">
        <AccountPanel profile={profile} />
        <HomePortPanel profile={profile} />
        <VesselPanel profile={profile} />
        <AlertsPanel profile={profile} />
        <LanguagePanel profile={profile} />
      </div>
    </PageBody>
  );
}

// --- Account (read-only identity) -------------------------------------------

function AccountPanel({ profile }: { profile: Profile | null }) {
  const t = useT();
  return (
    <Panel title={t("profile.account")}>
      <ReadoutGrid cols={2}>
        <Readout label={t("profile.name")} value={profile?.display_name ?? "—"} />
        <Readout label={t("profile.signInId")} value={profile?.identifier ?? "—"} />
      </ReadoutGrid>
      {profile && profile.role !== "user" && (
        <p className="mt-3">
          <Badge tone="accent">{profile.role}</Badge>
        </p>
      )}
    </Panel>
  );
}

// --- Home port ---------------------------------------------------------------

function HomePortPanel({ profile }: { profile: Profile | null }) {
  const t = useT();
  const [editing, setEditing] = useState(false);
  const [lat, setLat] = useState(profile?.home_port ? String(profile.home_port.lat) : "");
  const [lon, setLon] = useState(profile?.home_port ? String(profile.home_port.lon) : "");
  const [name, setName] = useState(profile?.home_port_name ?? "");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const latNum = Number(lat);
    const lonNum = Number(lon);
    if (!Number.isFinite(latNum) || !Number.isFinite(lonNum)) return;
    setBusy(true);
    try {
      const res = await authFetch("/api/profile/home-port", {
        method: "PUT",
        body: JSON.stringify({ lat: latNum, lon: lonNum, name: name.trim() || null }),
      });
      if (res.ok) {
        invalidateProfile();
        setEditing(false);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title={t("profile.homePort")}
      action={
        !editing && (
          <button type="button" onClick={() => setEditing(true)} className="text-[11px] font-medium text-accent underline">
            {profile?.home_port ? t("profile.change") : t("profile.setIt")}
          </button>
        )
      }
    >
      {!editing ? (
        profile?.home_port ? (
          <ReadoutGrid cols={3}>
            <Readout label={t("profile.place")} value={profile.home_port_name ?? "—"} />
            <Readout label={t("profile.latitude")} value={profile.home_port.lat.toFixed(4)} />
            <Readout label={t("profile.longitude")} value={profile.home_port.lon.toFixed(4)} />
          </ReadoutGrid>
        ) : (
          <p className="text-sm text-ink-muted">{t("profile.noHomePort")}</p>
        )
      ) : (
        <form onSubmit={save}>
          <Field label={t("profile.place")} hint={t("profile.placeHint")}>
            {(id) => <input id={id} className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("profile.placePlaceholder")} />}
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("profile.latitude")}>
              {(id) => <input id={id} className={inputClass} value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" required />}
            </Field>
            <Field label={t("profile.longitude")}>
              {(id) => <input id={id} className={inputClass} value={lon} onChange={(e) => setLon(e.target.value)} inputMode="decimal" required />}
            </Field>
          </div>
          <div className="flex gap-2">
            <Button type="submit" variant="primary" disabled={busy}>
              {busy ? t("profile.saving") : t("profile.save")}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </form>
      )}
      {saved && (
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-go">
          <Check className="size-3.5" aria-hidden="true" /> {t("profile.savedHomePort")}
        </p>
      )}
    </Panel>
  );
}

// --- Vessel -------------------------------------------------------------------

function VesselPanel({ profile }: { profile: Profile | null }) {
  const t = useT();
  const [vessels, setVessels] = useState<Vessel[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    authFetch("/api/vessels")
      .then((r) => (r.ok ? r.json() : []))
      .then((v) => {
        if (!cancelled) setVessels(v);
      })
      .catch(() => {
        if (!cancelled) setVessels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [profile?.active_vessel_id]);

  async function makeActive(vesselId: string) {
    setBusy(true);
    try {
      await authFetch("/api/profile/active-vessel", { method: "PUT", body: JSON.stringify({ vessel_id: vesselId }) });
      invalidateProfile();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title={t("profile.vessels")}
      action={
        !adding && (
          <button type="button" onClick={() => setAdding(true)} className="text-[11px] font-medium text-accent underline">
            {t("profile.addVessel")}
          </button>
        )
      }
    >
      {vessels === null && <Skeleton className="h-16" />}
      {vessels !== null && vessels.length === 0 && !adding && (
        <p className="text-sm text-ink-muted">{t("profile.noVessels")}</p>
      )}
      {vessels !== null && vessels.length > 0 && (
        <div className="flex flex-col gap-2">
          {vessels.map((v) => {
            const active = v.id === profile?.active_vessel_id;
            return (
              <div
                key={v.id}
                className={`flex items-center justify-between gap-3 rounded-lg border p-3 transition-colors ${
                  active ? "border-ocean-cyan/50 bg-ocean-cyan/5" : "border-hairline/60 bg-shelf-2/30"
                }`}
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <Ship className="size-3.5 shrink-0 text-ink-dim" aria-hidden="true" />
                    {v.name || VESSEL_CLASS_LABEL[v.vessel_class] || v.vessel_class}
                    {active && <Badge tone="cyan">{t("profile.active")}</Badge>}
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-ink-dim">
                    {VESSEL_CLASS_LABEL[v.vessel_class] || v.vessel_class}
                    {v.cruise_speed_kn != null ? ` · ${v.cruise_speed_kn} kn` : ""}
                    {v.fuel_burn_lph != null ? ` · ${v.fuel_burn_lph} L/h` : ""}
                    {v.draft_m != null ? ` · draft ${v.draft_m} m` : ""}
                  </p>
                </div>
                {!active && (
                  <Button variant="ghost" onClick={() => makeActive(v.id)} disabled={busy} className="shrink-0">
                    {t("profile.useThis")}
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}
      {adding && (
        <AddVesselForm
          onDone={(newVessels) => {
            setVessels(newVessels);
            setAdding(false);
          }}
          onCancel={() => setAdding(false)}
        />
      )}
    </Panel>
  );
}

function AddVesselForm({ onDone, onCancel }: { onDone: (v: Vessel[]) => void; onCancel: () => void }) {
  const t = useT();
  const [vesselClass, setVesselClass] = useState("fibreglass");
  const [name, setName] = useState("");
  const [draft, setDraft] = useState("");
  const [cruiseSpeed, setCruiseSpeed] = useState("");
  const [fuelBurn, setFuelBurn] = useState("");
  const [crew, setCrew] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const body: Record<string, unknown> = { vessel_class: vesselClass };
      if (name.trim()) body.name = name.trim();
      if (draft) body.draft_m = Number(draft);
      if (cruiseSpeed) body.cruise_speed_kn = Number(cruiseSpeed);
      if (fuelBurn) body.fuel_burn_lph = Number(fuelBurn);
      if (crew) body.crew_size = Number(crew);
      const res = await authFetch("/api/vessels", { method: "POST", body: JSON.stringify(body) });
      if (res.ok) {
        const created = await res.json();
        await authFetch("/api/profile/active-vessel", { method: "PUT", body: JSON.stringify({ vessel_id: created.id }) });
        invalidateProfile();
        const list = await authFetch("/api/vessels").then((r) => (r.ok ? r.json() : []));
        onDone(list);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 border-t border-hairline pt-3">
      <Field label={t("profile.vesselType")}>
        {(id) => (
          <select id={id} className={inputClass} value={vesselClass} onChange={(e) => setVesselClass(e.target.value)}>
            {Object.entries(VESSEL_CLASS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label={t("profile.vesselName")} hint={t("profile.optional")}>
        {(id) => <input id={id} className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label={t("profile.draft")} hint="m">
          {(id) => <input id={id} className={inputClass} value={draft} onChange={(e) => setDraft(e.target.value)} inputMode="decimal" />}
        </Field>
        <Field label={t("profile.cruiseSpeed")} hint="kn">
          {(id) => <input id={id} className={inputClass} value={cruiseSpeed} onChange={(e) => setCruiseSpeed(e.target.value)} inputMode="decimal" />}
        </Field>
        <Field label={t("profile.fuelBurn")} hint="L/h">
          {(id) => <input id={id} className={inputClass} value={fuelBurn} onChange={(e) => setFuelBurn(e.target.value)} inputMode="decimal" />}
        </Field>
      </div>
      <Field label={t("profile.crewSize")} hint={t("profile.optional")}>
        {(id) => <input id={id} className={inputClass} value={crew} onChange={(e) => setCrew(e.target.value)} inputMode="numeric" />}
      </Field>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? t("profile.saving") : t("profile.addVessel")}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

// --- Alerts: quiet hours (P5.22) ---------------------------------------------

// [start%, width%] segments on a 24h bar; two segments when the window wraps
// past midnight (e.g. 22:00-06:00), one otherwise.
function quietSegments(startMin: number, endMin: number): { left: number; width: number }[] {
  const pct = (m: number) => (m / 1440) * 100;
  if (startMin <= endMin) return [{ left: pct(startMin), width: pct(endMin - startMin) }];
  return [
    { left: pct(startMin), width: pct(1440 - startMin) },
    { left: 0, width: pct(endMin) },
  ];
}

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

function AlertsPanel({ profile }: { profile: Profile | null }) {
  const t = useT();
  const current = profile?.quiet_hours;
  const [enabled, setEnabled] = useState(!!current);
  const [start, setStart] = useState(current?.start ?? "22:00");
  const [end, setEnd] = useState(current?.end ?? "06:00");
  const [tz, setTz] = useState(current?.tz ?? "Asia/Kolkata");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [nowMin, setNowMin] = useState<number | null>(null);

  // R-NEW-16 — pre-dawn departure briefing, a separate save target
  // (PUT /api/profile/typical-departure-hour) from quiet hours above.
  const [briefingEnabled, setBriefingEnabled] = useState(profile?.typical_departure_hour != null);
  const [departureHour, setDepartureHour] = useState(profile?.typical_departure_hour ?? 5);
  const [briefingBusy, setBriefingBusy] = useState(false);
  const [briefingSaved, setBriefingSaved] = useState(false);

  useEffect(() => {
    const tick = () => {
      try {
        const parts = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(new Date());
        const h = Number(parts.find((p) => p.type === "hour")?.value ?? 0);
        const m = Number(parts.find((p) => p.type === "minute")?.value ?? 0);
        setNowMin(h * 60 + m);
      } catch {
        setNowMin(null);
      }
    };
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, [tz]);

  const segments = quietSegments(toMinutes(start), toMinutes(end));
  const inQuietNow =
    nowMin !== null &&
    (toMinutes(start) <= toMinutes(end)
      ? nowMin >= toMinutes(start) && nowMin < toMinutes(end)
      : nowMin >= toMinutes(start) || nowMin < toMinutes(end));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await authFetch("/api/profile/quiet-hours", {
        method: "PUT",
        body: JSON.stringify(enabled ? { start, end, tz } : null),
      });
      if (res.ok) {
        invalidateProfile();
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } finally {
      setBusy(false);
    }
  }

  async function saveBriefing(e: React.FormEvent) {
    e.preventDefault();
    setBriefingBusy(true);
    try {
      const res = await authFetch("/api/profile/typical-departure-hour", {
        method: "PUT",
        body: JSON.stringify(briefingEnabled ? { hour: departureHour } : null),
      });
      if (res.ok) {
        invalidateProfile();
        setBriefingSaved(true);
        setTimeout(() => setBriefingSaved(false), 2000);
      }
    } finally {
      setBriefingBusy(false);
    }
  }

  return (
    <Panel title={t("profile.alerts")}>
      <p className="mb-3 text-sm text-ink-muted">{t("profile.quietHoursExplain")}</p>

      <label className="mb-3 flex items-center gap-2.5 text-sm text-ink">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="size-4 rounded border-hairline accent-ocean-cyan"
        />
        {t("profile.enableQuietHours")}
      </label>

      {enabled && (
        <>
          {/* 24h instrument strip: shaded = quiet window, bright tick = now. */}
          <div className="relative mb-1 h-7 overflow-hidden rounded-md border border-hairline/70 bg-shelf-2/40">
            {[6, 12, 18].map((h) => (
              <span key={h} className="absolute top-0 h-full w-px bg-hairline/50" style={{ left: `${(h / 24) * 100}%` }} />
            ))}
            {segments.map((seg, i) => (
              <span key={i} className="absolute top-0 h-full bg-ocean-cyan/25" style={{ left: `${seg.left}%`, width: `${seg.width}%` }} />
            ))}
            {nowMin !== null && (
              <span
                className="absolute top-0 h-full w-[2px] bg-caution shadow-[0_0_4px_var(--color-caution)]"
                style={{ left: `${(nowMin / 1440) * 100}%` }}
                title={t("profile.nowMarker")}
              />
            )}
          </div>
          <div className="mb-4 flex justify-between text-[10px] font-mono text-ink-dim">
            <span>00:00</span>
            <span>06:00</span>
            <span>12:00</span>
            <span>18:00</span>
            <span>24:00</span>
          </div>

          <form onSubmit={save}>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("profile.quietStart")}>
                {(id) => <input id={id} type="time" className={inputClass} value={start} onChange={(e) => setStart(e.target.value)} required />}
              </Field>
              <Field label={t("profile.quietEnd")}>
                {(id) => <input id={id} type="time" className={inputClass} value={end} onChange={(e) => setEnd(e.target.value)} required />}
              </Field>
            </div>
            <Field label={t("profile.timezone")}>
              {(id) => (
                <select id={id} className={inputClass} value={tz} onChange={(e) => setTz(e.target.value)}>
                  <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                  <option value="UTC">UTC</option>
                </select>
              )}
            </Field>
            <div className="mb-3 flex items-center gap-2">
              <Bell className="size-3.5 text-ink-dim" aria-hidden="true" />
              <p className="text-[11px] text-ink-dim">
                {inQuietNow ? t("profile.quietNowActive") : t("profile.quietNowInactive")}
              </p>
              <Badge tone={inQuietNow ? "caution" : "neutral"}>{inQuietNow ? t("profile.quiet") : t("profile.notQuiet")}</Badge>
            </div>
            <p className="mb-3 flex items-start gap-1.5 text-[11px] text-ink-dim">
              <AlertCircle className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
              {t("profile.quietHoursCritical")}
            </p>
            <Button type="submit" variant="primary" disabled={busy}>
              {busy ? t("profile.saving") : t("profile.save")}
            </Button>
          </form>
        </>
      )}
      {saved && (
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-go">
          <Check className="size-3.5" aria-hidden="true" /> {t("profile.savedAlerts")}
        </p>
      )}

      <div className="mt-5 border-t border-hairline/50 pt-4">
        <div className="mb-2 flex items-center gap-2">
          <Sunrise className="size-3.5 text-ink-dim" aria-hidden="true" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-ink">{t("profile.preDawnBriefing")}</h3>
        </div>
        <p className="mb-3 text-sm text-ink-muted">{t("profile.preDawnBriefingExplain")}</p>
        <label className="mb-3 flex items-center gap-2.5 text-sm text-ink">
          <input
            type="checkbox"
            checked={briefingEnabled}
            onChange={(e) => setBriefingEnabled(e.target.checked)}
            className="size-4 rounded border-hairline accent-ocean-cyan"
          />
          {t("profile.enablePreDawnBriefing")}
        </label>
        {briefingEnabled && (
          <form onSubmit={saveBriefing}>
            <Field label={t("profile.departureHour")}>
              {(id) => (
                <select
                  id={id} className={inputClass} value={departureHour}
                  onChange={(e) => setDepartureHour(Number(e.target.value))}
                >
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={h}>
                      {new Date(2000, 0, 1, h).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Button type="submit" variant="primary" disabled={briefingBusy}>
              {briefingBusy ? t("profile.saving") : t("profile.save")}
            </Button>
          </form>
        )}
        {briefingSaved && (
          <p className="mt-2 flex items-center gap-1.5 text-[11px] text-go">
            <Check className="size-3.5" aria-hidden="true" /> {t("profile.savedAlerts")}
          </p>
        )}
      </div>
    </Panel>
  );
}

// --- Language & persona -------------------------------------------------------

function LanguagePanel({ profile }: { profile: Profile | null }) {
  const t = useT();
  const [busyLang, setBusyLang] = useState<string | null>(null);
  const [busyPersona, setBusyPersona] = useState(false);

  async function chooseLanguage(code: LangCode) {
    setBusyLang(code);
    try {
      const res = await authFetch("/api/profile/language", { method: "PUT", body: JSON.stringify({ language: code }) });
      if (res.ok) invalidateProfile();
    } finally {
      setBusyLang(null);
    }
  }

  async function choosePersona(persona: string) {
    setBusyPersona(true);
    try {
      const res = await authFetch("/api/profile/persona", { method: "PUT", body: JSON.stringify({ default_persona: persona }) });
      if (res.ok) invalidateProfile();
    } finally {
      setBusyPersona(false);
    }
  }

  return (
    <Panel title={t("profile.languageAndRole")}>
      <div className="mb-4">
        <p className="mb-2 flex items-center gap-1.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
          <Globe2 className="size-3.5" aria-hidden="true" /> {t("profile.language")}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {LANGUAGES.map((l) => {
            const active = profile?.language === l.code;
            return (
              <button
                key={l.code}
                type="button"
                disabled={busyLang !== null}
                onClick={() => chooseLanguage(l.code)}
                className={`rounded-full border px-3 py-1.5 text-sm transition-colors disabled:opacity-50 ${
                  active
                    ? "border-ocean-cyan/60 bg-ocean-cyan/10 font-semibold text-ocean-cyan"
                    : "border-hairline/70 bg-shelf-2/40 text-ink-muted hover:border-hairline-strong hover:text-ink"
                }`}
              >
                {l.native}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <p className="mb-2 flex items-center gap-1.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
          <Anchor className="size-3.5" aria-hidden="true" /> {t("profile.defaultRole")}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {PERSONAS.filter((p) => p.id !== "unresolved").map((p) => {
            const active = profile?.default_persona === p.id;
            return (
              <button
                key={p.id}
                type="button"
                disabled={busyPersona}
                onClick={() => choosePersona(p.id)}
                className={`rounded-full border px-3 py-1.5 text-sm transition-colors disabled:opacity-50 ${
                  active
                    ? "border-ocean-cyan/60 bg-ocean-cyan/10 font-semibold text-ocean-cyan"
                    : "border-hairline/70 bg-shelf-2/40 text-ink-muted hover:border-hairline-strong hover:text-ink"
                }`}
              >
                {p.label}
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-[11px] text-ink-dim">{t("profile.defaultRoleHint")}</p>
      </div>
    </Panel>
  );
}
