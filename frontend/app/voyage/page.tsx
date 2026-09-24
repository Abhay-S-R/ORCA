"use client";

// Voyage (D3 plan §5) — plan a corridor, not just check "now". Click the
// chart to drop origin/destination (or type coordinates), and ORCA returns a
// per-leg classified route: the same hazard cascade `/safety` runs for a
// single point, walked along the whole passage at each leg's own ETA.
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Anchor, AlertTriangle, Bell, BellOff, Download, MapPin, Navigation, Printer, Save, Trash2 } from "lucide-react";
import { Badge, type ConfidenceTier, type Verdict } from "../components/Badge";
import { Button } from "../components/Button";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { Field, inputClass } from "../components/Field";
import { MapView, type MapPin as Pin, type RouteGeoJson } from "../components/MapView";
import { PageHeader, PageBody } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceChip } from "../components/SourceChip";
import { ErrorState } from "../components/States";
import { VerdictBadge } from "../components/VerdictBadge";
import { getToken } from "../lib/auth";
import { createVoyage, deleteVoyage, listVoyages, promoteVoyage, unpromoteVoyage, type Voyage } from "../lib/voyages";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type VesselClass = "small_fishing" | "mechanized_trawler" | "cargo_vessel";
const VESSEL_LABELS: Record<VesselClass, string> = {
  small_fishing: "Small fishing boat",
  mechanized_trawler: "Mechanized trawler",
  cargo_vessel: "Cargo vessel",
};

type LatLon = { lat: number; lon: number };
type PointCheck = { on_land: boolean; shallow_hazard: boolean; depth_m: number | null };
type Segment = {
  segment_id: string; start: [number, number]; end: [number, number]; distance_nm: number;
  eta: string; hazard_class: string; status: "CLEAR" | "CAUTION" | "BLOCKED"; detail: string;
  depth_m: number | null; wave_height_m: number | null;
};
type NearestSafeHarbour = {
  name: string; kind: string; latitude: number; longitude: number;
  bearing_deg: number; distance_nm: number; eta_hours: number | null;
};
type SourceProvenance = { dataset: string; acquisition_timestamp: string; freshness_minutes: number };
type VoyagePlanResponse = {
  voyage_id: string; origin: [number, number]; destination: [number, number];
  vessel_class: VesselClass; departure_time: string; segments: Segment[];
  verdict: Verdict; verdict_reason: string; confidence: { score: ConfidenceTier; rationale: string };
  route_layer: { geojson: RouteGeoJson; source_provenance: SourceProvenance[] } | null;
  route_layer_dropped: string[];
  // Checklist P0 #2 — route optimization evidence, not just an audited
  // straight line. `rerouted` means this plan's own segments/verdict above
  // ARE the chosen detour, not the blocked direct route.
  rerouted: boolean;
  alternatives_tried: { strategy: string; verdict: Verdict; added_nm: number }[];
  // P1.2 (`R-NEW-8`) — the draft every under-keel clearance on this plan was
  // computed against, and whether it was the caller's choice. An assumed one
  // carries `draft_disclosure` and MUST be shown: a clearance answer computed
  // for a boat other than yours, unlabelled, is the silent-substitution
  // failure Phase 1 is named after.
  draft_m: number;
  draft_source: "supplied" | "assumed_deepest_of_class";
  draft_disclosure: string | null;
  // P5.24 — the rest of the voyage outputs: nearest safe harbour off the
  // destination (from the same ICG station roster distress calls use) and
  // a fuel estimate that only appears when the request supplied a burn
  // rate — an honest gap, not a guessed number.
  nearest_safe_harbour: NearestSafeHarbour | null;
  fuel_burn_lph: number | null;
  fuel_estimate_liters: number | null;
};
type Tide = {
  station_name: string; tidal_state: string; range_m: number | null; spring_neap: string;
  next_high: { when: string; height_m: number } | null; next_low: { when: string; height_m: number } | null;
  datum: string;
  // The heights above are PREDICTED (astronomical). This is what an INCOIS
  // gauge actually measured, carried alongside rather than blended in — the
  // residual between them is a surge or a set-up, not an error in the table.
  observed_cross_check: {
    available: boolean;
    // in_situ_gauge = an INCOIS gauge measured this. satellite_altimetry =
    // no gauge within 150 km, so CMEMS DUACS anomaly stands in. The two are
    // not interchangeable and must not render as the same card.
    source_kind?: "in_situ_gauge" | "satellite_altimetry";
    note?: string;
    dataset?: string;
    absolute_dynamic_topography_m?: number;
    station_name?: string;
    distance_km?: number;
    observed_level_m?: number;
    predicted_astronomical_m?: number;
    sea_level_anomaly_m?: number;
    status?: string;
    tsunami_trigger_state?: string;
    observed_at_ist?: string;
  };
};

const STATUS_TONE = { CLEAR: "go", CAUTION: "caution", BLOCKED: "no-go" } as const;

// Short label for the same on-land/shallow check the route planner itself
// runs per leg — surfaced at pin-drop time so a route never has to reach
// "8 segments blocked" before the actual cause (a pin placed on land, not
// a routing bug) is visible.
function pointWarning(check: { on_land: boolean; shallow_hazard: boolean } | null): string | null {
  if (!check) return null;
  if (check.on_land) return "is on land";
  if (check.shallow_hazard) return "is in shallow water";
  return null;
}

// P5.7 (§8.4) — GPX/CSV export of the waypoint table. The plan already
// carries every field either format needs, so this is a pure client-side
// serialization of state already on screen, not a second server round-trip.
function planToGpx(plan: VoyagePlanResponse): string {
  const points = [
    { lat: plan.origin[0], lon: plan.origin[1], name: "Origin", cmt: "" },
    ...plan.segments.map((s) => ({
      lat: s.end[0], lon: s.end[1], name: s.segment_id,
      cmt: `${s.hazard_class} (${s.status}) — ${s.detail}`, time: s.eta,
    })),
  ];
  const rtepts = points
    .map((p) => {
      const time = "time" in p && p.time ? `<time>${p.time}</time>` : "";
      return `      <rtept lat="${p.lat}" lon="${p.lon}"><name>${p.name}</name>${time}<cmt>${p.cmt}</cmt></rtept>`;
    })
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="ORCA" xmlns="http://www.topografix.com/GPX/1/1">
  <rte>
    <name>ORCA voyage ${plan.voyage_id}</name>
    <desc>${plan.verdict}: ${plan.verdict_reason}</desc>
${rtepts}
  </rte>
</gpx>`;
}

function planToCsv(plan: VoyagePlanResponse): string {
  const escape = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const header = "leg,start_lat,start_lon,end_lat,end_lon,distance_nm,eta_utc,hazard_class,status,ukc_m,wave_height_m,detail";
  const rows = plan.segments.map((s) => {
    const ukc = s.depth_m != null ? (s.depth_m - plan.draft_m).toFixed(1) : "";
    return [
      s.segment_id, s.start[0], s.start[1], s.end[0], s.end[1], s.distance_nm.toFixed(2), s.eta,
      s.hazard_class, s.status, ukc, s.wave_height_m ?? "", escape(s.detail),
    ].join(",");
  });
  return [header, ...rows].join("\n");
}

function downloadText(filename: string, content: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function VoyageContent() {
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<"origin" | "destination">("origin");
  const [origin, setOrigin] = useState<LatLon | null>(null);
  const [destination, setDestination] = useState<LatLon | null>(null);
  // Live land/shallow feedback the moment a pin drops — the same
  // /api/depth lookup the chart's own sounding HUD already uses, just
  // surfaced right at the point of the mistake instead of only after a
  // "8 segments blocked" result forces a user to guess why.
  const [originCheck, setOriginCheck] = useState<PointCheck | null>(null);
  const [destinationCheck, setDestinationCheck] = useState<PointCheck | null>(null);
  const [vesselClass, setVesselClass] = useState<VesselClass>("small_fishing");
  const [speedKn, setSpeedKn] = useState(8);
  const [draftM, setDraftM] = useState("");
  // P1.2 — the "correct it in one tap" target for the assumed-draft banner.
  const draftRef = useRef<HTMLInputElement>(null);
  const [departure, setDeparture] = useState("");
  // P5.24 — fuel-burn rate is optional and per-vessel; left blank, the plan
  // states the total is missing rather than guessing a rate.
  const [fuelBurnLph, setFuelBurnLph] = useState("");

  const [plan, setPlan] = useState<VoyagePlanResponse | null>(null);
  const [tide, setTide] = useState<Tide | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // P5.20 UI — saved voyages. The backend (`/api/voyages`, promote-to-watch)
  // has been done and API-only since P5.20's own entry; this is the
  // frontend half that entry named as still missing.
  const [signedIn, setSignedIn] = useState(false);
  const [savedVoyages, setSavedVoyages] = useState<Voyage[] | null>(null);
  const [savingVoyage, setSavingVoyage] = useState(false);
  const [voyageBusyId, setVoyageBusyId] = useState<string | null>(null);

  const loadSavedVoyages = useCallback(() => {
    if (!getToken()) return;
    listVoyages().then(setSavedVoyages).catch(() => setSavedVoyages([]));
  }, []);

  useEffect(() => {
    const sync = () => setSignedIn(!!getToken());
    sync();
    window.addEventListener("orca:auth", sync);
    return () => window.removeEventListener("orca:auth", sync);
  }, []);

  useEffect(() => {
    if (signedIn) {
      loadSavedVoyages();
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clearing stale data on sign-out, not synchronizing external state
    setSavedVoyages(null);
  }, [signedIn, loadSavedVoyages]);

  async function saveVoyage() {
    if (!plan) return;
    setSavingVoyage(true);
    try {
      await createVoyage({
        name: `${plan.origin[0].toFixed(2)},${plan.origin[1].toFixed(2)} → ${plan.destination[0].toFixed(2)},${plan.destination[1].toFixed(2)}`,
        route: [
          { lat: plan.origin[0], lon: plan.origin[1] },
          ...plan.segments.map((s) => ({ lat: s.end[0], lon: s.end[1] })),
        ],
        departure_at: plan.departure_time,
      });
      loadSavedVoyages();
    } finally {
      setSavingVoyage(false);
    }
  }

  function loadSavedVoyage(v: Voyage) {
    const first = v.route[0];
    const last = v.route[v.route.length - 1];
    setOrigin({ lat: first.lat, lon: first.lon });
    setDestination({ lat: last.lat, lon: last.lon });
    setOriginCheck(null);
    setDestinationCheck(null);
  }

  async function togglePromote(v: Voyage) {
    setVoyageBusyId(v.id);
    try {
      if (v.watch_id) await unpromoteVoyage(v.id);
      else await promoteVoyage(v.id);
      loadSavedVoyages();
    } finally {
      setVoyageBusyId(null);
    }
  }

  async function removeSavedVoyage(id: string) {
    setVoyageBusyId(id);
    try {
      await deleteVoyage(id);
      loadSavedVoyages();
    } finally {
      setVoyageBusyId(null);
    }
  }

  // A ROUTE question on /ask links here with its endpoints already resolved
  // (?from=lat,lon&to=lat,lon — P5.29). Pins only; the user still presses Plan.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const parse = (v: string | null) => {
      const [lat, lon] = (v ?? "").split(",").map(Number);
      return Number.isFinite(lat) && Number.isFinite(lon) && v ? { lat, lon } : null;
    };
    const from = parse(q.get("from"));
    const to = parse(q.get("to"));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the URL only exists after mount
    if (from) setOrigin(from);
    if (to) setDestination(to);
    if (from && !to) setMode("destination");
  }, []);

  function handlePointClick(lat: number, lon: number) {
    const setPoint = mode === "origin" ? setOrigin : setDestination;
    const setCheck = mode === "origin" ? setOriginCheck : setDestinationCheck;
    setPoint({ lat, lon });
    setCheck(null);
    if (mode === "origin") setMode("destination");
    fetch(`${API_BASE}/api/depth?lat=${lat}&lon=${lon}`)
      .then((r) => r.json())
      .then(setCheck)
      .catch(() => {});
  }

  async function runPlan(o: LatLon, d: LatLon) {
    setLoading(true);
    setError(null);
    setPlan(null);
    setTide(null);
    try {
      const res = await fetch(`${API_BASE}/api/voyage-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_lat: o.lat, origin_lon: o.lon,
          destination_lat: d.lat, destination_lon: d.lon,
          vessel_class: vesselClass, speed_kn: speedKn,
          draft_m: draftM ? Number(draftM) : null,
          departure_time: departure ? new Date(departure).toISOString() : null,
          fuel_burn_lph: fuelBurnLph ? Number(fuelBurnLph) : null,
        }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = (await res.json()) as VoyagePlanResponse;
      setPlan(data);
      // Berthing window at the destination — same tide predictor `/safety`'s
      // sibling ocean-analytics surfaces already use, just pointed here.
      fetch(`${API_BASE}/api/tides?lat=${d.lat}&lon=${d.lon}`)
        .then((r) => r.json())
        .then(setTide)
        .catch(() => {});
    } catch {
      setError("Could not reach ORCA. Check the backend is running and try again.");
    } finally {
      setLoading(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!origin || !destination) return;
    await runPlan(origin, destination);
  }

  // P6.9 (orca_final §29.2) — `/demo`'s depth-blocked-detour scenario card
  // deep-links here with a pinned origin/destination rather than duplicating
  // this page's map/segment-table rendering: bathymetry is static, so the
  // same coordinates always cross the same shallow bank and always need the
  // same detour, with no fixture-pinning required (unlike scenario 1's
  // live-weather fixtures).
  const autoRanRef = useRef(false);
  useEffect(() => {
    if (autoRanRef.current) return;
    const oLat = searchParams.get("origin_lat"), oLon = searchParams.get("origin_lon");
    const dLat = searchParams.get("destination_lat"), dLon = searchParams.get("destination_lon");
    if (!oLat || !oLon || !dLat || !dLon) return;
    autoRanRef.current = true;
    const o = { lat: Number(oLat), lon: Number(oLon) };
    const d = { lat: Number(dLat), lon: Number(dLon) };
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the URL only exists after mount, same rationale as line 274 above
    setOrigin(o);
    setDestination(d);
    void runPlan(o, d);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deliberately one-shot on mount, not on every origin/destination edit
  }, [searchParams]);

  const pins: Pin[] = [
    ...(origin ? [{ lat: origin.lat, lon: origin.lon, label: "Origin", color: "#2f6f74" }] : []),
    ...(destination ? [{ lat: destination.lat, lon: destination.lon, label: "Destination", color: "#8a3b52" }] : []),
  ];
  const routeProvenance = plan?.route_layer?.source_provenance?.[0];

  return (
    <PageBody className="mx-auto max-w-7xl">
      <PageHeader
        title="Plan a voyage"
        lede="Tap the chart to drop an origin and destination, or type coordinates. ORCA classifies every leg — shallows, boundaries, protected areas, rough sea and lightning — at that leg's own arrival time, not just conditions right now."
      />

      <div className="grid gap-6 lg:grid-cols-[380px_1fr] print:block">
        <div className="flex flex-col gap-4">
          <Panel title="Route" dense className="print:hidden">
            <form onSubmit={submit} className="flex flex-col gap-1">
              <div className="mb-2.5 flex gap-2">
                <Button
                  type="button"
                  variant={mode === "origin" ? "primary" : "ghost"}
                  icon={<Anchor className="size-4" />}
                  onClick={() => setMode("origin")}
                  className="flex-1"
                >
                  {origin ? `${origin.lat.toFixed(2)}, ${origin.lon.toFixed(2)}` : "Set origin"}
                </Button>
                <Button
                  type="button"
                  variant={mode === "destination" ? "primary" : "ghost"}
                  icon={<MapPin className="size-4" />}
                  onClick={() => setMode("destination")}
                  className="flex-1"
                >
                  {destination ? `${destination.lat.toFixed(2)}, ${destination.lon.toFixed(2)}` : "Set destination"}
                </Button>
              </div>
              {pointWarning(originCheck) && (
                <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-caution">
                  <AlertTriangle className="size-3 shrink-0" />
                  Origin {pointWarning(originCheck)} — pick a point further offshore.
                </p>
              )}
              {pointWarning(destinationCheck) && (
                <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-caution">
                  <AlertTriangle className="size-3 shrink-0" />
                  Destination {pointWarning(destinationCheck)} — pick a point further offshore.
                </p>
              )}
              <p className="mb-2.5 text-[11px] text-ink-dim">
                Chart clicks set the {mode === "origin" ? "origin" : "destination"} pin — click the other button to switch.
              </p>

              <div className="grid grid-cols-[1.3fr_1fr] gap-x-3">
                <Field label="Vessel class">
                  {(id) => (
                    <select
                      id={id}
                      value={vesselClass}
                      onChange={(e) => setVesselClass(e.target.value as VesselClass)}
                      className={inputClass}
                    >
                      {(Object.keys(VESSEL_LABELS) as VesselClass[]).map((v) => (
                        <option key={v} value={v} className="bg-shelf-2">
                          {VESSEL_LABELS[v]}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label="Speed">
                  {(id) => (
                    <input
                      id={id} type="number" min={1} step={0.5} value={speedKn}
                      onChange={(e) => setSpeedKn(Number(e.target.value))} className={inputClass}
                    />
                  )}
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-x-3">
                <Field label="Draft (optional)" hint="Deepest of class if blank">
                  {(id) => (
                    <input
                      ref={draftRef}
                      id={id} type="number" min={0.1} step={0.1} value={draftM} placeholder="m"
                      onChange={(e) => setDraftM(e.target.value)} className={inputClass}
                    />
                  )}
                </Field>
                <Field label="Departure (optional)" hint="Defaults to now">
                  {(id) => (
                    <input
                      id={id} type="datetime-local" value={departure}
                      onChange={(e) => setDeparture(e.target.value)} className={inputClass}
                    />
                  )}
                </Field>
              </div>
              <Field label="Fuel burn (optional)" hint="L/h — leave blank to skip the estimate">
                {(id) => (
                  <input
                    id={id} type="number" min={0.1} step={0.1} value={fuelBurnLph} placeholder="L/h"
                    onChange={(e) => setFuelBurnLph(e.target.value)} className={inputClass}
                  />
                )}
              </Field>

              <Button
                type="submit" variant="primary" className="mt-1"
                disabled={!origin || !destination || loading}
                icon={<Navigation className="size-4" />}
              >
                {loading ? "Charting" : "Plan voyage"}
              </Button>
            </form>
          </Panel>

          {signedIn && savedVoyages && savedVoyages.length > 0 && (
            <Panel title="Saved voyages" dense>
              <ul className="flex flex-col gap-2">
                {savedVoyages.map((v) => (
                  <li key={v.id} className="flex items-center justify-between gap-2 rounded-lg border border-hairline/70 px-2.5 py-2 text-xs">
                    <button type="button" onClick={() => loadSavedVoyage(v)} className="min-w-0 flex-1 text-left">
                      <span className="block truncate font-medium text-ink">{v.name ?? v.id}</span>
                      <span className="text-[10px] text-ink-dim">{new Date(v.departure_at).toLocaleString("en-GB", { timeZone: "UTC" })} UTC</span>
                    </button>
                    <div className="flex items-center gap-1">
                      <Button
                        type="button" variant="ghost" disabled={voyageBusyId === v.id}
                        icon={v.watch_id ? <BellOff className="size-3.5" aria-hidden="true" /> : <Bell className="size-3.5" aria-hidden="true" />}
                        onClick={() => togglePromote(v)}
                        title={v.watch_id ? "Stop watching this voyage" : "Watch this voyage for hazards"}
                      >
                        {v.watch_id ? "Watched" : "Watch"}
                      </Button>
                      <Button
                        type="button" variant="ghost" disabled={voyageBusyId === v.id}
                        icon={<Trash2 className="size-3.5" aria-hidden="true" />}
                        onClick={() => removeSavedVoyage(v.id)}
                        aria-label="Delete saved voyage"
                      >
                        <span className="sr-only">Delete</span>
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {tide && (
            <Panel title={`Berthing window — ${tide.station_name}`}>
              {/* Which station answered matters now that the roster is
                  national: the nearest one can be the destination port itself
                  or a hundred miles up the coast, and only five of the fourteen
                  quote chart datum — `tide.datum` is the hint on Range. */}
              <ReadoutGrid cols={2}>
                <Readout label="Tide" value={tide.tidal_state} hint={tide.spring_neap} />
                <Readout
                  label="Range"
                  value={tide.range_m != null ? tide.range_m.toFixed(1) : "—"}
                  unit={tide.range_m != null ? "m" : undefined}
                  hint={tide.datum}
                />
                <Readout
                  label="Next high"
                  value={tide.next_high ? new Date(tide.next_high.when).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) : "—"}
                  unit="UTC"
                />
                <Readout
                  label="Next low"
                  value={tide.next_low ? new Date(tide.next_low.when).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) : "—"}
                  unit="UTC"
                />
              </ReadoutGrid>

              {/* Predicted vs observed. Shown only when a gauge is actually
                  in range — INCOIS runs 6 nationally, so most of the coast
                  legitimately has none, and an absent gauge says so. */}
              <div className="mt-4 border-t border-hairline pt-3">
                {tide.observed_cross_check.available &&
                tide.observed_cross_check.source_kind === "satellite_altimetry" ? (
                  <>
                    <p className="mb-2 flex items-baseline justify-between gap-3 text-xs">
                      <span className="text-ink-dim">
                        Satellite altimetry — no gauge in range
                      </span>
                      <Badge tone="caution">not an in-situ reading</Badge>
                    </p>
                    <ReadoutGrid cols={2}>
                      <Readout
                        label="Sea-level anomaly"
                        value={tide.observed_cross_check.sea_level_anomaly_m ?? "—"}
                        unit="m"
                        hint={tide.observed_cross_check.dataset}
                      />
                      <Readout
                        label="Dynamic topography"
                        value={tide.observed_cross_check.absolute_dynamic_topography_m ?? "—"}
                        unit="m"
                      />
                    </ReadoutGrid>
                    {tide.observed_cross_check.note && (
                      <p className="mt-2 text-[11px] text-ink-dim">{tide.observed_cross_check.note}</p>
                    )}
                  </>
                ) : tide.observed_cross_check.available ? (
                  <>
                    <p className="mb-2 flex items-baseline justify-between gap-3 text-xs">
                      <span className="text-ink-dim">
                        Observed at {tide.observed_cross_check.station_name}
                        {tide.observed_cross_check.distance_km != null
                          ? ` · ${tide.observed_cross_check.distance_km} km`
                          : ""}
                      </span>
                      {tide.observed_cross_check.tsunami_trigger_state && (
                        <Badge
                          tone={
                            tide.observed_cross_check.tsunami_trigger_state === "NORMAL"
                              ? "neutral"
                              : "no-go"
                          }
                        >
                          {/* INCOIS's own state, carried verbatim. ORCA does
                              not threshold or interpret it. */}
                          tsunami: {tide.observed_cross_check.tsunami_trigger_state.toLowerCase()}
                        </Badge>
                      )}
                    </p>
                    <ReadoutGrid cols={3}>
                      <Readout
                        label="Observed"
                        value={tide.observed_cross_check.observed_level_m ?? "—"}
                        unit="m"
                      />
                      <Readout
                        label="Predicted"
                        value={tide.observed_cross_check.predicted_astronomical_m ?? "—"}
                        unit="m"
                      />
                      <Readout
                        label="Anomaly"
                        value={tide.observed_cross_check.sea_level_anomaly_m ?? "—"}
                        unit="m"
                        hint={tide.observed_cross_check.observed_at_ist}
                      />
                    </ReadoutGrid>
                  </>
                ) : (
                  <p className="text-[11px] text-ink-dim">
                    {tide.observed_cross_check.note ??
                      "No INCOIS tide gauge in range — these heights are predicted only."}
                  </p>
                )}
              </div>
            </Panel>
          )}
        </div>

        <div className="flex flex-col gap-4">
          <MapView
            className="h-[440px] min-h-[380px] lg:h-[500px] w-full rounded-2xl shadow-xl ring-1 ring-hairline overflow-hidden print:hidden"
            defaultCollapsedSounding={true}
            showLayerPanel={false}
            showRegionSwitcher={false}
            onPointClick={handlePointClick}
            routeGeoJson={plan?.route_layer?.geojson}
            pins={pins}
          />

          {error && <ErrorState title="Voyage plan failed" body={error} />}

          {!plan && !error && (
            <p className="flex items-center gap-2 rounded-lg border border-dashed border-hairline px-3.5 py-2.5 text-xs text-ink-dim">
              <Navigation className="size-3.5 shrink-0" />
              Every leg is classified on real bathymetry, boundary, MPA, sea-state and lightning data — never a straight-line guess.
            </p>
          )}

          {plan && (
            <>
              <VerdictBadge verdict={plan.verdict} summary={plan.verdict_reason}>
                <div className="mt-3">
                  <ConfidenceMeter tier={plan.confidence.score} />
                </div>
              </VerdictBadge>

              {/* P1.2 — the assumed draft, above the waypoint table, with the
                  correction one tap away. */}
              {plan.draft_disclosure && (
                <div className="flex items-start gap-2 rounded-lg border border-caution/35 bg-caution/5 px-3.5 py-2.5 text-xs text-ink-muted">
                  <Navigation className="mt-0.5 size-3.5 shrink-0 text-caution" aria-hidden="true" />
                  <span>
                    <span className="font-semibold text-ink">Assumed draft.</span> {plan.draft_disclosure}{" "}
                    <button
                      type="button"
                      onClick={() => draftRef.current?.focus()}
                      className="underline underline-offset-2 transition-colors hover:text-ink"
                    >
                      Enter your draft
                    </button>
                  </span>
                </div>
              )}

              {/* Checklist P0 #2's own evidence: the direct line was blocked
                  and ORCA chose an alternate, not just reported the block. */}
              {plan.rerouted && (
                <div className="flex items-start gap-2 rounded-lg border border-ocean-cyan/30 bg-ocean-cyan/10 px-3.5 py-2.5 text-xs text-ink-muted">
                  <Navigation className="mt-0.5 size-3.5 shrink-0 text-ocean-cyan" aria-hidden="true" />
                  <span>
                    <span className="font-semibold text-ink">Rerouted.</span> The direct line was blocked, so this
                    plan is the best clearing alternate ORCA found — see the reason above for which one and why.
                  </span>
                </div>
              )}

              {plan.alternatives_tried.length > 0 && (
                <details className="rounded-lg border border-hairline/70 bg-shelf-1/30 px-3.5 py-2.5 text-xs text-ink-dim">
                  <summary className="cursor-pointer font-medium text-ink-muted">
                    {plan.alternatives_tried.length} alternate route{plan.alternatives_tried.length === 1 ? "" : "s"} checked
                  </summary>
                  <ul className="mt-2 space-y-1">
                    {plan.alternatives_tried.map((a) => (
                      <li key={a.strategy} className="flex items-center justify-between gap-3">
                        <span className="capitalize">{a.strategy.replace(/_/g, " ")}</span>
                        <span className="flex items-center gap-2">
                          <Badge tone={a.verdict === "NO_GO" ? "no-go" : a.verdict === "CAUTION" ? "caution" : "go"}>
                            {a.verdict}
                          </Badge>
                          <span data-readout>+{a.added_nm.toFixed(1)} nm</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {plan.route_layer_dropped.length > 0 && (
                <ErrorState
                  title="Route layer degraded"
                  body={`The map overlay for this route failed ORCA's own validation and was dropped: ${plan.route_layer_dropped.join("; ")}. The waypoint table below is still the full, real result.`}
                />
              )}

              {/* P5.24 — nearest safe harbour (the closest ICG rescue
                  station to the destination, same roster a distress call
                  uses) and the fuel-burn estimate, which stays an honest
                  MISSING rather than a guess when no burn rate was given. */}
              <Panel title="Passage summary">
                <ReadoutGrid cols={plan.nearest_safe_harbour ? 4 : 2}>
                  <Readout label="Total distance" value={plan.segments.reduce((sum, s) => sum + s.distance_nm, 0).toFixed(1)} unit="nm" />
                  <Readout
                    label="Fuel estimate"
                    value={plan.fuel_estimate_liters != null ? plan.fuel_estimate_liters.toFixed(0) : "MISSING"}
                    unit={plan.fuel_estimate_liters != null ? "L" : undefined}
                    hint={plan.fuel_estimate_liters == null ? "No burn rate supplied" : `at ${plan.fuel_burn_lph} L/h`}
                  />
                  {plan.nearest_safe_harbour && (
                    <>
                      <Readout
                        label="Nearest safe harbour"
                        value={plan.nearest_safe_harbour.name}
                        hint={plan.nearest_safe_harbour.kind}
                      />
                      <Readout
                        label="Bearing / distance"
                        value={`${plan.nearest_safe_harbour.bearing_deg.toFixed(0)}° / ${plan.nearest_safe_harbour.distance_nm.toFixed(1)} nm`}
                        hint={plan.nearest_safe_harbour.eta_hours != null ? `~${plan.nearest_safe_harbour.eta_hours.toFixed(1)} h at cruise speed` : undefined}
                      />
                    </>
                  )}
                </ReadoutGrid>
              </Panel>

              <Panel
                title="Waypoints"
                action={
                  <div className="flex items-center gap-2.5 print:hidden">
                    {routeProvenance && <SourceChip dataset={routeProvenance.dataset} acquisitionTimestamp={routeProvenance.acquisition_timestamp || new Date().toISOString()} />}
                    <Button
                      type="button" variant="ghost" icon={<Download className="size-3.5" aria-hidden="true" />}
                      onClick={() => downloadText(`orca-voyage-${plan.voyage_id}.gpx`, planToGpx(plan), "application/gpx+xml")}
                    >
                      GPX
                    </Button>
                    <Button
                      type="button" variant="ghost" icon={<Download className="size-3.5" aria-hidden="true" />}
                      onClick={() => downloadText(`orca-voyage-${plan.voyage_id}.csv`, planToCsv(plan), "text/csv")}
                    >
                      CSV
                    </Button>
                    <Button type="button" variant="ghost" icon={<Printer className="size-3.5" aria-hidden="true" />} onClick={() => window.print()}>
                      Print
                    </Button>
                    {signedIn && (
                      <Button type="button" variant="ghost" icon={<Save className="size-3.5" aria-hidden="true" />} onClick={saveVoyage} disabled={savingVoyage}>
                        {savingVoyage ? "Saving" : "Save voyage"}
                      </Button>
                    )}
                  </div>
                }
              >
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-ink-dim">
                        <th className="pb-2 pr-3 font-medium">Leg</th>
                        <th className="pb-2 pr-3 font-medium">Distance</th>
                        <th className="pb-2 pr-3 font-medium">ETA (UTC)</th>
                        <th className="pb-2 pr-3 font-medium">UKC</th>
                        <th className="pb-2 pr-3 font-medium">Hs</th>
                        <th className="pb-2 pr-3 font-medium">Status</th>
                        <th className="pb-2 font-medium">Detail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {plan.segments.map((s) => (
                        <tr key={s.segment_id} className="border-t border-hairline">
                          <td className="py-1.5 pr-3 text-ink-muted">{s.segment_id}</td>
                          <td className="py-1.5 pr-3" data-readout>{s.distance_nm.toFixed(1)} nm</td>
                          <td className="py-1.5 pr-3" data-readout>
                            {new Date(s.eta).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })}
                          </td>
                          <td className="py-1.5 pr-3" data-readout>
                            {s.depth_m != null ? `${(s.depth_m - plan.draft_m).toFixed(1)}m` : "—"}
                          </td>
                          <td className="py-1.5 pr-3" data-readout>{s.wave_height_m != null ? `${s.wave_height_m.toFixed(1)}m` : "—"}</td>
                          <td className="py-1.5 pr-3">
                            <Badge tone={STATUS_TONE[s.status]}>{s.hazard_class}</Badge>
                          </td>
                          <td className="py-1.5 text-ink-muted">{s.detail}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </>
          )}
        </div>
      </div>
    </PageBody>
  );
}

export default function VoyagePage() {
  return (
    <Suspense fallback={null}>
      <VoyageContent />
    </Suspense>
  );
}
