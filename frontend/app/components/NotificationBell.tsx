"use client";

// The notification toast + bell (plan §4 D2 Day 17). Persistent on every
// screen (mounted in layout.tsx, like the SOS button). A crossing that
// Sentinel fires lands here live over SSE as a toast; the bell itself is a
// deep link to `/alerts` (P4.11) — the inline dropdown this used to open is
// gone, superseded by the full inbox rather than duplicating it.
//
// aria-live="polite" for the toast; a distress-class alert (severity
// "danger") escalates it to "assertive" per §4.11.
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, X } from "lucide-react";
import { Badge } from "./Badge";
import { notificationStream, unreadCount, SEVERITY_TONE, type OrcaNotification } from "../lib/watches";
import { getToken } from "../lib/auth";

export function NotificationBell() {
  const [signedIn, setSignedIn] = useState(false);
  const [unread, setUnread] = useState(0);
  const [toast, setToast] = useState<OrcaNotification | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    if (!getToken()) return;
    unreadCount()
      .then((count) => setUnread(count))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const sync = () => {
      const token = !!getToken();
      setSignedIn(token);
      if (!token) setUnread(0);
    };
    sync();
    window.addEventListener("orca:auth", sync);
    return () => window.removeEventListener("orca:auth", sync);
  }, []);

  useEffect(() => {
    if (!signedIn) return;
    refresh();
    const es = notificationStream();
    if (!es) return;
    es.onmessage = (ev) => {
      try {
        const n: OrcaNotification = JSON.parse(ev.data);
        setUnread((c) => c + 1);
        setToast(n);
        if (toastTimer.current) clearTimeout(toastTimer.current);
        toastTimer.current = setTimeout(() => setToast(null), 8000);
      } catch {
        /* keep-alive / malformed frame */
      }
    };
    es.onerror = () => {
      es.close();
    };
    return () => es.close();
  }, [signedIn, refresh]);

  if (!signedIn) return null;

  return (
    <>
      {/* Live toast region. assertive only for a danger-class alert. */}
      <div
        aria-live={toast?.severity === "danger" ? "assertive" : "polite"}
        className="pointer-events-none fixed top-3 right-3 z-50 flex w-[min(22rem,calc(100vw-1.5rem))] flex-col gap-2"
      >
        {toast && (
          <div className="glass pointer-events-auto rounded-md border-l-2 border-accent p-3 text-sm shadow-lg shadow-black/40">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="flex items-center gap-2 font-semibold text-ink">
                  <Badge tone={SEVERITY_TONE[toast.severity] ?? "neutral"}>{toast.severity}</Badge>
                  {toast.title}
                </p>
                <p className="mt-1 text-ink-muted">{toast.body}</p>
                {toast.status !== "sent" && (
                  <p className="mt-1 text-[11px] text-ink-dim">
                    Channel <span className="text-ink-muted">{toast.channel}</span> — SIMULATED, no message transmitted.
                  </p>
                )}
              </div>
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => setToast(null)}
                className="shrink-0 text-ink-dim hover:text-ink"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Bell — bottom-left so it never sits under the SOS button. Links to
          the full inbox rather than opening a second, smaller one here. */}
      <Link
        href="/alerts"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        className="fixed bottom-18 left-4 z-40 grid size-11 place-items-center rounded-full border border-hairline bg-shelf-1/95 text-ink-muted backdrop-blur-md transition-colors hover:text-ink sm:bottom-6"
      >
        <Bell className="size-5" strokeWidth={1.75} aria-hidden="true" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 grid min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold text-on-accent">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </Link>
    </>
  );
}
