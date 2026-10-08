"use client";

// P6.7 (orca_final §7, PS-C8) — Scenario 2, the border-crossing
// demonstration. Steps through GET /api/replay/imbl-crossing's frames (each
// one a real sentinel.geofence_check()/evaluate_marine_safety() call against
// the real boundary geometry), escalating exactly as the plan's own text
// describes: an advisory chip on entering ADVISORY (12-6 nm), a spoken Tamil
// warning on entering WATCH (6-3 nm), a CAUTION banner + simulated SMS on
// entering WARNING (3-1 nm), and the real P4.12 full-screen takeover — with
// a reciprocal heading, this scenario's own bearing reading — on entering
// CRITICAL (<=1 nm). Nothing here is scripted to show a band; every band
// comes from the frame the backend just computed.
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, MessageSquareWarning, Play, RotateCcw, Volume2 } from "lucide-react";
import { Badge, type BadgeTone } from "../components/Badge";
import { Button } from "../components/Button";
import { MapView, type MapPin, type RouteGeoJson } from "../components/MapView";
import { ErrorState } from "../components/States";
import { CHART } from "../map/basemap";
import { API_BASE } from "../lib/apiBase";
import { useCriticalAlert } from "../lib/criticalAlert";

type Frame = {
  lat: number; lon: number;
  distance_nm: number; band: "CLEAR" | "ADVISORY" | "WATCH" | "WARNING" | "CRITICAL";
  line_name: string | null; between: [string | null, string | null] | null;
  bearing_deg: number | null; reciprocal_heading_deg: number | null;
  go_no_go: "GO" | "CAUTION" | "NO_GO"; status: string; reason: string;
};

const BAND_TONE: Record<Frame["band"], BadgeTone> = {
  CLEAR: "neutral", ADVISORY: "accent", WATCH: "cyan", WARNING: "caution", CRITICAL: "no-go",
};

// Same three-state colour every other route/corridor line in this app uses
// (voyage_route_layer's own contract) — the crossing reads as one continuous
// track, not a table row, and its colour is the real computed verdict, not a
// fixed "danger zone ahead" gradient.
const VERDICT_STATUS: Record<Frame["go_no_go"], "CLEAR" | "CAUTION" | "BLOCKED"> = {
  GO: "CLEAR", CAUTION: "CAUTION", NO_GO: "BLOCKED",
};
const VERDICT_COLOR: Record<Frame["go_no_go"], string> = {
  GO: CHART.go, CAUTION: CHART.caution, NO_GO: CHART.noGo,
};

const STEP_MS = 1400;

export function IMBLCrossing() {
  const [frames, setFrames] = useState<Frame[] | null>(null);
  const [index, setIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const { raise: raiseCriticalAlert, acknowledge } = useCriticalAlert();
  const spokenBandRef = useRef<Frame["band"] | null>(null);

  async function start() {
    setLoading(true);
    setError(false);
    acknowledge();
    spokenBandRef.current = null;
    try {
      const res = await fetch(`${API_BASE}/api/replay/imbl-crossing`);
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as { frames: Frame[] };
      setFrames(data.frames);
      setIndex(0);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setFrames(null);
    setIndex(-1);
    acknowledge();
  }

  // Auto-advance one position at a time, stopping at the last frame — never
  // looping back to CLEAR, which would misrepresent a one-way approach.
  useEffect(() => {
    if (!frames || index < 0 || index >= frames.length - 1) return;
    const id = setTimeout(() => setIndex((i) => i + 1), STEP_MS);
    return () => clearTimeout(id);
  }, [frames, index]);

  // Escalation side-effects, keyed to the CURRENT frame's band only (never
  // re-fired for a band already passed) — same band-entry rule
  // sentinel.detect_geofence_crossing uses on the live watch path.
  useEffect(() => {
    if (!frames || index < 0) return;
    const frame = frames[index];
    if (frame.band === "WATCH" && spokenBandRef.current !== "WATCH" && "speechSynthesis" in window) {
      spokenBandRef.current = "WATCH";
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance("எச்சரிக்கை. கடல் எல்லைக்கு அருகில் உள்ளீர்கள்."));
    }
    if (frame.band === "CRITICAL") {
      raiseCriticalAlert({
        kind: "boundary",
        level: "CRITICAL",
        distanceNm: frame.distance_nm,
        queryId: null,
        reciprocalHeadingDeg: frame.reciprocal_heading_deg,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires once per index change, raiseCriticalAlert is stable from context
  }, [frames, index]);

  // Hooks run before the early returns below (rules-of-hooks) — both are
  // no-ops (empty route, no pins) until a scenario is actually running.
  const seen = useMemo(() => (frames && index >= 0 ? frames.slice(0, index + 1) : []), [frames, index]);

  // The travelled track so far, as one line-string leg per step — each leg
  // coloured by the verdict it ends on, so the line itself visibly changes
  // colour from GO green through CAUTION amber to NO-GO red as the vessel
  // closes on the boundary, instead of a single flat colour end to end.
  const routeGeoJson: RouteGeoJson = useMemo(
    () => ({
      type: "FeatureCollection",
      features: seen.slice(1).map((f, i) => ({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [
            [seen[i].lon, seen[i].lat],
            [f.lon, f.lat],
          ],
        },
        properties: {
          segment_id: `leg-${i}`,
          status: VERDICT_STATUS[f.go_no_go],
          hazard_class: f.band,
          detail: f.reason,
          eta: "",
          distance_nm: f.distance_nm,
        },
      })),
    }),
    [seen],
  );

  const pins: MapPin[] = useMemo(() => {
    if (!frames || index < 0) return [];
    const start = frames[0];
    const frame = frames[index];
    return [
      { lat: start.lat, lon: start.lon, label: "Track start", color: CHART.eez },
      { lat: frame.lat, lon: frame.lon, label: `Vessel — ${frame.band}`, color: VERDICT_COLOR[frame.go_no_go] },
    ];
  }, [frames, index]);

  if (error) {
    return (
      <ErrorState
        title="Scenario data not found"
        body="GET /api/replay/imbl-crossing failed — check the backend is reachable."
        action={
          <Button variant="primary" icon={<Play className="size-3.5" />} onClick={start}>
            Retry
          </Button>
        }
      />
    );
  }

  if (!frames) {
    return (
      <Button variant="primary" icon={loading ? <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Play className="size-3.5" />} disabled={loading} onClick={start}>
        Run the scenario
      </Button>
    );
  }

  const frame = frames[index];

  return (
    <div className="space-y-4">
      {/* The cinematic piece: the real boundary-line layer under a travelled
          track that recolours leg by leg as the verdict changes, camera
          re-fitting to the growing route on every step (MapView's own
          existing routeGeoJson effect — no new camera logic here) — a
          moving vessel position, not a text row saying one happened. */}
      <div className="h-64 overflow-hidden rounded-xl border border-hairline/60 sm:h-80">
        <MapView
          className="h-full w-full"
          routeGeoJson={routeGeoJson}
          pins={pins}
          initialLayers={{ boundaryLines: true }}
          showLayerPanel={false}
          showRegionSwitcher={false}
          showLegends={false}
          showSoundingHud={false}
        />
      </div>

      <div className="flex items-center justify-between">
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <span className="font-mono">{frame.lat.toFixed(4)}N {frame.lon.toFixed(4)}E</span>
          <span>—</span>
          <span>{frame.distance_nm.toFixed(2)} nm from {frame.line_name ?? "the boundary"}</span>
        </div>
        <Button icon={<RotateCcw className="size-3.5" />} onClick={reset}>
          Reset
        </Button>
      </div>

      {/* ADVISORY (12-6 nm) — the earliest chip, well before the verdict
          itself ever changes (that stays GO until WARNING at 3 nm). */}
      {frame.band === "ADVISORY" && (
        <Badge tone="accent" icon={<AlertTriangle className="size-3" aria-hidden="true" />}>
          Advisory — approaching {frame.line_name}
        </Badge>
      )}

      {/* WATCH (6-3 nm) — spoken once on entry, per the effect above. */}
      {(frame.band === "WATCH" || frame.band === "WARNING" || frame.band === "CRITICAL") && (
        <div className="flex items-center gap-2 rounded-lg border border-ocean-cyan/40 bg-ocean-cyan/10 p-3 text-sm text-ocean-cyan">
          <Volume2 className="size-4 shrink-0" aria-hidden="true" />
          Tamil voice alert spoken on entering the WATCH band (6 nm).
        </div>
      )}

      {/* WARNING (3-1 nm) — CAUTION banner + a simulated SMS payload, never
          rendered as delivered (same discipline every dispatcher in this
          codebase uses for a channel with no real transport wired here). */}
      {(frame.band === "WARNING" || frame.band === "CRITICAL") && (
        <div className="space-y-2 rounded-lg border border-caution/45 bg-caution/10 p-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-caution">
            <MessageSquareWarning className="size-4 shrink-0" aria-hidden="true" />
            CAUTION — {frame.reason}
          </p>
          <p className="rounded-md border border-hairline/60 bg-shelf-1/60 p-2 font-mono text-[11px] text-ink-muted">
            [SAGAR SARATHI CAUTION] Approaching {frame.between?.filter(Boolean).join(" – ") ?? "the maritime boundary"}.
            {" "}{frame.distance_nm.toFixed(1)} nm remaining. — SIMULATED, no live SMS transport in this build.
          </p>
        </div>
      )}

      {/* CRITICAL (<=1 nm) — the real P4.12 full-screen takeover fires via
          the effect above; this card also states the verdict inline so the
          escalation reads correctly even once the takeover is acknowledged. */}
      {frame.band === "CRITICAL" && (
        <Badge tone="no-go" icon={<AlertTriangle className="size-3" aria-hidden="true" />}>
          NO-GO — {frame.reason}
          {frame.reciprocal_heading_deg != null && ` — reciprocal heading ${frame.reciprocal_heading_deg.toFixed(0)}°`}
        </Badge>
      )}

      <span className="block text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
        Full track log — the same data driving the map above
      </span>
      <div className="max-h-40 overflow-y-auto rounded-lg border border-hairline/60">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-shelf-2 text-[10px] uppercase tracking-wide text-ink-dim">
            <tr>
              <th className="px-3 py-2">Position</th>
              <th className="px-3 py-2">Distance</th>
              <th className="px-3 py-2">Band</th>
              <th className="px-3 py-2">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {seen.map((f, i) => (
              <tr key={i} className="border-t border-hairline/40">
                <td className="px-3 py-1.5 font-mono">{f.lat.toFixed(4)}, {f.lon.toFixed(4)}</td>
                <td className="px-3 py-1.5">{f.distance_nm.toFixed(2)} nm</td>
                <td className="px-3 py-1.5">
                  <Badge tone={BAND_TONE[f.band]}>{f.band}</Badge>
                </td>
                <td className="px-3 py-1.5">{f.go_no_go.replace("_", " ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
