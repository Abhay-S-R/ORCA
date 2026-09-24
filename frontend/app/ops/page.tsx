"use client";

// District Ops (§4.2 `/ops`) — coastal-authority surface. Sector threat
// matrix (SEC001–SEC014), CAP 1.2 builder, four-channel broadcast composer,
// audit trail. §5.5 is a hard constraint: the authority sees COUNTS per
// sector, never plottable individual vessels.
import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Building2, LifeBuoy } from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Badge, type BadgeTone } from "../components/Badge";
import { Button } from "../components/Button";
import { Field, inputClass } from "../components/Field";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { usePersona } from "../persona/context";
import { authFetch, getToken } from "../lib/auth";
import type { DistressMarker } from "../components/MapView";

// MapLibre touches `window` at module load — client-only, same as /map.
const MapView = dynamic(() => import("../components/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full" />,
});

type SectorRow = {
  sector_id: string;
  sector_name: string | null;
  pfz_status: string | null;
  pfz_message: string | null;
  is_data_gap: boolean;
  vessel_count: number;
  alert_severity: "info" | "advisory" | "warning" | "danger";
};

const SEV_TONE: Record<string, BadgeTone> = { info: "neutral", advisory: "accent", warning: "caution", danger: "no-go" };

export default function OpsPage() {
  const { persona } = usePersona();
  const [rows, setRows] = useState<SectorRow[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [error, setError] = useState<"forbidden" | "server" | null>(null);

  const load = useCallback(async () => {
    if (!getToken()) {
      setError("forbidden");
      return;
    }
    try {
      const r = await authFetch("/api/ops/sectors");
      if (r.status === 401 || r.status === 403) {
        setError("forbidden");
        return;
      }
      if (!r.ok) {
        setError("server");
        return;
      }
      const data = await r.json();
      setRows(data.matrix);
      setCounts(data.district_severity_counts ?? {});
    } catch {
      setError("server");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- forbidden/server state is set from load()'s outcome
    void load();
  }, [load]);

  return (
    <PageBody className="mx-auto max-w-4xl">
      <PageHeader
        title="District ops"
        lede="Sector threat rollups, CAP 1.2 alert composition and the broadcast preview for coastal authorities."
      />

      {error === "forbidden" && (
        <EmptyState
          icon={<Building2 className="size-6" />}
          title="Authority sign-in required"
          body="District ops is limited to coastal-authority and admin accounts. Sign in from Watches with an authority account, then return here."
        />
      )}
      {error === "server" && <ErrorState title="Could not load district data" body="The server did not answer. Try reloading." />}

      {!error && (
        <>
          <DistressQueue />

          {/* P4.4 — "district roll-up first": the day's severity counts,
              right after the one thing more urgent than any roll-up
              (an open distress call). */}
          <Panel title="District severity — last 24 h" className="mb-4">
            <div className="flex flex-wrap gap-2">
              {(["danger", "warning", "advisory", "info"] as const).map((s) => (
                <Badge key={s} tone={SEV_TONE[s]}>
                  {s}: <span data-readout>{counts[s] ?? 0}</span>
                </Badge>
              ))}
            </div>
          </Panel>

          {/* P4.4 — "CAP builder promoted from preview to primary": its own
              panel, ahead of the sector matrix, output always rendered
              rather than tucked behind a `<details>` under the broadcast
              composer's channel preview. */}
          <CapBuilder />

          <Panel title="Sector threat matrix" className="mb-4">
            {rows === null ? (
              <Skeleton className="h-64" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-ink-dim">
                    <tr className="border-b border-hairline">
                      <th className="py-2 pr-3 font-medium">Sector</th>
                      <th className="py-2 pr-3 font-medium">PFZ status</th>
                      <th className="py-2 pr-3 font-medium">Vessels</th>
                      <th className="py-2 font-medium">Alert</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.sector_id} className="border-b border-hairline/60">
                        <td className="py-2 pr-3 text-ink">
                          {r.sector_id}
                          <span className="ml-1 text-ink-dim">{r.sector_name}</span>
                        </td>
                        <td className="py-2 pr-3 text-ink-muted">
                          {r.pfz_status ?? "—"}
                          {r.is_data_gap && <span className="ml-1 text-caution">data gap</span>}
                        </td>
                        <td className="py-2 pr-3" data-readout>
                          {r.vessel_count}
                        </td>
                        <td className="py-2">
                          <Badge tone={SEV_TONE[r.alert_severity]}>{r.alert_severity}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 text-[11px] text-ink-dim">
                  Vessel figures are sector counts only — individual positions are never shown to an authority (§5.5).
                </p>
              </div>
            )}
          </Panel>

          <BroadcastComposer />
        </>
      )}

      <p className="mt-4 text-[11px] text-ink-dim">
        Viewing as <span className="text-ink-muted">{persona.replace(/_/g, " ")}</span>.
      </p>
    </PageBody>
  );
}

// P4.4 — the CAP 1.2 builder, split out of the broadcast composer and
// promoted to a primary panel of its own: a headline/description/severity
// form and the generated XML payload, both always visible, not a preview
// artifact tucked inside another panel's `<details>`.
function CapBuilder() {
  const [verdict, setVerdict] = useState("NO-GO");
  const [hazard, setHazard] = useState("High waves");
  const [location, setLocation] = useState("Thoothukudi");
  const [cap, setCap] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function build() {
    setBusy(true);
    try {
      const c = await authFetch("/api/ops/cap", {
        method: "POST",
        body: JSON.stringify({
          headline: `${verdict}: ${hazard} near ${location}`,
          description: `${hazard} reported near ${location}. Advisory issued to district vessels.`,
          severity: verdict.includes("NO") ? "danger" : "warning",
          area_desc: `${location} coastal sector`,
        }),
      });
      if (c.ok) setCap(await c.text());
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="CAP 1.2 alert builder" className="mb-4">
      <div className="grid grid-cols-3 gap-3">
        <Field label="Verdict">{(id) => <input id={id} className={inputClass} value={verdict} onChange={(e) => setVerdict(e.target.value)} />}</Field>
        <Field label="Hazard">{(id) => <input id={id} className={inputClass} value={hazard} onChange={(e) => setHazard(e.target.value)} />}</Field>
        <Field label="Location">{(id) => <input id={id} className={inputClass} value={location} onChange={(e) => setLocation(e.target.value)} />}</Field>
      </div>
      <Button variant="primary" onClick={build} disabled={busy}>
        {busy ? "Building…" : "Build CAP alert"}
      </Button>

      <div className="mt-4 border-t border-hairline pt-3">
        <p className="mb-1.5 text-[11px] font-medium text-ink-dim">CAP 1.2 XML payload</p>
        {cap ? (
          <pre className="max-h-80 overflow-auto rounded-sm border border-hairline bg-abyss/60 p-3 text-[11px] text-ink-muted">
            {cap}
          </pre>
        ) : (
          <p className="text-xs text-ink-dim">Fill in the fields above and build the alert to see its CAP 1.2 XML here.</p>
        )}
      </div>
    </Panel>
  );
}

// The four rendered-and-simulated channel previews (P4.13's per-channel
// pattern, at the district-broadcast scale rather than one alert). Kept
// separate from the CAP builder above — one is the regulatory payload, the
// other is what a fisherman's phone would actually show.
function BroadcastComposer() {
  const [verdict, setVerdict] = useState("NO-GO");
  const [hazard, setHazard] = useState("High waves");
  const [location, setLocation] = useState("Thoothukudi");
  const [preview, setPreview] = useState<Record<string, { body: string; chars: number | null }> | null>(null);
  const [busy, setBusy] = useState(false);

  async function runPreview() {
    setBusy(true);
    try {
      const p = await authFetch(
        `/api/ops/broadcast/preview?verdict=${encodeURIComponent(verdict)}&hazard=${encodeURIComponent(hazard)}&location=${encodeURIComponent(location)}`,
      );
      if (p.ok) setPreview((await p.json()).channels);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Broadcast composer">
      <div className="grid grid-cols-3 gap-3">
        <Field label="Verdict">{(id) => <input id={id} className={inputClass} value={verdict} onChange={(e) => setVerdict(e.target.value)} />}</Field>
        <Field label="Hazard">{(id) => <input id={id} className={inputClass} value={hazard} onChange={(e) => setHazard(e.target.value)} />}</Field>
        <Field label="Location">{(id) => <input id={id} className={inputClass} value={location} onChange={(e) => setLocation(e.target.value)} />}</Field>
      </div>
      <Button variant="primary" onClick={runPreview} disabled={busy}>
        {busy ? "Rendering…" : "Preview all channels"}
      </Button>

      {preview && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {(["web", "sms", "ivr", "ussd", "whatsapp", "missed_call", "vhf", "harbour_board"] as const).map((ch) => (
            <div key={ch} className="rounded-sm border border-hairline bg-shelf-1/60 p-3">
              <p className="mb-1 flex items-center justify-between text-[11px] font-medium text-ink-dim">
                <span className="uppercase">{ch}</span>
                {preview[ch]?.chars != null && <span data-readout>{preview[ch].chars} chars</span>}
              </p>
              <p className="text-xs whitespace-pre-wrap text-ink-muted">{preview[ch]?.body}</p>
              {ch !== "web" && <p className="mt-1 text-[11px] text-caution">Delivery not built — SIMULATED preview only.</p>}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// --- Distress queue (P4.16) ----------------------------------------------
// The only place an authority sees an individual position, and only while the
// incident is open or acknowledged; the server audits every read and every
// state change. Polled every 15 s — a distress call must not wait for a reload.

type DistressEvent = {
  id: string;
  query_id: string;
  state: "open" | "acknowledged" | "closed";
  created_at: string;
  place_name: string | null;
  distress_type: string | null;
  matched_language: string | null;
  matched_phrase: string | null;
  // As surfaced to the caller by distress.surface_mrcc_contact.
  mrcc_contact: {
    primary?: { name?: string; phone?: string | null };
    nearest_station?: { station?: string; coordinating_mrcc?: string; straight_line_distance_km?: number } | null;
  } | null;
  lat: number | null;
  lon: number | null;
};

const STATE_TONE: Record<DistressEvent["state"], BadgeTone> = { open: "no-go", acknowledged: "caution", closed: "neutral" };

function DistressQueue() {
  const [events, setEvents] = useState<DistressEvent[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await authFetch("/api/ops/distress?hours=24");
      if (!r.ok) throw new Error(String(r.status));
      setEvents((await r.json()).events);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the queue is server state, polled
    void load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, [load]);

  async function transition(id: string, action: "acknowledge" | "close") {
    setBusy(id);
    try {
      await authFetch(`/api/ops/distress/${id}/${action}`, { method: "POST" });
      await load();
    } finally {
      setBusy(null);
    }
  }

  const markers: DistressMarker[] = (events ?? [])
    .filter((e) => e.state !== "closed" && e.lat !== null && e.lon !== null)
    .map((e) => ({ id: e.id, lat: e.lat!, lon: e.lon!, label: titleCase(e.place_name) ?? `${e.lat!.toFixed(3)}, ${e.lon!.toFixed(3)}` }));
  const active = (events ?? []).filter((e) => e.state !== "closed").length;

  return (
    <Panel title={`Distress queue — last 24 h${events ? ` · ${active} active` : ""}`} className="mb-4">
      {failed && <ErrorState title="Could not load the distress queue" body="The server did not answer. Retrying every 15 seconds." />}
      {!failed && events === null && <Skeleton className="h-24" />}
      {events && events.length === 0 && (
        <EmptyState icon={<LifeBuoy className="size-6" />} title="No distress calls in the last 24 hours" body="New calls appear here within 15 seconds." />
      )}
      {events && events.length > 0 && (
        <>
          {markers.length > 0 && (
            <div className="mb-3 h-56 overflow-hidden rounded-sm border border-hairline">
              <MapView className="h-full w-full" distressMarkers={markers} showLayerPanel={false} showRegionSwitcher={false} showLegends={false} showSoundingHud={false} />
            </div>
          )}
          <ul className="flex flex-col gap-2" aria-live="assertive">
            {events.map((e) => (
              <li key={e.id} className="rounded-sm border border-hairline bg-shelf-1/60 p-3 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={STATE_TONE[e.state]}>{e.state.toUpperCase()}</Badge>
                  <time dateTime={e.created_at} className="text-ink-dim" data-readout>
                    {new Date(e.created_at).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Kolkata" })} IST
                  </time>
                  <span className="text-ink">
                    {e.lat !== null && e.lon !== null ? (
                      <span data-readout>
                        {e.place_name ? `${titleCase(e.place_name)} · ` : ""}
                        {e.lat.toFixed(3)}°N {e.lon.toFixed(3)}°E
                      </span>
                    ) : e.state === "closed" ? (
                      "Position withheld — incident closed"
                    ) : (
                      <span className="text-caution">No position given by the caller</span>
                    )}
                  </span>
                </div>
                <p className="mt-1 text-ink-muted">
                  {e.distress_type === "sos_control" ? "SOS button" : `Phrase "${e.matched_phrase ?? "?"}"${e.matched_language ? ` (${e.matched_language})` : ""}`}
                  {e.mrcc_contact?.nearest_station
                    ? ` · nearest ${e.mrcc_contact.nearest_station.station} (${e.mrcc_contact.nearest_station.straight_line_distance_km} km), coordinated by ${e.mrcc_contact.nearest_station.coordinating_mrcc}`
                    : e.mrcc_contact?.primary?.name
                      ? ` · ${e.mrcc_contact.primary.name} ${e.mrcc_contact.primary.phone ?? ""}`
                      : ""}
                  {" · "}
                  <Link href={`/reasoning?query_id=${e.query_id}`} className="text-accent underline-offset-2 hover:underline">
                    trace
                  </Link>
                </p>
                {e.state !== "closed" && (
                  <div className="mt-2 flex gap-2">
                    {e.state === "open" && (
                      <Button variant="primary" disabled={busy === e.id} onClick={() => transition(e.id, "acknowledge")}>
                        Acknowledge
                      </Button>
                    )}
                    <Button disabled={busy === e.id} onClick={() => transition(e.id, "close")}>
                      Close incident
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-ink-dim">
            Exact positions are shown only for open and acknowledged incidents, and every view is written to the audit trail.
          </p>
        </>
      )}
    </Panel>
  );
}

// Place names come back from the gazetteer in lower case.
function titleCase(s: string | null): string | null {
  return s ? s.replace(/\b\p{L}/gu, (c) => c.toUpperCase()) : s;
}
