"use client";

// District Ops (§4.2 `/ops`) — coastal-authority surface. Sector threat
// matrix (SEC001–SEC014), CAP 1.2 builder, four-channel broadcast composer,
// audit trail. §5.5 is a hard constraint: the authority sees COUNTS per
// sector, never plottable individual vessels.
import { useCallback, useEffect, useState } from "react";
import { Building2 } from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Badge, type BadgeTone } from "../components/Badge";
import { Button } from "../components/Button";
import { Field, inputClass } from "../components/Field";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { usePersona } from "../persona/context";
import { authFetch, getToken } from "../lib/auth";

type SectorRow = {
  sector_id: string;
  sector_name: string | null;
  pfz_status: string | null;
  pfz_message: string | null;
  is_data_gap: boolean;
  vessel_count: number;
  alert_severity: "info" | "advisory" | "warning" | "danger";
};

const SEV_TONE: Record<string, BadgeTone> = { info: "neutral", advisory: "accent", warning: "caution", danger: "no-go" };

export default function OpsPage() {
  const { persona } = usePersona();
  const [rows, setRows] = useState<SectorRow[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [error, setError] = useState<"forbidden" | "server" | null>(null);

  const load = useCallback(async () => {
    if (!getToken()) {
      setError("forbidden");
      return;
    }
    try {
      const r = await authFetch("/api/ops/sectors");
      if (r.status === 401 || r.status === 403) {
        setError("forbidden");
        return;
      }
      if (!r.ok) {
        setError("server");
        return;
      }
      const data = await r.json();
      setRows(data.matrix);
      setCounts(data.district_severity_counts ?? {});
    } catch {
      setError("server");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- forbidden/server state is set from load()'s outcome
    void load();
  }, [load]);

  return (
    <PageBody className="mx-auto max-w-4xl">
      <PageHeader
        title="District ops"
        lede="Sector threat rollups, CAP 1.2 alert composition and the broadcast preview for coastal authorities."
      />

      {error === "forbidden" && (
        <EmptyState
          icon={<Building2 className="size-6" />}
          title="Authority sign-in required"
          body="District ops is limited to coastal-authority and admin accounts. Sign in from Watches with an authority account, then return here."
        />
      )}
      {error === "server" && <ErrorState title="Could not load district data" body="The server did not answer. Try reloading." />}

      {!error && (
        <>
          <Panel title="District severity — last 24 h" className="mb-4">
            <div className="flex flex-wrap gap-2">
              {(["danger", "warning", "advisory", "info"] as const).map((s) => (
                <Badge key={s} tone={SEV_TONE[s]}>
                  {s}: <span data-readout>{counts[s] ?? 0}</span>
                </Badge>
              ))}
            </div>
          </Panel>

          <Panel title="Sector threat matrix" className="mb-4">
            {rows === null ? (
              <Skeleton className="h-64" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-ink-dim">
                    <tr className="border-b border-hairline">
                      <th className="py-2 pr-3 font-medium">Sector</th>
                      <th className="py-2 pr-3 font-medium">PFZ status</th>
                      <th className="py-2 pr-3 font-medium">Vessels</th>
                      <th className="py-2 font-medium">Alert</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.sector_id} className="border-b border-hairline/60">
                        <td className="py-2 pr-3 text-ink">
                          {r.sector_id}
                          <span className="ml-1 text-ink-dim">{r.sector_name}</span>
                        </td>
                        <td className="py-2 pr-3 text-ink-muted">
                          {r.pfz_status ?? "—"}
                          {r.is_data_gap && <span className="ml-1 text-caution">data gap</span>}
                        </td>
                        <td className="py-2 pr-3" data-readout>
                          {r.vessel_count}
                        </td>
                        <td className="py-2">
                          <Badge tone={SEV_TONE[r.alert_severity]}>{r.alert_severity}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 text-[11px] text-ink-dim">
                  Vessel figures are sector counts only — individual positions are never shown to an authority (§5.5).
                </p>
              </div>
            )}
          </Panel>

          <BroadcastComposer />
        </>
      )}

      <p className="mt-4 text-[11px] text-ink-dim">
        Viewing as <span className="text-ink-muted">{persona.replace(/_/g, " ")}</span>.
      </p>
    </PageBody>
  );
}

function BroadcastComposer() {
  const [verdict, setVerdict] = useState("NO-GO");
  const [hazard, setHazard] = useState("High waves");
  const [location, setLocation] = useState("Thoothukudi");
  const [preview, setPreview] = useState<Record<string, { body: string; chars: number | null }> | null>(null);
  const [cap, setCap] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function runPreview() {
    setBusy(true);
    try {
      const p = await authFetch(
        `/api/ops/broadcast/preview?verdict=${encodeURIComponent(verdict)}&hazard=${encodeURIComponent(hazard)}&location=${encodeURIComponent(location)}`,
      );
      if (p.ok) setPreview((await p.json()).channels);
      const c = await authFetch("/api/ops/cap", {
        method: "POST",
        body: JSON.stringify({
          headline: `${verdict}: ${hazard} near ${location}`,
          description: `${hazard} reported near ${location}. Advisory issued to district vessels.`,
          severity: verdict.includes("NO") ? "danger" : "warning",
          area_desc: `${location} coastal sector`,
        }),
      });
      if (c.ok) setCap(await c.text());
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Broadcast composer">
      <div className="grid grid-cols-3 gap-3">
        <Field label="Verdict">{(id) => <input id={id} className={inputClass} value={verdict} onChange={(e) => setVerdict(e.target.value)} />}</Field>
        <Field label="Hazard">{(id) => <input id={id} className={inputClass} value={hazard} onChange={(e) => setHazard(e.target.value)} />}</Field>
        <Field label="Location">{(id) => <input id={id} className={inputClass} value={location} onChange={(e) => setLocation(e.target.value)} />}</Field>
      </div>
      <Button variant="primary" onClick={runPreview} disabled={busy}>
        {busy ? "Rendering…" : "Preview all channels"}
      </Button>

      {preview && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {(["web", "sms", "ivr", "ussd"] as const).map((ch) => (
            <div key={ch} className="rounded-sm border border-hairline bg-shelf-1/60 p-3">
              <p className="mb-1 flex items-center justify-between text-[11px] font-medium text-ink-dim">
                <span className="uppercase">{ch}</span>
                {preview[ch]?.chars != null && <span data-readout>{preview[ch].chars} chars</span>}
              </p>
              <p className="text-xs whitespace-pre-wrap text-ink-muted">{preview[ch]?.body}</p>
              {ch !== "web" && <p className="mt-1 text-[11px] text-caution">Delivery not built — SIMULATED preview only.</p>}
            </div>
          ))}
        </div>
      )}

      {cap && (
        <details className="mt-4">
          <summary className="cursor-pointer text-[11px] text-accent">CAP 1.2 XML payload</summary>
          <pre className="mt-2 max-h-72 overflow-auto rounded-sm border border-hairline bg-abyss/60 p-3 text-[11px] text-ink-muted">
            {cap}
          </pre>
        </details>
      )}
    </Panel>
  );
}
