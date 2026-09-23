"use client";

// Alerts (§11.5 `/alerts`) — "what is ORCA warning me about right now, and
// what did it send me?" Active alerts (unread, severity-ranked) first, then
// history. `/safety` used to be the fisherman's landing page for exactly
// this question about a single verdict; this answers it for every alert
// Sentinel has fired, which is why the redirect points here (P4.1/P4.11).
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Bell, ChevronDown, Radio } from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { Badge, confidenceClass, confidenceLabel, type ConfidenceTier } from "../components/Badge";
import { Button } from "../components/Button";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { useAuth } from "../lib/auth";
import {
  listNotifications,
  markAllRead,
  markRead,
  notificationStream,
  SEVERITY_RANK,
  SEVERITY_TONE,
  type OrcaNotification,
} from "../lib/watches";

// What Sentinel actually put on the wire for this alert (sentinel_runtime.py
// `dispatch_decision`'s `rendered` dict) — read defensively since it is a
// free-form JSON column, not a typed contract across that boundary.
type AlertRendered = {
  snapshot?: {
    go_no_go?: string;
    wave_height_m?: number | null;
    wind_speed_ms?: number | null;
    lightning_active?: boolean;
    cyclone_alert?: string | null;
    confidence?: ConfidenceTier;
  };
  channels_requested?: string[];
  by_channel?: Record<string, { body?: string; status?: string; detail?: string }>;
};

function triggeringValue(snap: AlertRendered["snapshot"]): string | null {
  if (!snap) return null;
  if (snap.lightning_active) return "Lightning active";
  if (snap.cyclone_alert) return `Cyclone alert: ${snap.cyclone_alert}`;
  if (typeof snap.wave_height_m === "number") return `Wave height ${snap.wave_height_m.toFixed(1)} m`;
  if (typeof snap.wind_speed_ms === "number") return `Wind speed ${snap.wind_speed_ms.toFixed(1)} m/s`;
  return null;
}

function AlertRow({ n, onRead }: { n: OrcaNotification; onRead: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const rendered = (n.rendered_payload ?? {}) as AlertRendered;
  const value = triggeringValue(rendered.snapshot);
  const confidence = rendered.snapshot?.confidence;

  return (
    <li>
      <Panel dense>
        <button
          type="button"
          onClick={() => {
            setOpen((v) => !v);
            if (!n.read) onRead(n.id);
          }}
          aria-expanded={open}
          className="flex w-full items-start justify-between gap-3 text-left"
        >
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-2">
              <Badge tone={SEVERITY_TONE[n.severity]}>{n.severity}</Badge>
              <span className="text-sm font-medium text-ink">{n.title}</span>
              {!n.read && <span className="size-1.5 rounded-full bg-accent" aria-label="unread" />}
            </p>
            <p className="mt-1 text-sm text-ink-muted">{n.body}</p>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-dim">
              {value && <span data-readout>{value}</span>}
              <span data-readout>{new Date(n.created_at).toLocaleString("en-GB", { timeZone: "UTC" })} UTC</span>
              {confidence && <span className={confidenceClass(confidence)}>{confidenceLabel(confidence)}</span>}
              {n.status !== "sent" && <span className="text-caution">{n.status.toUpperCase()}</span>}
            </p>
          </div>
          <ChevronDown className={`size-4 shrink-0 text-ink-dim transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>

        {open && (
          <div className="mt-3 flex flex-col gap-3 border-t border-hairline pt-3 text-xs">
            {n.query_id && (
              <Link href={`/reasoning?query_id=${n.query_id}`} className="w-fit text-accent underline">
                Open the full trace for this alert
              </Link>
            )}

            {/* P4.13 — the verbatim payload actually rendered for every
                channel the user had enabled on this watch, not just the
                one that was the primary dispatch target. */}
            {rendered.by_channel && Object.keys(rendered.by_channel).length > 0 && (
              <div>
                <p className="mb-1.5 font-semibold text-ink-dim uppercase tracking-wide">What was sent</p>
                <dl className="flex flex-col gap-2">
                  {Object.entries(rendered.by_channel).map(([channel, c]) => (
                    <div key={channel} className="rounded-sm border border-hairline bg-shelf-2/50 p-2">
                      <div className="flex items-center justify-between gap-2">
                        <dt className="font-mono text-[10px] uppercase tracking-wide text-ink-dim">{channel}</dt>
                        <dd>
                          <span className={c.status === "sent" ? "text-go" : "text-caution"}>
                            {(c.status ?? "unknown").toUpperCase()}
                          </span>
                        </dd>
                      </div>
                      {c.body && <p data-readout className="mt-1 text-ink-muted">{c.body}</p>}
                      {c.detail && c.status !== "sent" && <p className="mt-1 text-ink-dim">{c.detail}</p>}
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </div>
        )}
      </Panel>
    </li>
  );
}

export default function AlertsPage() {
  const auth = useAuth();
  const [items, setItems] = useState<OrcaNotification[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    listNotifications()
      .then((feed) => {
        setItems(feed);
        setError(false);
      })
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (auth.status !== "signed_in") return;
    load();
    const es = notificationStream();
    if (!es) return;
    es.onmessage = (ev) => {
      try {
        const n: OrcaNotification = JSON.parse(ev.data);
        setItems((prev) => [n, ...(prev ?? []).filter((p) => p.id !== n.id)]);
      } catch {
        /* keep-alive / malformed frame */
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [auth.status, load]);

  function onRead(id: string) {
    setItems((prev) => (prev ? prev.map((n) => (n.id === id ? { ...n, read: true } : n)) : prev));
    void markRead(id);
  }

  async function onReadAll() {
    setItems((prev) => (prev ? prev.map((n) => ({ ...n, read: true })) : prev));
    await markAllRead();
  }

  if (auth.status === "loading") return null;
  if (auth.status === "signed_out") {
    return (
      <PageBody className="mx-auto max-w-md">
        <PageHeader title="Alerts" lede="Sign in to see what ORCA is warning you about." />
        <Link href="/login?next=/alerts" className="text-accent underline">
          Sign in
        </Link>
      </PageBody>
    );
  }

  const active = (items ?? [])
    .filter((n) => !n.read)
    .sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] || b.created_at.localeCompare(a.created_at));
  const history = (items ?? [])
    .filter((n) => n.read)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader
        title="Alerts"
        lede="Active alerts first, ranked by severity, then history — with exactly what was sent on every channel."
        action={
          active.length > 0 ? (
            <Button variant="ghost" onClick={() => void onReadAll()}>
              Mark all read
            </Button>
          ) : undefined
        }
      />

      {error && <ErrorState title="Could not reach the ORCA API" body="Start the backend, then reload this page." />}
      {!error && items === null && (
        <div className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      )}

      {!error && items !== null && items.length === 0 && (
        <EmptyState icon={<Bell className="size-6" />} title="No alerts yet" body="Sentinel watches your subscriptions and speaks up here the moment something crosses a threshold." />
      )}

      {!error && items !== null && items.length > 0 && (
        <div className="flex flex-col gap-5">
          {active.length > 0 && (
            <section>
              <h2 className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-dim">
                <Radio className="size-3.5 text-accent" aria-hidden="true" />
                Active ({active.length})
              </h2>
              <ul className="flex flex-col gap-2">
                {active.map((n) => (
                  <AlertRow key={n.id} n={n} onRead={onRead} />
                ))}
              </ul>
            </section>
          )}

          {history.length > 0 && (
            <section>
              <h2 className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-dim">
                <AlertTriangle className="size-3.5" aria-hidden="true" />
                History
              </h2>
              <ul className="flex flex-col gap-2">
                {history.map((n) => (
                  <AlertRow key={n.id} n={n} onRead={onRead} />
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </PageBody>
  );
}
