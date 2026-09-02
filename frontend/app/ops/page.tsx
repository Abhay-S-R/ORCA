"use client";

import { Card } from "../components/Card";
import { usePersona } from "../persona/context";

// District Ops (§4.2 `/ops`): threat matrix, CAP payload builder, broadcast
// composer, audit trail — coastal_authority's primary surface (parent plan
// §4.3). None of that is itemized in the Phase 1 day-by-day plan (plan §4
// S6); this stub exists so the route (and the persona visibility matrix
// gating it) is real today, without inventing an unscoped dashboard.
export default function OpsPage() {
  const { persona } = usePersona();
  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">District Ops</h1>
      <Card>
        <p className="text-sm text-black/60">
          The threat matrix, CAP payload builder and broadcast composer aren&apos;t Phase 1 scope. This
          route is reachable directly regardless of persona — you&apos;re currently viewing as{" "}
          <span className="font-medium">{persona.replace("_", " ")}</span>.
        </p>
      </Card>
    </div>
  );
}
