import { LineChart } from "lucide-react";
import { Planned } from "../components/Planned";

// Trends (§4.2 `/trends`) — time-series, anomalies, the "why has catch
// declined" workspace. All of it is driven by Agent 5 (Ocean Analytics),
// which the plan defers to Phase 2.
export default function TrendsPage() {
  return (
    <Planned
      icon={<LineChart className="size-6" />}
      title="Trends"
      lede="Sea surface temperature, chlorophyll and catch-decline analysis over time."
      needs="Trends are produced by the Ocean Analytics agent, which lands in Phase 2. Rather than draw a chart with nothing behind it, this surface stays empty until that agent returns real series."
    />
  );
}
