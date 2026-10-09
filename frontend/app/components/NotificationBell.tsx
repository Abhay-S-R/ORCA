"use client";

// The notification bell — persistent on every screen (mounted in AppChrome).
// On a new alert:
//  1. A short chime plays via Web Audio (no file dependency).
//  2. A compact bubble pops above the bell with the alert title + body.
//  3. The unread badge count increments.
// The bell links to /alerts (the full inbox). The top-right toast is removed;
// the bubble here is the sole in-context alert surface.
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, X } from "lucide-react";
import { Badge } from "./Badge";
import {
  notificationStream,
  unreadCount,
  SEVERITY_TONE,
  type OrcaNotification,
} from "../lib/watches";
import { getToken } from "../lib/auth";

// ---------------------------------------------------------------------------
// Web Audio chime — two-tone "ding" using the OscillatorNode API.
// Runs only in the browser; gracefully no-ops if AudioContext is unavailable.
// ---------------------------------------------------------------------------
function playAlertChime(severity: OrcaNotification["severity"]) {
  try {
    const ctx = new (window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext)();

    // Frequency pairs per severity: info=soft, advisory=medium, warning/danger=urgent
    const [f1, f2] =
      severity === "danger"
        ? [880, 660]
        : severity === "warning"
        ? [660, 520]
        : severity === "advisory"
        ? [520, 440]
        : [440, 380];

    function tone(freq: number, startAt: number, duration: number) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, startAt);
      gain.gain.linearRampToValueAtTime(0.18, startAt + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, startAt + duration);
      osc.start(startAt);
      osc.stop(startAt + duration + 0.05);
    }

    const now = ctx.currentTime;
    tone(f1, now, 0.35);
    tone(f2, now + 0.28, 0.35);

    // Close context after tones complete to free resources.
    setTimeout(() => ctx.close(), 1200);
  } catch {
    // AudioContext blocked or unavailable — silent fallback.
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export function NotificationBell() {
  const [signedIn, setSignedIn] = useState(false);
  const [unread, setUnread] = useState(0);
  const [bubble, setBubble] = useState<OrcaNotification | null>(null);
  const bubbleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
        // Play chime
        playAlertChime(n.severity);
        // Show bubble above bell
        setBubble(n);
        if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
        bubbleTimer.current = setTimeout(() => setBubble(null), 8000);
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
    /*
     * Wrapper is position:fixed bottom-left.
     * - Mobile (< sm): bottom-18 so it floats above the mobile tab bar
     * - Desktop (sm+): bottom-6, clear of any UI chrome
     * The bubble grows upward from the bell (flex-col-reverse stacking).
     */
    <div className="fixed bottom-18 left-4 z-40 flex flex-col-reverse items-start gap-2 sm:bottom-6">
      {/* ── Alert bubble ── */}
      {bubble && (
        <div
          role="alert"
          aria-live={bubble.severity === "danger" ? "assertive" : "polite"}
          className="pointer-events-auto relative mb-1 w-[min(18rem,calc(100vw-5rem))] rounded-xl border border-hairline bg-shelf-1/95 p-3 shadow-xl shadow-black/30 backdrop-blur-md ring-1 ring-white/10 animate-in slide-in-from-bottom-2 duration-200 overflow-hidden"
        >
          {/* Severity accent strip */}
          <div
            className={`absolute left-0 top-0 h-full w-1 rounded-l-xl ${
              bubble.severity === "danger"
                ? "bg-no-go"
                : bubble.severity === "warning"
                ? "bg-caution"
                : bubble.severity === "advisory"
                ? "bg-accent"
                : "bg-ink-dim"
            }`}
            aria-hidden="true"
          />
          <div className="pl-2">
            <div className="flex items-start justify-between gap-2">
              <p className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-ink leading-snug">
                <Badge tone={SEVERITY_TONE[bubble.severity] ?? "neutral"}>
                  {bubble.severity}
                </Badge>
                {bubble.title}
              </p>
              <button
                type="button"
                aria-label="Dismiss alert"
                onClick={() => setBubble(null)}
                className="shrink-0 text-ink-dim hover:text-ink transition-colors"
              >
                <X className="size-3.5" aria-hidden="true" />
              </button>
            </div>
            <p className="mt-1 text-[11px] text-ink-muted leading-snug line-clamp-3">
              {bubble.body}
            </p>
            <Link
              href="/alerts"
              onClick={() => setBubble(null)}
              className="mt-1.5 inline-block text-[10px] text-ocean-cyan hover:underline"
            >
              View all alerts →
            </Link>
          </div>
        </div>
      )}

      {/* ── Bell button ── */}
      <Link
        href="/alerts"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        className="relative grid size-11 place-items-center rounded-full border border-hairline bg-shelf-1/95 text-ink-muted backdrop-blur-md transition-colors hover:text-ink"
      >
        <Bell
          className={`size-5 transition-all ${unread > 0 ? "text-ocean-cyan" : ""}`}
          strokeWidth={1.75}
          aria-hidden="true"
        />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 grid min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold text-on-accent">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </Link>
    </div>
  );
}
