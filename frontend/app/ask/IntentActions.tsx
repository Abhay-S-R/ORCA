"use client";

// The one concrete thing a ROUTE / DIAGNOSTIC / REGULATORY / META / EXPORT /
// SUBSCRIPTION / ADMINISTRATIVE question asks for (P5.29, orca/intent_actions.py).
// Built deterministically by the backend; this only renders it. A watch is
// never created from the answer itself — only when the user presses the button.
import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Bell, Download, Info } from "lucide-react";
import { Button } from "../components/Button";
import { authFetch, getToken } from "../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type IntentAction = {
  intent: string;
  kind: "link" | "info" | "download" | "create_watch";
  text: string;
  label?: string;
  href?: string | null;
  watch?: { watch_type: string; lat: number; lon: number; radius_km: number };
};

export function IntentActions({ actions }: { actions: IntentAction[] }) {
  if (!actions.length) return null;
  return (
    <ul className="flex flex-col gap-2">
      {actions.map((a) => (
        <li key={a.intent} className="rounded-lg border border-hairline bg-shelf-1/60 p-3 text-xs">
          <p className="flex gap-1.5 text-ink-muted">
            <Info className="mt-0.5 size-3 shrink-0 text-accent" aria-hidden="true" />
            <span>{a.text}</span>
          </p>
          <ActionControl action={a} />
        </li>
      ))}
    </ul>
  );
}

function ActionControl({ action: a }: { action: IntentAction }) {
  const [watchState, setWatchState] = useState<"idle" | "busy" | "done" | "failed">("idle");

  if (a.kind === "create_watch" && a.watch) {
    if (!getToken()) {
      return (
        <p className="mt-2 text-[11px] text-ink-dim">
          <Link href="/login" className="text-accent hover:underline">Sign in</Link> to create this watch.
        </p>
      );
    }
    if (watchState === "done") return <p className="mt-2 text-[11px] text-go">Watch created — see Watches.</p>;
    return (
      <div className="mt-2 flex items-center gap-2">
        <Button
          variant="primary"
          icon={<Bell className="size-3.5" />}
          disabled={watchState === "busy"}
          onClick={async () => {
            setWatchState("busy");
            const r = await authFetch("/api/watches", { method: "POST", body: JSON.stringify(a.watch) }).catch(() => null);
            setWatchState(r?.ok ? "done" : "failed");
          }}
        >
          {a.label}
        </Button>
        {watchState === "failed" && <span className="text-[11px] text-caution">Could not create the watch.</span>}
      </div>
    );
  }

  if (!a.href || !a.label) return null;
  if (a.kind === "download" || a.href.startsWith("http")) {
    const href = a.href.startsWith("/api/") ? `${API_BASE}${a.href}` : a.href;
    return (
      <a href={href} target={a.kind === "download" ? undefined : "_blank"} rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-accent hover:underline">
        {a.kind === "download" ? <Download className="size-3" aria-hidden="true" /> : <ArrowRight className="size-3" aria-hidden="true" />}
        {a.label}
      </a>
    );
  }
  return (
    <Link href={a.href} className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-accent hover:underline">
      <ArrowRight className="size-3" aria-hidden="true" />
      {a.label}
    </Link>
  );
}
