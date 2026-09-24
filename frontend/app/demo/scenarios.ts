// P6.6 (orca_final §29.2) — the five scenario cards `/demo` ships. Every URL
// below runs the real, live, production `/query` graph — nothing here is a
// canned string. Scenarios 1 and 5 (this installment's minimum, per the
// plan's own text) are wired to real query strings; the query result is
// live for every node except, on scenario 1 only, the four data-fetch
// agents, which read a pinned prior real reading (`orca/demo_fixtures.py`)
// instead of today's live one — named on screen via each span's own
// "[pinned demo fixture, not live]" engine tag, never hidden.

export type ScenarioKind = "live" | "replay" | "stepper" | "link" | "not-yet-built";

export type Scenario = {
  id: string;
  title: string;
  summary: string;
  kind: ScenarioKind;
  // Built for a "live" scenario: the exact /query URL to run.
  buildUrl?: () => string;
  // Built for a "link" scenario: navigates to a different page rather than
  // running inline (e.g. P6.9 deep-links to /voyage, which already owns the
  // map/segment-table rendering a route needs — no point duplicating it here).
  href?: string;
};

function qs(params: Record<string, string>): string {
  return new URLSearchParams(params).toString();
}

export const SCENARIOS: Scenario[] = [
  {
    id: "safe_morning_mannar",
    kind: "live",
    title: "1 — Safe morning, Gulf of Mannar",
    summary:
      "A clean GO with the full provenance trail — pinned so the verdict holds regardless of today's actual weather, computed live by the real graph.",
    buildUrl: () =>
      `/query?${qs({
        q: "Is it safe to go out this morning?",
        lat: "8.9",
        lon: "78.5",
        persona: "fisherman",
        demo_scenario: "safe_morning_mannar",
      })}`,
  },
  {
    id: "imbl_border_crossing",
    kind: "stepper",
    title: "2 — IMBL border crossing, Palk Bay",
    summary:
      "A scripted vessel track stepped through the production geofence — sentinel.geofence_check() and evaluate_marine_safety() re-run at every position, so the band and verdict below are computed, never scripted: advisory at 12 nm, Tamil voice at 6 nm, CAUTION + SMS at 3 nm, NO-GO + full-screen takeover + reciprocal heading at 1 nm.",
  },
  {
    id: "cyclone_gaja_replay",
    kind: "replay",
    title: "3 — Cyclone Gaja replay (Nov 2018)",
    summary:
      "The real IBTrACS/ERA5 historical record, run through the same evaluate_marine_safety() the live path uses — GO → CAUTION → NO-GO, with missing data shown as missing, never smoothed.",
  },
  {
    id: "depth_blocked_detour",
    kind: "link",
    title: "4 — Depth-blocked passage with detour",
    summary:
      "A direct leg crossing a real shallow bank near Palk Bay — the blocked leg and the rerouted detour, both drawn on the real /voyage planner (bathymetry is static, so this needs no fixture pinning).",
    href: `/voyage?${qs({
      origin_lat: "9.20", origin_lon: "79.30",
      destination_lat: "9.20", destination_lon: "79.50",
    })}`,
  },
  {
    id: "distress_at_sea",
    kind: "live",
    title: "5 — Distress at sea",
    summary:
      "A real Tamil SOS phrase, matched by the same deterministic pattern list the live path uses — MRCC contact and the DAT-SG handoff payload, simulated and labelled as such.",
    buildUrl: () =>
      `/query?${qs({
        q: "படகு மூழ்குகிறது",
        lat: "8.8",
        lon: "78.14",
        persona: "fisherman",
      })}`,
  },
];
