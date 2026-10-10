"use client";

// District Ops (§4.2 `/ops`) — coastal-authority surface. Sector threat
// matrix (SEC001–SEC014), CAP 1.2 builder, four-channel broadcast composer,
// audit trail. §5.5 is a hard constraint: the authority sees COUNTS per
// sector, never plottable individual vessels.
import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  Building2,
  LifeBuoy,
  Radio,
  CheckCircle2,
  AlertTriangle,
  History,
  RotateCw,
} from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Badge, type BadgeTone } from "../components/Badge";
import { Button } from "../components/Button";
import { Field, inputClass } from "../components/Field";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { usePersona } from "../persona/context";
import { authFetch, getToken, useAuth } from "../lib/auth";
import type { DistressMarker } from "../components/MapView";

// MapLibre touches `window` at module load — client-only, same as /map.
const MapView = dynamic(() => import("../components/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full" />,
});

const PORT_AUTHORITIES = [
  { name: "Mumbai", email: "authority.mumbai@orca.test", lat: 18.9446, lon: 72.8347 },
  { name: "Thoothukudi", email: "authority.thoothukudi@orca.test", lat: 8.7642, lon: 78.1348 },
  { name: "Chennai", email: "authority.chennai@orca.test", lat: 13.0827, lon: 80.2707 },
  { name: "Kochi", email: "authority.kochi@orca.test", lat: 9.9312, lon: 76.2673 },
  { name: "Visakhapatnam", email: "authority.visakhapatnam@orca.test", lat: 17.6868, lon: 83.2185 },
  { name: "Mangalore", email: "authority.mangalore@orca.test", lat: 12.8700, lon: 74.8800 },
  { name: "Rameswaram", email: "authority.rameswaram@orca.test", lat: 9.2876, lon: 79.3129 },
  { name: "Kanyakumari", email: "authority.kanyakumari@orca.test", lat: 8.0883, lon: 77.5385 },
  { name: "Paradip", email: "authority.paradip@orca.test", lat: 20.3164, lon: 86.6114 },
  { name: "Veraval", email: "authority.veraval@orca.test", lat: 20.9074, lon: 70.3678 },
  { name: "Kakinada", email: "authority.kakinada@orca.test", lat: 16.9891, lon: 82.2475 },
  { name: "Kolkata", email: "authority.kolkata@orca.test", lat: 22.5726, lon: 88.3639 },
];

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
  const auth = useAuth();
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
      setError(null);
    } catch {
      setError("server");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- forbidden/server state is set from load()'s outcome
    void load();
  }, [load]);

  const currentPort = auth.profile?.home_port_name || null;

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
          body="District ops is limited to coastal-authority and admin accounts. Sign in with an authority account, then return here."
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

          {/* Multi-Persona Broadcast Composer & Issuer */}
          <BroadcastComposer authorityPort={currentPort} authorityName={auth.profile?.display_name} />

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

type BroadcastResult = {
  status: string;
  alert_id: string;
  title: string;
  severity: "info" | "advisory" | "warning" | "danger";
  target_audience: "all" | "fisherman" | "commercial_navigator" | "researcher" | "port_users";
  authority_name: string;
  authority_port: string;
  delivered_count: number;
  watches_updated: number;
  breakdown: Record<string, number>;
  published_at: string;
};

type BroadcastHistoryItem = {
  alert_id: string;
  title: string;
  severity: "info" | "advisory" | "warning" | "danger";
  target_audience: string;
  authority_name: string;
  authority_port: string;
  delivered_count: number;
  watches_updated: number;
  published_at: string | null;
};

const AUDIENCE_OPTIONS: {
  id: "all" | "fisherman" | "commercial_navigator" | "researcher" | "port_users";
  label: string;
  icon: string;
  desc: string;
}[] = [
  { id: "all", label: "All User Types", icon: "🌐", desc: "All mariners, coastal vessels & subscribers" },
  { id: "fisherman", label: "Fishermen", icon: "🎣", desc: "Artisanal, mechanized & traditional fishing craft" },
  { id: "commercial_navigator", label: "Commercial Navigators", icon: "🚢", desc: "Cargo vessels, container ships & tugs" },
  { id: "researcher", label: "Ocean Researchers", icon: "🔬", desc: "Research survey vessels & oceanographic teams" },
  { id: "port_users", label: "Port Jurisdiction", icon: "⚓", desc: "Mariners registered in this port authority sector" },
];

const SEVERITY_OPTIONS: { id: "danger" | "warning" | "advisory" | "info"; label: string; tone: BadgeTone }[] = [
  { id: "danger", label: "Danger (Critical)", tone: "no-go" },
  { id: "warning", label: "Warning (High)", tone: "caution" },
  { id: "advisory", label: "Advisory (Caution)", tone: "accent" },
  { id: "info", label: "Info (Notice)", tone: "neutral" },
];

const CHANNELS_LIST = [
  { id: "in_app", label: "In-App Push (Live)", live: true },
  { id: "sms", label: "SMS Broadcast (Simulated)", live: false },
  { id: "vhf", label: "VHF Ch 16 (Simulated)", live: false },
  { id: "harbour_board", label: "Harbour Board (Simulated)", live: false },
  { id: "whatsapp", label: "WhatsApp (Simulated)", live: false },
];

function BroadcastComposer({
  authorityPort,
}: {
  authorityPort?: string | null;
  authorityName?: string | null;
}) {
  const [targetAudience, setTargetAudience] = useState<
    "all" | "fisherman" | "commercial_navigator" | "researcher" | "port_users"
  >("all");
  const [severity, setSeverity] = useState<"danger" | "warning" | "advisory" | "info">("warning");
  const [title, setTitle] = useState("Severe Cyclone & Wave Alert");
  const [body, setBody] = useState(
    "Squally weather with sustained gale winds 48 kt and wave swells 4.5 m detected. All vessels in this coastal sector are advised immediate caution and to return to safe harbour.",
  );
  const [location, setLocation] = useState(authorityPort ? `${authorityPort} Sector` : "Mumbai Sector");
  const [lat, setLat] = useState("18.945");
  const [lon, setLon] = useState("72.835");
  const [radiusKm, setRadiusKm] = useState("30");
  const [channels, setChannels] = useState<string[]>(["in_app", "sms", "vhf"]);

  const [publishBusy, setPublishBusy] = useState(false);
  const [publishResult, setPublishResult] = useState<BroadcastResult | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);

  const [previewBusy, setPreviewBusy] = useState(false);
  const [preview, setPreview] = useState<Record<string, { body: string; chars: number | null }> | null>(null);

  const [history, setHistory] = useState<BroadcastHistoryItem[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  // Sync default location & coordinates during render when authorityPort changes
  const [prevAuthorityPort, setPrevAuthorityPort] = useState(authorityPort);
  if (authorityPort !== prevAuthorityPort) {
    setPrevAuthorityPort(authorityPort);
    if (authorityPort) {
      setLocation(`${authorityPort} Sector`);
      const matched = PORT_AUTHORITIES.find((p) => p.name.toLowerCase() === authorityPort.toLowerCase());
      if (matched) {
        setLat(String(matched.lat));
        setLon(String(matched.lon));
      }
    }
  }

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await authFetch("/api/ops/broadcast/history?limit=15");
      if (res.ok) {
        const data = await res.json();
        setHistory(data.history || []);
      }
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  async function publishAlert() {
    setPublishBusy(true);
    setPublishError(null);
    try {
      const res = await authFetch("/api/ops/broadcast/publish", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          body: body.trim(),
          severity,
          target_audience: targetAudience,
          location: location.trim(),
          lat: lat ? Number(lat) : undefined,
          lon: lon ? Number(lon) : undefined,
          radius_km: radiusKm ? Number(radiusKm) : 30.0,
          channels,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Failed to broadcast alert (${res.status})`);
      }
      const data: BroadcastResult = await res.json();
      setPublishResult(data);
      if (showHistory) void loadHistory();
    } catch (err: unknown) {
      setPublishError(err instanceof Error ? err.message : "Failed to broadcast alert");
    } finally {
      setPublishBusy(false);
    }
  }

  async function runPreview() {
    setPreviewBusy(true);
    try {
      const p = await authFetch(
        `/api/ops/broadcast/preview?verdict=${encodeURIComponent(severity.toUpperCase())}&hazard=${encodeURIComponent(title)}&location=${encodeURIComponent(location)}`,
      );
      if (p.ok) setPreview((await p.json()).channels);
    } finally {
      setPreviewBusy(false);
    }
  }

  function toggleChannel(chId: string) {
    setChannels((prev) => (prev.includes(chId) ? prev.filter((c) => c !== chId) : [...prev, chId]));
  }

  return (
    <Panel title="Broadcast alert composer & issuer" className="mb-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-hairline pb-3">
        <p className="text-xs text-ink-muted">
          Authoritative broadcast terminal. Select target audience, severity, and advisory directives to issue live alerts.
        </p>
        <button
          type="button"
          className="flex items-center gap-1.5 text-xs text-ocean-cyan hover:underline"
          onClick={() => {
            setShowHistory((v) => !v);
            if (!showHistory && !history) void loadHistory();
          }}
        >
          <History className="size-3.5" />
          <span>{showHistory ? "Hide broadcast log" : "View broadcast log"}</span>
        </button>
      </div>

      {/* Target Audience / User Type Selection */}
      <div className="mb-4">
        <label className="mb-2 block text-xs font-semibold text-ink">
          Target user type / Audience:
        </label>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {AUDIENCE_OPTIONS.map((opt) => {
            const isSelected = targetAudience === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                className={`flex flex-col rounded-sm border p-2.5 text-left transition-all ${
                  isSelected
                    ? "border-ocean-cyan bg-ocean-cyan/15 shadow-sm"
                    : "border-hairline bg-shelf-1/60 hover:bg-shelf-1"
                }`}
                onClick={() => setTargetAudience(opt.id)}
              >
                <div className="flex items-center gap-2">
                  <span className="text-base">{opt.icon}</span>
                  <span className={`text-xs font-semibold ${isSelected ? "text-ocean-cyan" : "text-ink"}`}>
                    {opt.label}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-ink-dim line-clamp-1">{opt.desc}</p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Severity Selector */}
      <div className="mb-4">
        <label className="mb-2 block text-xs font-semibold text-ink">Alert severity level:</label>
        <div className="flex flex-wrap gap-2">
          {SEVERITY_OPTIONS.map((sev) => {
            const isSelected = severity === sev.id;
            return (
              <button
                key={sev.id}
                type="button"
                className={`flex items-center gap-1.5 rounded-sm px-3 py-1.5 text-xs font-medium transition-all ${
                  isSelected
                    ? "ring-2 ring-offset-1 ring-ocean-cyan"
                    : "opacity-75 hover:opacity-100"
                }`}
                onClick={() => setSeverity(sev.id)}
              >
                <Badge tone={sev.tone}>{sev.label}</Badge>
              </button>
            );
          })}
        </div>
      </div>

      {/* Form Fields: Title & Location */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Alert title / Headline">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Severe Cyclone Warning"
            />
          )}
        </Field>
        <Field label="Sector location name">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Mumbai Sector"
            />
          )}
        </Field>
      </div>

      {/* Sector Coordinates & Radius */}
      <div className="mt-3 grid grid-cols-3 gap-3">
        <Field label="Latitude (°N)" hint="Sector centroid">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              value={lat}
              onChange={(e) => setLat(e.target.value)}
              placeholder="18.945"
              inputMode="decimal"
            />
          )}
        </Field>
        <Field label="Longitude (°E)" hint="Sector centroid">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              value={lon}
              onChange={(e) => setLon(e.target.value)}
              placeholder="72.835"
              inputMode="decimal"
            />
          )}
        </Field>
        <Field label="Coverage radius (km)" hint="Active watch match">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              value={radiusKm}
              onChange={(e) => setRadiusKm(e.target.value)}
              placeholder="30"
              inputMode="decimal"
            />
          )}
        </Field>
      </div>

      {/* Message Directive Body */}
      <div className="mt-3">
        <Field label="Alert directive & survival instructions" hint="Delivered to user notifications and watches">
          {(id) => (
            <textarea
              id={id}
              rows={3}
              className={`${inputClass} resize-y font-sans`}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Enter comprehensive emergency guidance, gale warnings, VHF frequencies, or port directives..."
            />
          )}
        </Field>
      </div>

      {/* Dispatch Channels Selection */}
      <div className="mt-3">
        <label className="mb-1.5 block text-[11px] font-medium text-ink-dim">
          Dispatched channels:
        </label>
        <div className="flex flex-wrap gap-2">
          {CHANNELS_LIST.map((ch) => {
            const checked = channels.includes(ch.id);
            return (
              <button
                key={ch.id}
                type="button"
                className={`flex items-center gap-1.5 rounded-sm border px-2.5 py-1 text-xs transition-colors ${
                  checked
                    ? "border-ocean-cyan bg-ocean-cyan/20 text-ink"
                    : "border-hairline bg-shelf-1 text-ink-dim hover:text-ink"
                }`}
                onClick={() => toggleChannel(ch.id)}
              >
                <span>{checked ? "✓" : "+"}</span>
                <span>{ch.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Actions */}
      <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-hairline pt-3.5">
        <Button
          variant="primary"
          onClick={publishAlert}
          disabled={publishBusy || !title.trim() || !body.trim()}
        >
          <div className="flex items-center gap-2">
            <Radio className={`size-4 ${publishBusy ? "animate-pulse" : ""}`} />
            <span>{publishBusy ? "Broadcasting to mariners…" : "Broadcast alert to users"}</span>
          </div>
        </Button>
        <Button variant="ghost" onClick={runPreview} disabled={previewBusy}>
          {previewBusy ? "Rendering channels…" : "Preview all channels"}
        </Button>
      </div>

      {/* Delivery Feedback Banner */}
      {publishError && (
        <div className="mt-4 flex items-start gap-2.5 rounded-sm border border-no-go/40 bg-no-go/10 p-3 text-xs text-no-go">
          <AlertTriangle className="size-4 shrink-0 mt-0.5" />
          <div>
            <strong>Broadcast failed:</strong> {publishError}
          </div>
        </div>
      )}

      {publishResult && (
        <div className="mt-4 rounded-sm border border-emerald-500/40 bg-emerald-950/20 p-3.5 text-xs text-emerald-300">
          <div className="flex items-center justify-between gap-2 border-b border-emerald-500/20 pb-2">
            <span className="flex items-center gap-2 font-semibold">
              <CheckCircle2 className="size-4 text-emerald-400" />
              <span>ALERT BROADCAST SUCCESSFULLY PUBLISHED</span>
            </span>
            <Badge tone="accent">{publishResult.target_audience.replace(/_/g, " ").toUpperCase()}</Badge>
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <p className="text-[11px] text-ink-dim">Recipients delivered:</p>
              <p className="text-base font-bold text-ink" data-readout>
                {publishResult.delivered_count} users
              </p>
            </div>
            <div>
              <p className="text-[11px] text-ink-dim">Watches updated:</p>
              <p className="text-base font-bold text-ocean-cyan" data-readout>
                {publishResult.watches_updated} watches
              </p>
            </div>
            <div>
              <p className="text-[11px] text-ink-dim">Issuing authority:</p>
              <p className="text-xs font-medium text-ink">
                {publishResult.authority_name}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-ink-dim">Port sector:</p>
              <p className="text-xs font-medium text-ink">
                {publishResult.authority_port}
              </p>
            </div>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-2 text-[11px] text-ink-muted">
            <span className="text-ink-dim">Delivery breakdown:</span>
            <span>🎣 {publishResult.breakdown.fisherman ?? 0} Fishermen</span>
            <span>· 🚢 {publishResult.breakdown.commercial_navigator ?? 0} Navigators</span>
            <span>· 🔬 {publishResult.breakdown.researcher ?? 0} Researchers</span>
            <span>· 👤 {publishResult.breakdown.unresolved ?? 0} General mariners</span>
          </div>
        </div>
      )}

      {/* Broadcast History Panel */}
      {showHistory && (
        <div className="mt-4 rounded-sm border border-hairline bg-shelf-1/40 p-3 text-xs">
          <div className="flex items-center justify-between gap-2 border-b border-hairline pb-2">
            <span className="font-semibold text-ink">Recent authority alert broadcasts</span>
            <button
              type="button"
              className="text-[11px] text-accent hover:underline flex items-center gap-1"
              onClick={loadHistory}
              disabled={historyLoading}
            >
              <RotateCw className={`size-3 ${historyLoading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
          {historyLoading && <Skeleton className="mt-2 h-16" />}
          {!historyLoading && (!history || history.length === 0) && (
            <p className="mt-2 text-ink-dim">No previous broadcast records found in the audit trail.</p>
          )}
          {!historyLoading && history && history.length > 0 && (
            <div className="mt-2.5 space-y-2 max-h-60 overflow-y-auto pr-1">
              {history.map((h) => (
                <div key={h.alert_id} className="rounded border border-hairline/60 bg-shelf-2/60 p-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <Badge tone={SEV_TONE[h.severity]}>{h.severity.toUpperCase()}</Badge>
                      <span className="font-medium text-ink">{h.title}</span>
                    </div>
                    {h.published_at && (
                      <time className="text-[11px] text-ink-dim">
                        {new Date(h.published_at).toLocaleString("en-GB", {
                          dateStyle: "short",
                          timeStyle: "short",
                          timeZone: "Asia/Kolkata",
                        })}{" "}
                        IST
                      </time>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-ink-dim">
                    <span>Issued by: <strong className="text-ink-muted">{h.authority_name}</strong> ({h.authority_port})</span>
                    <span>· Target: <strong className="text-ocean-cyan">{h.target_audience}</strong></span>
                    <span>· Delivered to: <strong className="text-ink-muted">{h.delivered_count} users</strong></span>
                    {h.watches_updated > 0 && <span>({h.watches_updated} watches linked)</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Simulated Channel Previews */}
      {preview && (
        <div className="mt-4 border-t border-hairline pt-3">
          <p className="mb-2 text-xs font-semibold text-ink">Multi-channel broadcast preview:</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {(["web", "sms", "ivr", "ussd", "whatsapp", "missed_call", "vhf", "harbour_board"] as const).map(
              (ch) => (
                <div key={ch} className="rounded-sm border border-hairline bg-shelf-1/60 p-3">
                  <p className="mb-1 flex items-center justify-between text-[11px] font-medium text-ink-dim">
                    <span className="uppercase">{ch}</span>
                    {preview[ch]?.chars != null && <span data-readout>{preview[ch].chars} chars</span>}
                  </p>
                  <p className="text-xs whitespace-pre-wrap text-ink-muted">{preview[ch]?.body}</p>
                  {ch !== "web" && (
                    <p className="mt-1 text-[11px] text-caution">Delivery not built — SIMULATED preview only.</p>
                  )}
                </div>
              ),
            )}
          </div>
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
  target_port?: string | null;
  authority_name?: string | null;
  survival_suggestions?: string[] | null;
  is_assigned_to_reader?: boolean;
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
  const [portFilter, setPortFilter] = useState<"all" | "assigned">("all");

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
  const hasAssigned = (events ?? []).some((e) => e.is_assigned_to_reader);
  const displayedEvents = (events ?? []).filter((e) => portFilter === "all" || e.is_assigned_to_reader);

  return (
    <Panel title={`Distress queue — last 24 h${events ? ` · ${active} active` : ""}`} className="mb-4">
      {failed && <ErrorState title="Could not load the distress queue" body="The server did not answer. Retrying every 15 seconds." />}
      {!failed && events === null && <Skeleton className="h-24" />}
      {events && events.length === 0 && (
        <EmptyState icon={<LifeBuoy className="size-6" />} title="No distress calls in the last 24 hours" body="New calls appear here within 15 seconds." />
      )}
      {events && events.length > 0 && (
        <>
          {active > 0 && (
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-sm border border-no-go/40 bg-no-go/10 px-3 py-2 text-xs text-no-go">
              <span className="flex items-center gap-2 font-medium">
                <LifeBuoy className="size-4 animate-pulse shrink-0" />
                <span>
                  <strong>CRITICAL DISTRESS SIGNAL ACTIVE:</strong> Coastal authorities alerted &amp; rescue units mobilizing.
                </span>
              </span>
              <span className="font-mono text-[11px] font-semibold tracking-wider">
                {active} ACTIVE INCIDENT{active > 1 ? "S" : ""}
              </span>
            </div>
          )}

          {hasAssigned && (
            <div className="mb-3 flex gap-2 text-xs">
              <button
                type="button"
                className={`rounded px-2.5 py-1 font-medium transition-colors ${
                  portFilter === "all" ? "bg-shelf-3 text-ink" : "text-ink-dim hover:text-ink"
                }`}
                onClick={() => setPortFilter("all")}
              >
                All sectors ({events.length})
              </button>
              <button
                type="button"
                className={`rounded px-2.5 py-1 font-medium transition-colors ${
                  portFilter === "assigned" ? "bg-no-go/20 text-no-go border border-no-go/40" : "text-ink-dim hover:text-ink"
                }`}
                onClick={() => setPortFilter("assigned")}
              >
                Assigned to your port ({events.filter((e) => e.is_assigned_to_reader).length})
              </button>
            </div>
          )}

          {markers.length > 0 && (
            <div className="mb-3 h-56 overflow-hidden rounded-sm border border-hairline">
              <MapView className="h-full w-full" distressMarkers={markers} showLayerPanel={false} showRegionSwitcher={false} showLegends={false} showSoundingHud={false} />
            </div>
          )}
          <ul className="flex flex-col gap-2" aria-live="assertive">
            {displayedEvents.map((e) => (
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
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                  {e.authority_name ? (
                    <Badge tone="accent">
                      Assigned: {e.authority_name}
                    </Badge>
                  ) : e.target_port ? (
                    <Badge tone="accent">
                      Sector: {e.target_port} Authority
                    </Badge>
                  ) : null}
                  {e.is_assigned_to_reader && (
                    <Badge tone="no-go">Your Port Unit</Badge>
                  )}
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

                {e.survival_suggestions && e.survival_suggestions.length > 0 && (
                  <details className="mt-2 rounded border border-hairline/60 bg-abyss/40 p-2 text-[11px]">
                    <summary className="cursor-pointer font-medium text-ink-dim hover:text-ink">
                      Vessel Survival Instructions ({e.survival_suggestions.length} steps issued)
                    </summary>
                    <ol className="mt-1.5 list-decimal space-y-1 pl-4 text-ink-muted">
                      {e.survival_suggestions.map((step, idx) => (
                        <li key={idx}>{step}</li>
                      ))}
                    </ol>
                  </details>
                )}

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
