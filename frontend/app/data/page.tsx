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
import { API_BASE } from "../lib/apiBase";

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

// Researcher export (plan §4 D2 Day 13 / exit criterion 2) — the same facts
// as the fisherman verdict, as a cited table whose every row carries dataset
// + acquisition timestamp + freshness. Built by Agent 9's export formatter.
function ExportButton() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function download(fmt: "csv" | "json") {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(`${API_BASE}/api/data/export?fmt=${fmt}`);
      if (!r.ok) throw new Error(`export failed (${r.status})`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `orca_export.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setErr("Export service did not respond.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex gap-1.5">
        {(["csv", "json"] as const).map((fmt) => (
          <button
            key={fmt}
            type="button"
            disabled={busy}
            onClick={() => download(fmt)}
            className="inline-flex items-center gap-1.5 rounded-sm border border-hairline px-2.5 py-1 text-xs text-ink-muted hover:border-hairline-strong hover:text-ink disabled:opacity-50"
          >
            <Download className="size-3.5" aria-hidden="true" />
            {busy ? "Preparing…" : `Cited facts (${fmt.toUpperCase()})`}
          </button>
        ))}
      </div>
      {err && <p className="text-[11px] text-no-go">{err}</p>}
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
            The export above is Agent&nbsp;9&rsquo;s formatter — every row carries its dataset,
            acquisition time and freshness. For the same facts as a written report, set your persona
            to <span className="text-ink-muted">Researcher</span> and ask a question on the home
            screen; Agent&nbsp;9 renders the methodology-first version. NetCDF export needs gridded
            arrays no agent produces yet.
          </p>
        </div>
      )}
    </PageBody>
  );
}
