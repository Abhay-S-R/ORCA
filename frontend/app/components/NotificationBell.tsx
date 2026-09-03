"use client";

// The notification bell + toast surface (plan §4 D2 Day 17). Persistent on
// every screen (mounted in layout.tsx, like the SOS button). A crossing that
// Sentinel fires lands here live over SSE.
//
// aria-live="polite" for the feed; a distress-class alert (severity
// "danger") escalates the toast region to "assertive" per §4.11.
import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, X } from "lucide-react";
import { Badge, type BadgeTone } from "./Badge";
import {
  listNotifications,
  markAllRead,
  notificationStream,
  unreadCount,
  type OrcaNotification,
} from "../lib/watches";
import { getToken } from "../lib/auth";

const SEVERITY_TONE: Record<string, BadgeTone> = {
  info: "neutral",
  advisory: "accent",
  warning: "caution",
  danger: "no-go",
};

export function NotificationBell() {
  const [signedIn, setSignedIn] = useState(false);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<OrcaNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [toast, setToast] = useState<OrcaNotification | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    if (!getToken()) return;
    listNotifications()
      .then((feed) => setItems(feed))
      .catch(() => {});
    unreadCount()
      .then((count) => setUnread(count))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const sync = () => {
      const token = !!getToken();
      setSignedIn(token);
      if (!token) {
        setItems([]);
        setUnread(0);
      }
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
        setItems((prev) => [n, ...prev.filter((p) => p.id !== n.id)]);
        setUnread((c) => c + 1);
        setToast(n);
        if (toastTimer.current) clearTimeout(toastTimer.current);
        toastTimer.current = setTimeout(() => setToast(null), 8000);
      } catch {
        /* keep-alive / malformed frame */
      }
    };
    return () => es.close();
  }, [signedIn, refresh]);

  async function openFeed() {
    setOpen(true);
    if (unread > 0) {
      await markAllRead();
      setUnread(0);
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    }
  }

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

      {/* Bell — bottom-left so it never sits under the SOS button. */}
      <button
        type="button"
        onClick={openFeed}
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        className="fixed bottom-18 left-4 z-40 grid size-11 place-items-center rounded-full border border-hairline bg-shelf-1/95 text-ink-muted backdrop-blur-md transition-colors hover:text-ink sm:bottom-6"
      >
        <Bell className="size-5" strokeWidth={1.75} aria-hidden="true" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 grid min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold text-abyss">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          className="fixed inset-0 z-50 flex items-end justify-start bg-abyss/50 p-3 sm:items-start sm:pt-14 sm:pl-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="glass max-h-[70vh] w-[min(24rem,calc(100vw-1.5rem))] overflow-y-auto rounded-md p-3"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
          >
            <header className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-ink">Notifications</h2>
              <button type="button" aria-label="Close" onClick={() => setOpen(false)} className="text-ink-dim hover:text-ink">
                <X className="size-4" aria-hidden="true" />
              </button>
            </header>
            {items.length === 0 ? (
              <p className="py-6 text-center text-sm text-ink-dim">No notifications yet.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {items.map((n) => (
                  <li key={n.id} className="rounded-sm border border-hairline bg-shelf-1/60 p-2.5 text-sm">
                    <p className="flex items-center gap-2 font-medium text-ink">
                      <Badge tone={SEVERITY_TONE[n.severity] ?? "neutral"}>{n.severity}</Badge>
                      {n.title}
                    </p>
                    <p className="mt-1 text-ink-muted">{n.body}</p>
                    {typeof n.rendered_payload?.alert === "object" && n.rendered_payload.alert !== null && (
                      <p data-readout className="mt-1 rounded-sm bg-shelf-2/60 p-1.5 text-[11px] text-ink-dim">
                        {String((n.rendered_payload.alert as Record<string, unknown>).sagar_vani_sms ?? "")}
                      </p>
                    )}
                    <p className="mt-1 flex items-center gap-2 text-[11px] text-ink-dim">
                      <span data-readout>{new Date(n.created_at).toLocaleString("en-GB", { timeZone: "UTC" })} UTC</span>
                      {n.status !== "sent" && <span className="text-caution">SIMULATED</span>}
                      {n.query_id && (
                        <a href={`/reasoning?query_id=${n.query_id}`} className="text-accent underline">
                          trace
                        </a>
                      )}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </>
  );
}
