"use client";

// Voyage (D3 plan §5) — plan a corridor, not just check "now". Click the
// chart to drop origin/destination (or type coordinates), and ORCA returns a
// per-leg classified route: the same hazard cascade `/safety` runs for a
// single point, walked along the whole passage at each leg's own ETA.
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, Anchor, Bell, BellOff, Droplets, Download, MapPin, Navigation, Printer, Route as RouteIcon, Save, Trash2 } from "lucide-react";
import { Badge, type ConfidenceTier, type Verdict } from "../components/Badge";
import { Button } from "../components/Button";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { Field, inputClass } from "../components/Field";
import { type RouteGeoJson } from "../components/MapView";
import { SeaRouteMap } from "./SeaRouteMap";
import { PageHeader, PageBody } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Readout, ReadoutGrid } from "../components/Readout";
import { SourceChip } from "../components/SourceChip";
import { ErrorState } from "../components/States";
import { VerdictBadge } from "../components/VerdictBadge";
import { getToken, useAuth } from "../lib/auth";
import { createVoyage, deleteVoyage, listVoyages, promoteVoyage, unpromoteVoyage, type Voyage } from "../lib/voyages";
import {
  computeSeaRoute,
  fetchFishingZones,
  fetchSeaPorts,
  type FishingZonesGeoJson,
  type SeaPort,
  type SeaRouteResult,
} from "../lib/seaRoute";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type VesselClass = "small_fishing" | "mechanized_trawler" | "cargo_vessel";
const VESSEL_LABELS: Record<VesselClass, string> = {
  small_fishing: "Small fishing boat",
  mechanized_trawler: "Mechanized trawler",
  cargo_vessel: "Cargo vessel",
};

type RoutePlanningMode = "port_to_zone" | "map_pick";
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
  fell_back: boolean;
  source_provenance: { dataset: string; acquisition_timestamp: string };
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

// Automatic maritime fuel burn rate formula based on vessel class and cruising speed.
// Marine power and fuel burn scale approximately quadratically with speed relative to 8-knot reference.
function calculateFuelBurnRate(vesselClass: VesselClass, speedKn: number): number {
  const baseRates: Record<VesselClass, number> = {
    small_fishing: 4.5,
    mechanized_trawler: 22.0,
    cargo_vessel: 110.0,
  };
  const base = baseRates[vesselClass] ?? 4.5;
  const s = Math.max(speedKn, 1);
  return Math.round(base * Math.pow(s / 8.0, 2) * 10) / 10;
}

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
<gpx version="1.1" creator="Sagar Sarathi" xmlns="http://www.topografix.com/GPX/1/1">
  <rte>
    <name>Sagar Sarathi voyage ${plan.voyage_id}</name>
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
  const auth = useAuth();

  // Home port from the user's profile — used to pre-fill port-to-zone mode
  const homePort = auth.status === "signed_in" ? auth.profile?.home_port ?? null : null;
  const homePortName = auth.status === "signed_in" ? auth.profile?.home_port_name ?? null : null;

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
  // Draft removed from UI — server always uses assumed deepest-of-class (safer).
  // The draft_disclosure banner in the results still shows the assumed value.
  const [departure, setDeparture] = useState("");
  // Fuel onboard — compared against the calculated fuel required; warns the
  // fisherman if they are taking insufficient fuel for the trip.
  const [fuelOnboardL, setFuelOnboardL] = useState("");

  // Automatic fuel burn rate derived from vessel class and speed
  const calculatedBurnRate = useMemo(
    () => calculateFuelBurnRate(vesselClass, speedKn),
    [vesselClass, speedKn]
  );

  // ── Route planning modes & coastal sea-route pickers ────────────────────
  const [routeMode, setRouteMode] = useState<RoutePlanningMode>("port_to_zone");
  const [ports, setPorts] = useState<SeaPort[]>([]);
  const [zones, setZones] = useState<FishingZonesGeoJson | null>(null);
  const [fromPortId, setFromPortId] = useState("");
  const [toZoneId, setToZoneId] = useState("");
  // Coastal Warshall result — computed alongside the hazard audit when points
  // are known, shows obstacle-avoiding distance + ETA as extra context.
  const [coastalResult, setCoastalResult] = useState<SeaRouteResult | null>(null);

  const [plan, setPlan] = useState<VoyagePlanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // P5.20 UI — saved voyages. The backend (`/api/voyages`, promote-to-watch)
  // has been done and API-only since P5.20's own entry; this is the
  // frontend half that entry named as still missing.
  const [signedIn, setSignedIn] = useState(false);
  const [savedVoyages, setSavedVoyages] = useState<Voyage[] | null>(null);
  const [savingVoyage, setSavingVoyage] = useState(false);
  const [voyageBusyId, setVoyageBusyId] = useState<string | null>(null);

  // Fetch ports; zones are re-fetched whenever the home port's state is known
  // so we only load zones for the fisherman's own state (MFRA boundary rule).
  useEffect(() => {
    fetchSeaPorts().then(setPorts).catch(() => {});
  }, []);

  // Determine default home port:
  // 1. Closest port to auth.profile.home_port if available
  // 2. Port matching home_port_name or ID "IN_KOC" (Kochi, default captain home port)
  // 3. First port in Kerala or first available port
  const defaultHomePort = useMemo(() => {
    if (ports.length === 0) return null;
    if (homePort) {
      let closest: SeaPort | null = null;
      let minDist = Infinity;
      for (const p of ports) {
        const dlat = p.lat - homePort.lat;
        const dlng = p.lng - homePort.lon;
        const d = dlat * dlat + dlng * dlng;
        if (d < minDist) { minDist = d; closest = p; }
      }
      if (closest) return closest;
    }
    if (homePortName) {
      const q = homePortName.toLowerCase();
      const matched = ports.find(
        (p) => p.name.toLowerCase().includes(q) || q.includes(p.name.toLowerCase())
      );
      if (matched) return matched;
    }
    return ports.find((p) => p.id === "IN_KOC") || ports.find((p) => p.state === "Kerala") || ports[0];
  }, [ports, homePort, homePortName]);

  // Derive the active port's state from the selected port or default home port.
  // Used to filter fishing zones strictly to the state's 0-12 NM territorial waters under MFRA.
  const activePortState = useMemo(() => {
    if (fromPortId) {
      const p = ports.find((x) => x.id === fromPortId);
      if (p?.state) return p.state;
    }
    if (defaultHomePort?.state) return defaultHomePort.state;
    return "Kerala";
  }, [fromPortId, ports, defaultHomePort]);

  // Auto-set departure port to default home port when entering port_to_zone mode
  useEffect(() => {
    if (routeMode !== "port_to_zone" || ports.length === 0) return;
    if (!fromPortId && defaultHomePort) {
      setFromPortId(defaultHomePort.id);
      setOrigin({ lat: defaultHomePort.lat, lon: defaultHomePort.lng });
      setOriginCheck(null);
    }
  }, [routeMode, ports.length, fromPortId, defaultHomePort]);

  // Reload zones when active state changes — ALWAYS pass the active state in port_to_zone mode
  // so pan-India zones from other states are never loaded or shown.
  useEffect(() => {
    if (routeMode !== "port_to_zone") return;
    let cancelled = false;
    const targetState = activePortState || "Kerala";
    fetchFishingZones(targetState)
      .then((data) => {
        if (!cancelled) setZones(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [routeMode, activePortState]);

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
    setRouteMode("map_pick");
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
    if (from) { setOrigin(from); setRouteMode("map_pick"); }
    if (to) { setDestination(to); setRouteMode("map_pick"); }
    if (from && !to) setMode("destination");
  }, []);

  function handlePointClick(lat: number, lon: number) {
    if (routeMode !== "map_pick") {
      setRouteMode("map_pick");
    }
    const setPoint = mode === "origin" ? setOrigin : setDestination;
    const setCheck = mode === "origin" ? setOriginCheck : setDestinationCheck;
    setPoint({ lat, lon });
    setCheck(null);
    // Auto-advance to destination only on the very first origin pick
    // (when destination hasn't been placed yet). Once both pins exist,
    // S/D hotkeys control which one the next click will move.
    if (mode === "origin" && !destination) setMode("destination");
    fetch(`${API_BASE}/api/depth?lat=${lat}&lon=${lon}`)
      .then((r) => r.json())
      .then(setCheck)
      .catch(() => {});
  }

  // Hotkeys: S → pick source/origin, D → pick destination.
  // Active whenever map_pick mode is on; ignored when a text field has focus.
  useEffect(() => {
    if (routeMode !== "map_pick") return;
    function onKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
      const editable = (e.target as HTMLElement)?.isContentEditable;
      if (tag === "input" || tag === "textarea" || tag === "select" || editable) return;
      if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        setMode("origin");
      } else if (e.key === "d" || e.key === "D") {
        e.preventDefault();
        setMode("destination");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [routeMode]);

  async function runPlan(o: LatLon, d: LatLon) {
    setLoading(true);
    setError(null);
    setPlan(null);
    try {
      const depIso = departure ? new Date(departure).toISOString() : null;
      let seaReq;
      if (routeMode === "port_to_zone" && fromPortId && toZoneId) {
        seaReq = {
          mode: "port_to_zone" as const,
          port_from: fromPortId,
          zone_id: toZoneId,
          speed_knots: speedKn,
          departure: depIso,
        };
      } else {
        seaReq = {
          mode: "map_pick" as const,
          from_lat: o.lat,
          from_lng: o.lon,
          to_lat: d.lat,
          to_lng: d.lon,
          speed_knots: speedKn,
          departure: depIso,
        };
      }

      // Compute fresh coastal obstacle-avoiding sea route so voyage planning follows real sea waypoints
      let seaRes: SeaRouteResult | null = null;
      try {
        seaRes = await computeSeaRoute(seaReq);
        setCoastalResult(seaRes);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("on land")) {
          setError(msg);
          setLoading(false);
          return;
        }
        seaRes = null;
      }

      const res = await fetch(`${API_BASE}/api/voyage-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_lat: o.lat, origin_lon: o.lon,
          destination_lat: d.lat, destination_lon: d.lon,
          vessel_class: vesselClass, speed_kn: speedKn,
          draft_m: null,  // server uses assumed deepest-of-class; shown in draft_disclosure
          departure_time: depIso,
          fuel_burn_lph: calculatedBurnRate,
          waypoints: seaRes && seaRes.coords.length >= 2 ? seaRes.coords : null,
        }),
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        const detail = errJson?.detail || `Server returned ${res.status}`;
        throw new Error(detail);
      }
      const data = (await res.json()) as VoyagePlanResponse;
      setPlan(data);
      if (data.segments.length > 0) {
        const segCoords: [number, number][] = [
          [data.segments[0].start[0], data.segments[0].start[1]],
          ...data.segments.map((s) => [s.end[0], s.end[1]] as [number, number]),
        ];
        const coords = (data.rerouted || !seaRes || seaRes.coords.length < 2) ? segCoords : seaRes.coords;
        const nm = data.segments.reduce((sum, s) => sum + s.distance_nm, 0);
        setCoastalResult({
          coords,
          distance_nm: nm,
          distance_km: nm * 1.852,
          hours: nm / Math.max(speedKn, 0.1),
          eta: data.segments[data.segments.length - 1]?.eta ?? "",
          warnings: data.rerouted ? [data.verdict_reason] : (seaRes?.warnings ?? []),
        });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("Failed to fetch") || msg.includes("NetworkError") || msg.includes("Load failed")) {
        setError("Could not reach Sagar Sarathi. Check the backend is running and try again.");
      } else {
        setError(msg || "Failed to calculate voyage plan.");
      }
    } finally {
      setLoading(false);
    }
  }


  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!origin || !destination) return;
    await runPlan(origin, destination);
  }

  // Automatically compute and display the coastal obstacle-avoiding route on the map
  // as soon as endpoints are selected (port-to-zone, port-to-port, or map clicks).
  useEffect(() => {
    if (!origin || !destination) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resetting coastal result when endpoints clear
      setCoastalResult(null);
      return;
    }
    const depIso = departure ? new Date(departure).toISOString() : null;
    let seaReq;
    if (routeMode === "port_to_zone" && fromPortId && toZoneId) {
      seaReq = {
        mode: "port_to_zone" as const,
        port_from: fromPortId,
        zone_id: toZoneId,
        speed_knots: speedKn,
        departure: depIso,
      };
    } else {
      seaReq = {
        mode: "map_pick" as const,
        from_lat: origin.lat,
        from_lng: origin.lon,
        to_lat: destination.lat,
        to_lng: destination.lon,
        speed_knots: speedKn,
        departure: depIso,
      };
    }
    let cancelled = false;
    computeSeaRoute(seaReq)
      .then((res) => {
        if (!cancelled) {
          setCoastalResult(res);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setCoastalResult(null);
          const msg = err instanceof Error ? err.message : String(err);
          if (msg.includes("on land")) {
            setError(msg);
          }
        }
      });
    return () => {
      cancelled = true;
    };
  }, [routeMode, fromPortId, toZoneId, origin, destination, speedKn, departure]);

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

  const routeProvenance = plan?.route_layer?.source_provenance?.[0];

  const majorPorts = ports.filter((p) => p.type === "major");
  const minorPorts = ports.filter((p) => p.type !== "major" && p.type !== "fishing_harbour");
  const fishingPorts = ports.filter((p) => p.type === "fishing_harbour");
  // Strictly filter zones to the active port's state boundary (0-12 NM MFRA rule)
  const zoneList = useMemo(() => {
    const all = zones?.features ?? [];
    if (routeMode !== "port_to_zone" || !activePortState) return all;
    const st = activePortState.toLowerCase().trim();
    return all.filter((z) => {
      const sec = String(z.properties?.sector || "").toLowerCase();
      const name = String(z.properties?.name || "").toLowerCase();
      const zState = String(z.properties?.state || "").toLowerCase();
      return sec.includes(st) || name.includes(st) || zState === st;
    });
  }, [zones, routeMode, activePortState]);
  const stateBoundary = zones?.state_fishing_boundary ?? null;

  // Reset selected zone if it is outside the legally active state's waters
  useEffect(() => {
    if (routeMode !== "port_to_zone" || !toZoneId) return;
    const exists = zoneList.some((z) => z.properties?.id === toZoneId);
    if (!exists) {
      setToZoneId("");
      setDestination(null);
      setDestinationCheck(null);
    }
  }, [routeMode, zoneList, toZoneId]);

  // Zones grouped by sector (all within the active state)
  const zonesBySector = useMemo(() => {
    const groups: Record<string, typeof zoneList> = {};
    for (const z of zoneList) {
      const sec = z.properties.sector ? String(z.properties.sector).toUpperCase() : "REGIONAL OFFSHORE";
      if (!groups[sec]) groups[sec] = [];
      groups[sec].push(z);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [zoneList]);

  // Fuel warning: compare fuel onboard vs fuel required for the trip
  const fuelRequired = plan?.fuel_estimate_liters ?? null;
  const fuelOnboard = fuelOnboardL ? Number(fuelOnboardL) : null;
  const fuelShortfall = fuelRequired != null && fuelOnboard != null && fuelOnboard < fuelRequired
    ? fuelRequired - fuelOnboard
    : null;
  const fuelOk = fuelRequired != null && fuelOnboard != null && fuelOnboard >= fuelRequired;

  return (
    <PageBody className="mx-auto max-w-7xl">
      <PageHeader
        title="Plan a voyage"
        lede="Tap the chart to drop an origin and destination, or type coordinates. Sagar Sarathi classifies every leg — shallows, boundaries, protected areas, rough sea and lightning — at that leg's own arrival time, not just conditions right now."
      />

      <div className="grid gap-6 lg:grid-cols-[380px_1fr] print:block">
        <div className="flex flex-col gap-4">
          <Panel title="Route" dense className="print:hidden">
            <form onSubmit={submit} className="flex flex-col gap-1">
              {/* ── Mode selector ── */}
              <div className="mb-3 flex rounded-lg border border-hairline overflow-hidden text-xs font-semibold">
                {(["port_to_zone", "map_pick"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => {
                      setRouteMode(m);
                      setError(null);
                    }}
                    className={`flex-1 px-2 py-2 transition-colors ${
                      routeMode === m
                        ? "bg-ocean-cyan text-on-accent"
                        : "bg-shelf-1/60 text-ink-muted hover:bg-shelf-2/80"
                    }`}
                  >
                    {m === "port_to_zone" ? "Port → Zone" : "Map Pick"}
                  </button>
                ))}
              </div>

              {/* ── Mode 1: Port → Fishing Zone ── */}
              {routeMode === "port_to_zone" && (
                <>
                  {/* Home port lock notice */}
                  {(defaultHomePort?.name || homePortName) && (
                    <p className="mb-1.5 flex items-center gap-1.5 rounded-md border border-ocean-cyan/30 bg-ocean-cyan/10 px-2.5 py-1.5 text-[11px] text-ink">
                      <Anchor className="size-3 shrink-0 text-ocean-cyan" />
                      <span>Departing from your home port: <strong>{defaultHomePort?.name ?? homePortName} ({activePortState})</strong></span>
                    </p>
                  )}

                  <Field label="Departure port">
                    {(id) => (
                      <select
                        id={id}
                        value={fromPortId}
                        onChange={(e) => {
                          const pId = e.target.value;
                          setFromPortId(pId);
                          const p = ports.find((x) => x.id === pId);
                          if (p) {
                            setOrigin({ lat: p.lat, lon: p.lng });
                            setOriginCheck(null);
                          }
                        }}
                        className={inputClass}
                      >
                        <option value="">Select a port…</option>
                        {majorPorts.length > 0 && (
                          <optgroup label="Major Ports">
                            {majorPorts.map((p) => (
                              <option key={p.id} value={p.id} className="bg-shelf-2">
                                {p.name} ({p.state})
                              </option>
                            ))}
                          </optgroup>
                        )}
                        {minorPorts.length > 0 && (
                          <optgroup label="Minor Ports">
                            {minorPorts.map((p) => (
                              <option key={p.id} value={p.id} className="bg-shelf-2">
                                {p.name} ({p.state})
                              </option>
                            ))}
                          </optgroup>
                        )}
                        {fishingPorts.length > 0 && (
                          <optgroup label="Fishing Harbours">
                            {fishingPorts.map((p) => (
                              <option key={p.id} value={p.id} className="bg-shelf-2">
                                {p.name} ({p.state})
                              </option>
                            ))}
                          </optgroup>
                        )}
                      </select>
                    )}
                  </Field>

                  {/* State fishing boundary info — shown when zone list is state-filtered */}
                  {stateBoundary && (
                    <p className="mb-1 flex items-start gap-1.5 rounded-md border border-amber-400/30 bg-amber-400/10 px-2.5 py-1.5 text-[10px] text-ink-dim">
                      <AlertTriangle className="mt-0.5 size-3 shrink-0 text-amber-400" />
                      <span>
                        Showing zones within <strong>{stateBoundary.state}</strong> waters (0–{stateBoundary.max_fishing_nm} NM).
                        Fishing in another state&apos;s waters requires that state&apos;s licence (MFRA).
                      </span>
                    </p>
                  )}

                  <Field label="Fishing zone">
                    {(id) => (
                      <select
                        id={id}
                        value={toZoneId}
                        onChange={(e) => {
                          const zId = e.target.value;
                          setToZoneId(zId);
                          const z = zoneList.find((x) => x.properties.id === zId);
                          if (z) {
                            let lat = z.properties.entry_lat;
                            let lng = z.properties.entry_lng;
                            if (lat == null || lng == null) {
                              const geom = z.geometry as { type?: string; coordinates?: unknown };
                              if (geom?.type === "Polygon" && Array.isArray(geom.coordinates) && geom.coordinates[0]) {
                                const polyCoords = geom.coordinates[0] as [number, number][];
                                if (polyCoords[0]) {
                                  lng = polyCoords[0][0];
                                  lat = polyCoords[0][1];
                                }
                              } else if (geom?.type === "Point" && Array.isArray(geom.coordinates)) {
                                const pointCoords = geom.coordinates as [number, number];
                                lng = pointCoords[0];
                                lat = pointCoords[1];
                              }
                            }
                            if (lat != null && lng != null) {
                              setDestination({ lat, lon: lng });
                              setDestinationCheck(null);
                            }
                          }
                        }}
                        className={inputClass}
                      >
                        <option value="">Select fishing zone…</option>
                        {zonesBySector.map(([sector, list]) => (
                          <optgroup key={sector} label={`${sector} (${list.length})`}>
                            {list.map((z) => (
                              <option key={z.properties.id} value={z.properties.id} className="bg-shelf-2">
                                {z.properties.name} {z.properties.depth_m ? `[depth ${z.properties.depth_m}m]` : ""}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    )}
                  </Field>
                  <p className="mb-2 text-[11px] text-ink-dim">
                    Zones from INCOIS Potential Fishing Zone (PFZ) advisory, filtered to your state.
                  </p>
                </>
              )}

              {/* ── Mode 3: Map Pick ── */}
              {routeMode === "map_pick" && (
                <>
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
                </>
              )}

              <div className="grid grid-cols-[1.25fr_0.85fr_0.9fr] gap-x-2">
                <Field label="Vessel">
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
                <Field label="Speed (kn)">
                  {(id) => (
                    <input
                      id={id} type="number" min={1} step={0.5} value={speedKn}
                      onChange={(e) => setSpeedKn(Number(e.target.value))} className={inputClass}
                    />
                  )}
                </Field>
                <Field label="Fuel (L)">
                  {(id) => (
                    <input
                      id={id} type="number" min={0} step={1} value={fuelOnboardL} placeholder="Onboard"
                      onChange={(e) => setFuelOnboardL(e.target.value)} className={inputClass}
                    />
                  )}
                </Field>
              </div>
              <Field label="Departure time">
                {(id) => (
                  <input
                    id={id} type="datetime-local" value={departure}
                    onChange={(e) => setDeparture(e.target.value)} className={inputClass}
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
                      <span className="text-[10px] text-ink-dim">{new Date(v.departure_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST</span>
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

        </div>

        <div className="flex flex-col gap-4">
          <div className="print:hidden">
            <SeaRouteMap
              result={coastalResult}
              mapPickMode={routeMode === "map_pick"}
              pickTarget={mode}
              startPin={origin ? [origin.lat, origin.lon] : null}
              endPin={destination ? [destination.lat, destination.lon] : null}
              onMapClick={handlePointClick}
              zones={zones}
            />
          </div>

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

              {/* Checklist P0 #2's own evidence: the direct line was blocked
                  and ORCA chose an alternate, not just reported the block. */}
              {plan.rerouted && (
                <div className="flex items-start gap-2 rounded-lg border border-ocean-cyan/30 bg-ocean-cyan/10 px-3.5 py-2.5 text-xs text-ink-muted">
                  <Navigation className="mt-0.5 size-3.5 shrink-0 text-ocean-cyan" aria-hidden="true" />
                  <span>
                    <span className="font-semibold text-ink">Rerouted ({plan.verdict}).</span>{" "}
                    {plan.verdict_reason}
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
                  body={`The map overlay for this route failed Sagar Sarathi's own validation and was dropped: ${plan.route_layer_dropped.join("; ")}. The waypoint table below is still the full, real result.`}
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* ── Full-page width results: Passage Summary & Waypoints ── */}
      {plan && (
        <div className="mt-6 flex flex-col gap-6">
          <Panel title="Passage summary">
            {/* Single row of enlarged parameter boxes */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
              <div className="rounded-xl border border-hairline/80 bg-shelf-2/60 p-4 transition-colors hover:border-hairline-strong">
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-ink-dim">Distance</div>
                <div className="mt-1.5 flex items-baseline gap-1.5">
                  <span className="font-mono text-2xl font-extrabold tracking-tight text-ink" data-readout>
                    {plan.segments.reduce((sum, s) => sum + s.distance_nm, 0).toFixed(1)}
                  </span>
                  <span className="font-mono text-sm font-semibold text-ink-dim">nm</span>
                </div>
              </div>

              <div className="rounded-xl border border-hairline/80 bg-shelf-2/60 p-4 transition-colors hover:border-hairline-strong">
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-ink-dim">Time at sea</div>
                <div className="mt-1.5 flex items-baseline gap-1.5">
                  <span className="font-mono text-2xl font-extrabold tracking-tight text-ink" data-readout>
                    {coastalResult
                      ? coastalResult.hours < 24
                        ? `${coastalResult.hours.toFixed(1)} h`
                        : `${Math.floor(coastalResult.hours / 24)}d ${(coastalResult.hours % 24).toFixed(0)}h`
                      : "—"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-ink-dim">{speedKn} kn cruise</p>
              </div>

              <div className="rounded-xl border border-hairline/80 bg-shelf-2/60 p-4 transition-colors hover:border-hairline-strong">
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-ink-dim">Arrive by (IST)</div>
                <div className="mt-1.5 flex items-baseline gap-1.5">
                  <span className="font-mono text-xl sm:text-2xl font-extrabold tracking-tight text-ink" data-readout>
                    {coastalResult
                      ? new Date(coastalResult.eta).toLocaleString("en-IN", {
                          timeZone: "Asia/Kolkata",
                          day: "numeric",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "—"}
                  </span>
                </div>
              </div>

              <div className="rounded-xl border border-hairline/80 bg-shelf-2/60 p-4 transition-colors hover:border-hairline-strong">
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-ink-dim">Fuel needed</div>
                <div className="mt-1.5 flex items-baseline gap-1.5">
                  <span className="font-mono text-2xl font-extrabold tracking-tight text-ink" data-readout>
                    {fuelRequired != null ? `${fuelRequired.toFixed(0)}` : "—"}
                  </span>
                  <span className="font-mono text-sm font-semibold text-ink-dim">L</span>
                </div>
                <p className="mt-1 text-xs text-ink-dim">Rate ~{(plan.fuel_burn_lph ?? calculatedBurnRate).toFixed(1)} L/h</p>
              </div>

              <div className="rounded-xl border border-hairline/80 bg-shelf-2/60 p-4 transition-colors hover:border-hairline-strong">
                <div className="font-mono text-xs font-bold uppercase tracking-wider text-ink-dim">Nearest rescue</div>
                <div className="mt-1.5 flex items-baseline gap-1.5">
                  <span className="font-mono text-2xl font-extrabold tracking-tight text-ink" data-readout>
                    {plan.nearest_safe_harbour
                      ? `${plan.nearest_safe_harbour.distance_nm.toFixed(1)}`
                      : "—"}
                  </span>
                  {plan.nearest_safe_harbour && (
                    <span className="font-mono text-sm font-semibold text-ink-dim">nm</span>
                  )}
                </div>
                <p className="mt-1 truncate text-xs text-ink-dim" title={plan.nearest_safe_harbour?.name ?? "MRSC"}>
                  {plan.nearest_safe_harbour?.name ?? "MRSC"}
                </p>
              </div>
            </div>

            {/* Fuel shortage warning */}
            {fuelShortfall != null && fuelShortfall > 0 && (
              <div className="mt-3.5 flex items-start gap-2.5 rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm">
                <Droplets className="mt-0.5 size-4.5 shrink-0 text-red-400" aria-hidden="true" />
                <span>
                  <span className="font-bold text-red-400">⚠ NOT ENOUGH FUEL.</span>{" "}
                  You have <strong>{fuelOnboard} L</strong> onboard but this trip needs
                  {" "}<strong>{fuelRequired?.toFixed(0)} L</strong>.
                  You are short by <strong className="text-red-400">{fuelShortfall.toFixed(0)} L</strong>.
                  {" "}Do not sail until you have enough fuel for the full trip.
                </span>
              </div>
            )}
            {fuelOk && fuelRequired != null && (
              <div className="mt-3.5 flex items-center gap-2.5 rounded-lg border border-green-500/30 bg-green-500/8 px-4 py-2.5 text-sm text-ink-muted">
                <Droplets className="size-4 shrink-0 text-green-400" aria-hidden="true" />
                <span>Fuel OK — you have {fuelOnboard} L, trip needs {fuelRequired?.toFixed(0)} L.</span>
              </div>
            )}

            {/* Route warnings from coastal sea-route engine */}
            {coastalResult && coastalResult.warnings.filter((w) =>
              !w.startsWith("DISCLAIMER") && !w.startsWith("NOTE")
            ).map((w, i) => (
              <div key={i} className="mt-2.5 flex items-start gap-2 rounded-md border border-caution/40 bg-caution/8 px-3 py-2 text-xs text-ink-muted">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <span>{w}</span>
              </div>
            ))}
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
              <table className="w-full text-left text-sm md:text-base">
                <thead>
                  <tr className="border-b border-hairline text-ink font-semibold">
                    <th className="pb-3 pr-4 font-semibold">Leg #</th>
                    <th className="pb-3 pr-4 font-semibold">Distance</th>
                    <th className="pb-3 pr-4 font-semibold">Reach by (IST)</th>
                    <th className="pb-3 pr-4 font-semibold">Water Depth</th>
                    <th className="pb-3 pr-4 font-semibold">Safe?</th>
                    <th className="pb-3 font-semibold">What to watch</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {plan.segments.map((s) => (
                    <tr key={s.segment_id} className="hover:bg-shelf-1/40 transition-colors">
                      <td className="py-2.5 pr-4 font-mono font-medium text-ink-muted text-sm">{s.segment_id}</td>
                      <td className="py-2.5 pr-4 font-mono font-semibold text-ink text-sm md:text-base" data-readout>{s.distance_nm.toFixed(1)} nm</td>
                      <td className="py-2.5 pr-4 font-mono font-medium text-ink text-sm md:text-base" data-readout>
                        {new Date(s.eta).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })}
                      </td>
                      <td className="py-2.5 pr-4 font-mono font-medium text-ink text-sm md:text-base" data-readout>
                        {s.depth_m != null ? `${(s.depth_m - plan.draft_m).toFixed(1)}m` : "—"}
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge tone={STATUS_TONE[s.status]}>{s.hazard_class}</Badge>
                      </td>
                      <td className="py-2.5 text-sm md:text-[15px] text-ink-muted">{s.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
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
