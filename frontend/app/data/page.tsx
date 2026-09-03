"use client";

// Data (§4.2 `/data`) — the catalogue of everything ORCA is allowed to cite.
// Its job is to make "where did that number come from" answerable without
// asking anyone: every source, its authority tier, its freshness, and the
// fallback chain ORCA walks when it is down (Architecture §12.1).
import { useEffect, useState } from "react";
import { ChevronDown, Copy, Download } from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { ErrorState, Skeleton } from "../components/States";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type DataSource = {
  id: string;
  dataset: string;
  authority_tier: "TIER1" | "TIER2" | "TIER3";
  typical_freshness_minutes: number;
  covers: string[];
  fallback_chain: string[];
};

const TIER_LABEL: Record<DataSource["authority_tier"], string> = {
  TIER1: "Tier 1 · official",
  TIER2: "Tier 2 · institutional",
  TIER3: "Tier 3 · derived",
};

function freshness(min: number): string {
  if (min === 0) return "static reference dataset";
  if (min < 90) return `refreshed roughly every ${min} min`;
  if (min < 2880) return `refreshed roughly every ${Math.round(min / 60)} h`;
  return `refreshed roughly every ${Math.round(min / 1440)} d`;
}

function ExportButton() {
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <div>
      <button
        type="button"
        onClick={() =>
          fetch(`${API_BASE}/api/data/export?source_id=incois_pfz&fmt=csv`)
            .then((r) => r.json())
            .then((d) => setMsg(d.detail ?? "Export is not available yet."))
            .catch(() => setMsg("Export service did not respond."))
        }
        className="inline-flex items-center gap-1.5 rounded-sm border border-hairline px-2.5 py-1 text-xs text-ink-muted hover:border-hairline-strong hover:text-ink"
      >
        <Download className="size-3.5" aria-hidden="true" />
        Export catalogue (CSV)
      </button>
      {msg && <p className="mt-1.5 max-w-[52ch] text-[11px] text-ink-dim">{msg}</p>}
    </div>
  );
}

// API access panel (plan §4 D2 Day 13). A researcher's first question after
// "where did this come from" is "how do I get it myself" — this answers it
// with the real, copyable endpoints rather than pointing at a wiki.
function ApiAccessPanel({ source }: { source: DataSource }) {
  const [copied, setCopied] = useState<string | null>(null);
  const calls: Array<{ label: string; url: string }> = [
    { label: "This source's metadata + cascade", url: `${API_BASE}/api/data/${source.id}` },
    {
      label: `Which source ORCA picks for "${source.covers[0]}"`,
      url: `${API_BASE}/api/source-decision?data_type=${source.covers[0]}`,
    },
    {
      label: "Same, with this source forced down",
      url: `${API_BASE}/api/source-decision?data_type=${source.covers[0]}&down=${source.id}`,
    },
  ];

  return (
    <div className="mt-3 border-t border-hairline pt-2.5">
      <p className="mb-1.5 text-[11px] font-medium text-ink-dim">API access</p>
      <ul className="flex flex-col gap-1.5">
        {calls.map((c) => (
          <li key={c.url}>
            <p className="text-[11px] text-ink-dim">{c.label}</p>
            <button
              type="button"
              onClick={() => {
                navigator.clipboard?.writeText(c.url);
                setCopied(c.url);
              }}
              title="Copy to clipboard"
              className="mt-0.5 flex w-full items-center gap-1.5 overflow-x-auto rounded-sm border border-hairline bg-abyss/50 px-2 py-1 text-left"
            >
              <Copy className="size-3 shrink-0 text-ink-dim" aria-hidden="true" />
              <code data-readout className="whitespace-nowrap text-[11px] text-ink-muted">
                GET {c.url}
              </code>
              {copied === c.url && <span className="ml-auto shrink-0 text-[10px] text-go">copied</span>}
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[11px] text-ink-dim">
        All responses are JSON. Bulk CSV / NetCDF export arrives with the Agent&nbsp;9 export formatter.
      </p>
    </div>
  );
}

export default function DataPage() {
  const [sources, setSources] = useState<DataSource[] | null>(null);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/sources`)
      .then((r) => r.json())
      .then((d) => setSources(d.sources))
      .catch(() => setError(true));
  }, []);

  const byTier = (t: DataSource["authority_tier"]) => sources?.filter((s) => s.authority_tier === t) ?? [];

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="Data sources"
        lede="Every dataset ORCA can cite, its authority tier, how fresh it is, and the fallback chain it walks when a source is unavailable."
        action={sources ? <ExportButton /> : undefined}
      />

      {error && (
        <ErrorState
          title="Could not reach the ORCA API"
          body="The catalogue service did not respond. Start the backend, then reload this page."
        />
      )}

      {!sources && !error && (
        <div className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {sources && (
        <div className="flex flex-col gap-5">
          {(["TIER1", "TIER2", "TIER3"] as const).map((tier) => (
            <section key={tier}>
              <h2 className="mb-2 text-xs font-semibold tracking-wide text-ink-dim">{TIER_LABEL[tier]}</h2>
              <ul className="flex flex-col gap-2">
                {byTier(tier).map((s) => {
                  const isOpen = open === s.id;
                  return (
                    <li key={s.id}>
                      <Panel dense>
                        <button
                          type="button"
                          onClick={() => setOpen(isOpen ? null : s.id)}
                          aria-expanded={isOpen}
                          className="flex w-full items-baseline justify-between gap-3 text-left"
                        >
                          <span className="text-sm font-medium text-ink">{s.dataset}</span>
                          <ChevronDown
                            className={`size-4 shrink-0 text-ink-dim transition-transform ${isOpen ? "rotate-180" : ""}`}
                            aria-hidden="true"
                          />
                        </button>
                        <p className="mt-1.5 text-xs text-ink-dim">
                          Covers {s.covers.join(", ")} · {freshness(s.typical_freshness_minutes)}
                        </p>
                        {isOpen && (
                          <div className="mt-3 border-t border-hairline pt-2.5 text-xs">
                            <dl>
                              <dt className="text-ink-dim">Source id</dt>
                              <dd data-readout className="mt-0.5 text-ink-muted">{s.id}</dd>
                              <dt className="mt-2 text-ink-dim">Fallback chain (Architecture §12.1)</dt>
                              <dd className="mt-0.5 text-ink-muted">
                                {s.fallback_chain.length > 0 ? (
                                  <>{s.id} → {s.fallback_chain.join(" → ")} → local cache</>
                                ) : (
                                  "no live fallback — static reference geometry"
                                )}
                              </dd>
                            </dl>
                            <ApiAccessPanel source={s} />
                          </div>
                        )}
                      </Panel>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
          <p className="text-[11px] text-ink-dim">
            Per-query drill-down opens from any number in the product via its provenance popover.
            Researcher CSV / NetCDF export with the full metadata block is Agent 9&rsquo;s deliverable
            (Phase 2, team D1) and is wired to this surface but not yet returning files.
          </p>
        </div>
      )}
    </PageBody>
  );
}
