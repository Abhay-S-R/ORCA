import { Navigation } from "lucide-react";
import { Planned } from "../components/Planned";

// Voyage (§4.2 `/voyage`) — the constraint-aware corridor. Explicitly out of
// scope before Phase 3 (§7: "Voyage routing | Phase 3 | A* is out of scope
// entirely"), so this is an honest stub rather than a drawn route.
export default function VoyagePage() {
  return (
    <Planned
      icon={<Navigation className="size-6" />}
      title="Voyage"
      lede="Route planning around your vessel draft, hazards and tidal berthing windows."
      needs="Route planning needs the constraint-aware corridor algorithm, which is Phase 3 work. A drawn route before that exists would be a guess that looks like advice."
    />
  );
}
