import { Card } from "../components/Card";

// Trends (§4.2 `/trends`): time-series, anomalies, "why has catch declined"
// workspace — all driven by Agent 5 (Ocean Analytics), which the plan
// explicitly defers to Phase 2 (plan §4 S4 intro — "Agent 5 is a Phase 2
// deliverable"). Honest stub over a fake chart with no data behind it.
export default function TrendsPage() {
  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Trends</h1>
      <Card>
        <p className="text-sm text-black/60">
          Time-series and anomaly analysis need Agent 5 (Ocean Analytics), which is Phase 2 scope. This
          surface renders once that agent lands.
        </p>
      </Card>
    </div>
  );
}
