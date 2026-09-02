import { Eye } from "lucide-react";
import { Planned } from "../components/Planned";

// Watches (§4.2 `/watches`) — the Sentinel agent subscriber surface. Needs
// identity (§5.4, Phase 2) before it has anyone to notify.
export default function WatchesPage() {
  return (
    <Planned
      icon={<Eye className="size-6" />}
      title="Watches"
      lede="Standing alerts on a place you care about, sent when conditions there cross your thresholds."
      needs="A watch has to belong to someone, so this surface waits on accounts and vessel registration in Phase 2. The Sentinel agent that evaluates watches lands in Phase 3."
    />
  );
}
