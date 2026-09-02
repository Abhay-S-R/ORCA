"use client";

import { Building2 } from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/States";
import { usePersona } from "../persona/context";

// District Ops (§4.2 `/ops`) — the coastal authority surface: threat matrix,
// CAP payload builder, broadcast composer, audit trail. None of that is Phase
// 1 scope, so this route exists to prove the nav and visibility matrix are
// real without inventing an unscoped dashboard.
export default function OpsPage() {
  const { persona } = usePersona();

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="District ops"
        lede="Sector threat rollups, CAP alert composition and the broadcast queue for coastal authorities."
      />
      <EmptyState
        icon={<Building2 className="size-6" />}
        title="Not built yet"
        body="The threat matrix, CAP payload builder and broadcast composer are later-phase work. This route stays reachable on a direct visit whatever persona you select — nav visibility changes what is listed, never what you can open."
      />
      <p className="mt-3 text-xs text-ink-dim">
        Viewing as <span className="text-ink-muted">{persona.replace(/_/g, " ")}</span>.
      </p>
    </PageBody>
  );
}
