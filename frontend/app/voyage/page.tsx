"use client";

// Voyage (D3 plan §5) — plan a corridor, not just check "now". Click the
// chart to drop origin/destination (or type coordinates), and ORCA returns a
// per-leg classified route: the same hazard cascade `/safety` runs for a
// single point, walked along the whole passage at each leg's own ETA.
import { useState } from "react";
import { Anchor, AlertTriangle, MapPin, Navigation } from "lucide-react";
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
};
type SourceProvenance = { dataset: string; acquisition_timestamp: string; freshness_minutes: number };
type VoyagePlanResponse = {
  voyage_id: string; origin: [number, number]; destination: [number, number];
  vessel_class: VesselClass; departure_time: string; segments: Segment[];
  verdict: Verdict; verdict_reason: string; confidence: { score: ConfidenceTier; rationale: string };
  route_layer: { geojson: RouteGeoJson; source_provenance: SourceProvenance[] } | null;
  route_layer_dropped: string[];
};
type Tide = {
  station_name: string; tidal_state: string; range_m: number | null; spring_neap: string;
  next_high: { when: string; height_m: number } | null; next_low: { when: string; height_m: number } | null;
  datum: string;
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

export default function VoyagePage() {
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
  const [departure, setDeparture] = useState("");

  const [plan, setPlan] = useState<VoyagePlanResponse | null>(null);
  const [tide, setTide] = useState<Tide | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!origin || !destination) return;
    setLoading(true);
    setError(null);
    setPlan(null);
    setTide(null);
    try {
      const res = await fetch(`${API_BASE}/api/voyage-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_lat: origin.lat, origin_lon: origin.lon,
          destination_lat: destination.lat, destination_lon: destination.lon,
          vessel_class: vesselClass, speed_kn: speedKn,
          draft_m: draftM ? Number(draftM) : null,
          departure_time: departure ? new Date(departure).toISOString() : null,
        }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = (await res.json()) as VoyagePlanResponse;
      setPlan(data);
      // Berthing window at the destination — same tide predictor `/safety`'s
      // sibling ocean-analytics surfaces already use, just pointed here.
      fetch(`${API_BASE}/api/tides?lat=${destination.lat}&lon=${destination.lon}`)
        .then((r) => r.json())
        .then(setTide)
        .catch(() => {});
    } catch {
      setError("Could not reach ORCA. Check the backend is running and try again.");
    } finally {
      setLoading(false);
    }
  }

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

      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <div className="flex flex-col gap-4">
          <Panel title="Route" dense>
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
                <Field label="Draft (optional)" hint="By vessel class">
                  {(id) => (
                    <input
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

              <Button
                type="submit" variant="primary" className="mt-1"
                disabled={!origin || !destination || loading}
                icon={<Navigation className="size-4" />}
              >
                {loading ? "Charting" : "Plan voyage"}
              </Button>
            </form>
          </Panel>

          {tide && (
            <Panel title="Berthing window at destination">
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
            </Panel>
          )}
        </div>

        <div className="flex flex-col gap-4">
          <MapView
            className="h-[440px] min-h-[380px] lg:h-[500px] w-full rounded-2xl shadow-xl ring-1 ring-hairline overflow-hidden"
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

              {plan.route_layer_dropped.length > 0 && (
                <ErrorState
                  title="Route layer degraded"
                  body={`The map overlay for this route failed ORCA's own validation and was dropped: ${plan.route_layer_dropped.join("; ")}. The waypoint table below is still the full, real result.`}
                />
              )}

              <Panel
                title="Waypoints"
                action={routeProvenance && <SourceChip dataset={routeProvenance.dataset} acquisitionTimestamp={routeProvenance.acquisition_timestamp || new Date().toISOString()} />}
              >
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-ink-dim">
                        <th className="pb-2 pr-3 font-medium">Leg</th>
                        <th className="pb-2 pr-3 font-medium">Distance</th>
                        <th className="pb-2 pr-3 font-medium">ETA (UTC)</th>
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
