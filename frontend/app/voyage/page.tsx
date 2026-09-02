import { Card } from "../components/Card";

// Voyage (§4.2 `/voyage`): route planner, waypoints, ETA. Voyage routing —
// the constraint-aware corridor — is explicitly out of scope entirely for
// Phase 1-2 (parent plan §7: "Voyage routing | Phase 3 | A* is out of scope
// entirely"). Honest stub, not a fake route.
export default function VoyagePage() {
  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Voyage</h1>
      <Card>
        <p className="text-sm text-black/60">
          Route planning is Phase 3 scope — the constraint-aware corridor algorithm doesn&apos;t exist yet
          anywhere in the plan before then.
        </p>
      </Card>
    </div>
  );
}
