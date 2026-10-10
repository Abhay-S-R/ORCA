"use client";

// Ask (§4.2, now at `/ask` — `/` itself is the public landing page) — the
// conversational entry point to a map-first product. A real multi-turn
// thread (was single-turn, replaced on every ask): the composer starts
// centered on a blank page and docks to the bottom of the thread once the
// first question lands, Claude-style. The map stays alongside the thread
// once it starts, collapsible, and the shared map instance follows each
// answer's context. (The map was removed on 2026-10-09, PLAN-ASK-1, and put
// back the same day at the team's request: the rest of PLAN-ASK stays.)
// The thread and the composer share ONE centred column of fixed maximum
// width (PLAN-ASK-3), so the input box is the same size whether the chat
// sidebar is open or closed.
//
// Past chats sit in a rail to the left (a drawer below lg, where a third
// column would squeeze the thread and the chart); they are kept in this
// browser for guests and in the account once signed in (./chatStore).
import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Compass, Fish, History, Maximize2, MapPin, Minimize2, PanelLeftOpen, ShieldCheck, Waves, Wind } from "lucide-react";
import { Button } from "../components/Button";
import { Greeting } from "../components/Greeting";
import { SavedLocationChips } from "../components/SavedLocationChips";
import { VesselChip } from "../components/VesselChip";
import { Skeleton } from "../components/States";
import { useVoiceInput } from "../components/VoiceInput";
import { useAuth } from "../lib/auth";
import { usePersona } from "../persona/context";
import { useLanguage } from "../language/context";
import { classifyQueryIntent, type QueryIntent } from "../lib/queryIntent";
import { Composer } from "./Composer";
import { ChatTurn } from "./ChatTurn";
import { ChatHistoryRail, CollapsedChatRail, iconButtonClass } from "./ChatHistoryRail";
import { accountStore, browserStore } from "./chatStore";
import { useAskThread, type Turn } from "./useAskThread";
import { useT } from "../i18n/useT";
import { useTour } from "../tour/useTour";
import { TourCard, TOUR_PRESET, TOUR_FOLLOWUP } from "../tour/TourCard";

const MapView = dynamic(() => import("../components/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full" />,
});

const INTENT_ICON: Record<QueryIntent, typeof Waves> = {
  fishing: Fish,
  boundary: Compass,
  safety: ShieldCheck,
  current: Waves,
  wave: Waves,
  wind: Wind,
  general: MapPin,
};

// Example queries in the fishermen & maritime users' own words
const EXAMPLES = [
  "Is it safe to venture into the sea tomorrow morning?",
  "Where is the nearest Potential Fishing Zone (PFZ) today?",
  "Which regions show high chlorophyll & favourable SST?",
  "What is the safest route considering sea-state conditions?",
];
const PRESETS = EXAMPLES.map((label) => ({ label, icon: INTENT_ICON[classifyQueryIntent(label)] }));

const RAIL_COLLAPSED_KEY = "orca-ask-rail-collapsed";
const MAP_WIDTH_KEY = "orca-ask-map-width";

export default function AskPage() {
  const { persona } = usePersona();
  const reduceMotion = useReducedMotion();
  const auth = useAuth();
  const t = useT();
  const { language } = useLanguage();
  const store = auth.status === "loading" ? null : auth.status === "signed_in" ? accountStore : browserStore;
  const [query, setQuery] = useState("");
  const [mapCollapsed, setMapCollapsed] = useState(false);
  const [mapWidth, setMapWidth] = useState(42);
  const [isResizing, setIsResizing] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);
  // Thread scrolling: threadRef is the scrollable container, latestTurnRef points
  // to the newest turn in the thread.
  const threadRef = useRef<HTMLDivElement>(null);
  const latestTurnRef = useRef<HTMLDivElement>(null);
  const prevTurnsLengthRef = useRef(0);
  const {
    turns,
    chatId,
    saveFailed,
    streaming,
    activeFocus,
    ask,
    rerun,
    showVersion,
    newChat,
    openChat,
  } = useAskThread(persona, store, () => setHistoryVersion((v) => v + 1));

  // The latest distress call in this chat with a position — pinned on the map
  // for as long as the chat is open (P4.16). No position, no pin: the answer
  // card already says the position is missing, the map never guesses one.
  const distressMarkers = useMemo(() => {
    // A regional default is where the backend computed, not where the caller is.
    const t = [...turns]
      .reverse()
      .find((x) => x.answer?.distress_flag && x.answer.user_location && x.answer.user_location.place_source !== "regional_default");
    const loc = t?.answer?.user_location;
    return t && loc ? [{ id: t.id, lat: loc.lat, lon: loc.lon, label: loc.place_name?.replace(/\b\p{L}/gu, (c) => c.toUpperCase()) ?? "your position" }] : [];
  }, [turns]);

  // P4.1 — the vessel class that actually drove the most recent verdict, so
  // the vessel button in the composer shows what is real rather than an assumption.
  const latestVesselClass = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i--) {
      const vc = turns[i].answer?.vessel_class;
      if (vc) return vc;
    }
    return null;
  }, [turns]);

  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage only exists after mount
      setRailCollapsed(localStorage.getItem(RAIL_COLLAPSED_KEY) === "1");
      const savedWidth = localStorage.getItem(MAP_WIDTH_KEY);
      if (savedWidth) {
        const val = Number(savedWidth);
        if (val >= 20 && val <= 75) setMapWidth(val);
      }
    } catch {
      /* storage disabled — the rail just starts expanded */
    }
  }, []);

  const startResizing = (e: React.PointerEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    if (!isResizing) return;

    const handlePointerMove = (e: PointerEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const rightDistance = rect.right - e.clientX;
      const pct = (rightDistance / rect.width) * 100;
      const clamped = Math.min(Math.max(pct, 20), 75);
      setMapWidth(Math.round(clamped));
      window.dispatchEvent(new Event("resize"));
    };

    const handlePointerUp = () => {
      setIsResizing(false);
      try {
        localStorage.setItem(MAP_WIDTH_KEY, String(mapWidth));
      } catch {
        /* storage disabled */
      }
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [isResizing, mapWidth]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  // When a query is asked, align the view to the top of that question/response
  // rather than auto-scrolling down during or after the answer.
  useEffect(() => {
    if (turns.length === 0) {
      prevTurnsLengthRef.current = 0;
      return;
    }
    if (turns.length > prevTurnsLengthRef.current) {
      prevTurnsLengthRef.current = turns.length;
      if (turns.length === 1) {
        threadRef.current?.scrollTo({ top: 0, behavior: "smooth" });
      } else if (latestTurnRef.current && threadRef.current) {
        const targetTop = latestTurnRef.current.offsetTop;
        threadRef.current.scrollTo({ top: targetTop, behavior: "smooth" });
      }
    }
  }, [turns.length]);

  // P4.9 — the five-step tour. Step 2 ("watch the agent strip stream") and
  // step 4 ("ask a follow-up") each end the moment their real query
  // finishes streaming — a streaming-true-then-false transition witnessed
  // while this page is mounted, not a turn count (which a resumed tour,
  // reloaded mid-step, cannot reconstruct reliably).
  const tour = useTour();
  const wasStreamingRef = useRef(false);
  useEffect(() => {
    void (async () => {
      const wasStreaming = wasStreamingRef.current;
      wasStreamingRef.current = streaming;
      if (!tour.active || !wasStreaming || streaming) return;
      if (tour.step === 2 || tour.step === 4) tour.advance();
    })();
    // tour.advance is stable (useTour's own useCallback); the whole `tour`
    // object is not, and re-runs on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tour.active, tour.step, tour.advance, streaming]);

  function collapseRail(collapsed: boolean) {
    setRailCollapsed(collapsed);
    try {
      localStorage.setItem(RAIL_COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      /* not remembered — nothing else depends on it */
    }
  }

  function submit(q: string, options?: { llm?: "off"; drop?: string[]; position?: { lat: number; lon: number } }) {
    ask(q, options);
    setQuery("");
  }

  // P3.10 — the most recent answer's resolved position, offered as what a
  // "+" tap on the saved-location chips bookmarks. A regional default isn't
  // a place the user chose, so it doesn't qualify (same exclusion
  // distressMarkers above already applies for the same reason).
  const lastResolvedLocation = useMemo(() => {
    const t = [...turns].reverse().find((x) => x.answer?.user_location && x.answer.user_location.place_source !== "regional_default");
    const loc = t?.answer?.user_location;
    return loc ? { lat: loc.lat, lon: loc.lon } : null;
  }, [turns]);

  function askSavedLocation(loc: { name: string; lat: number; lon: number }) {
    submit(`Is it safe near ${loc.name}?`, { position: { lat: loc.lat, lon: loc.lon } });
  }

  const lastQueryId = turns[turns.length - 1]?.answer?.query_id ?? null;

  // Whether the backend SHOULD still be holding context for turn `i`. Turns
  // before a deliberate reset (P2.14) don't count: the warning "earlier
  // messages have expired" is for a context that lapsed on its own, and
  // showing it after "forget that, start fresh" would tell the user the reset
  // they asked for was a failure.
  function hadEarlierAnswers(all: Turn[], i: number): boolean {
    const before = all.slice(0, i);
    const lastReset = before.map((t) => t.answer?.outcome).lastIndexOf("RESET");
    return before.slice(lastReset + 1).some((t) => t.answer && t.answer.outcome !== "RESET");
  }

  const voice = useVoiceInput({ onTranscriptConfirmed: submit, languageHint: language });
  const hasStarted = turns.length > 0;

  const history = (variant: "rail" | "drawer") => (
    <ChatHistoryRail
      store={store}
      auth={auth}
      activeChatId={chatId}
      version={historyVersion}
      variant={variant}
      onOpen={openChat}
      onNew={newChat}
      onDeleted={(id) => {
        if (id === chatId) newChat();
      }}
      onCollapse={() => collapseRail(true)}
      onClose={variant === "drawer" ? () => setDrawerOpen(false) : undefined}
    />
  );

  const historyButton = (
    <Button
      variant="ghost"
      className="lg:hidden"
      icon={<History className="size-3.5" />}
      onClick={() => setDrawerOpen(true)}
      aria-haspopup="dialog"
    >
      {t("common.chats")}
    </Button>
  );

  return (
    <div className="relative flex h-full min-h-0 gap-3 p-3 lg:p-4">
      <AnimatePresence initial={false}>
        {!railCollapsed && (
          <motion.div
            key="rail"
            layout={!reduceMotion}
            initial={reduceMotion ? false : { opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: "auto" }}
            exit={reduceMotion ? undefined : { opacity: 0, width: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="hidden min-h-0 overflow-hidden lg:flex"
          >
            {history("rail")}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Collapsed rail before a thread exists: a floating pill, not a
          reserved column, since the welcome screen has no header row to
          anchor an inline control to. Once a thread starts, the same
          control moves inline into the thread's own header (below) so it
          can never sit on top of that header's text. */}
      <AnimatePresence>
        {railCollapsed && !hasStarted && (
          <motion.div
            key="rail-expand"
            initial={reduceMotion ? false : { opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={reduceMotion ? undefined : { opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute top-3 left-3 z-20 hidden lg:block"
          >
            <CollapsedChatRail onExpand={() => collapseRail(false)} onNew={newChat} />
          </motion.div>
        )}
      </AnimatePresence>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex bg-abyss/50 lg:hidden" onClick={() => setDrawerOpen(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t("ask.chatHistoryDialog")}
            className="h-full w-[min(20rem,88vw)] border-r border-hairline bg-shelf-1 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {history("drawer")}
          </div>
        </div>
      )}

      {!hasStarted ? (
        <div className="relative flex min-w-0 flex-1 flex-col items-center justify-center gap-8">
          <div className="absolute top-0 left-0">{historyButton}</div>
          <div className="max-w-3xl text-center">
            <div className="mb-3 flex items-center justify-center gap-2">
              <span className="size-2 rounded-full bg-ocean-cyan beacon-pulse" aria-hidden="true" />
              <span className="font-mono text-[10px] font-bold tracking-widest text-ocean-cyan uppercase">
                SAGAR SARATHI INTELLIGENCE CONSOLE // VHF &amp; SATELLITE
              </span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">{t("ask.heading")}</h1>
            <div className="mt-1.5">
              <Greeting
                homePort={auth.status === "signed_in" ? auth.profile?.home_port : null}
                homePortName={auth.status === "signed_in" ? auth.profile?.home_port_name : null}
                fallback={t("ask.subheading")}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-2">
            <SavedLocationChips onSelect={askSavedLocation} addFrom={lastResolvedLocation} />
          </div>
          <Composer
            value={query}
            onChange={setQuery}
            onSubmit={submit}
            disabled={streaming}
            voice={voice}
            isFisherman={persona === "fisherman"}
            centered
            presets={PRESETS}
            leading={<VesselChip auth={auth} vesselClass={latestVesselClass} variant="icon" />}
          />
          {!tour.active && !tour.completed && (
            <button
              type="button"
              onClick={tour.start}
              className="text-xs font-medium text-ink-dim underline-offset-2 hover:text-accent hover:underline"
            >
              Take the 3-minute tour →
            </button>
          )}
        </div>
      ) : (
        <div ref={containerRef} className="relative flex min-h-0 min-w-0 flex-1 flex-col gap-4 lg:flex-row lg:gap-0">
          {/* Transparent drag barrier preventing pointer capture by iframes / map while resizing */}
          {isResizing && <div className="fixed inset-0 z-50 cursor-col-resize select-none" />}

          <div
            style={!mapCollapsed ? { flex: `0 0 calc(${100 - mapWidth}% - 0.75rem)` } : undefined}
            className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 lg:pr-2"
          >
          <div className="flex items-center justify-between gap-3 border-b border-hairline/60 pb-3">
            <div className="flex min-w-0 items-baseline gap-2">
              {railCollapsed && (
                <button
                  type="button"
                  onClick={() => collapseRail(false)}
                  aria-label={t("common.chats")}
                  title={t("common.chats")}
                  className={`${iconButtonClass} hidden self-center lg:grid`}
                >
                  <PanelLeftOpen className="size-3.5" aria-hidden="true" />
                </button>
              )}
              <h1 className="shrink-0 text-xs font-bold uppercase tracking-wider text-ink-dim">{t("ask.title")}</h1>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {saveFailed && (
                <span role="status" className="text-[11px] text-caution">
                  {t(saveFailed === "rejected" ? "ask.saveRejected" : "ask.notSaved")}
                </span>
              )}
              {historyButton}
              {mapCollapsed && (
                <button
                  type="button"
                  onClick={() => setMapCollapsed(false)}
                  aria-label={t("ask.expandMap")}
                  title={t("nav.map")}
                  className={iconButtonClass}
                >
                  <Maximize2 className="size-3.5" aria-hidden="true" />
                </button>
              )}
            </div>
          </div>

          {/* `relative` is load-bearing, not decoration: it makes this
              scroller the containing block for the absolutely positioned
              bits inside a turn (the agent pills' sr-only status spans).
              Without it those resolve against the panel wrapper below,
              escape this box's clipping, and stretch the page's own scroll
              area by the full height of the thread — the empty scroll
              space that appeared under the composer and history once a
              thread ran past one screen. The scroller spans the full width
              (so its scrollbar sits at the edge); the column inside it is
              the same centred max-w-4xl the composer uses. */}
          <div ref={threadRef} className="relative min-h-0 min-w-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-4xl flex-col gap-5 pr-2">
              {turns.map((turn, i) => (
                <div
                  key={turn.id}
                  ref={i === turns.length - 1 ? latestTurnRef : undefined}
                  className="w-full"
                >
                  <ChatTurn
                    turn={turn}
                    persona={persona}
                    hadEarlierAnswers={hadEarlierAnswers(turns, i)}
                    onRetry={() => ask(turn.askedQuery)}
                    onRerun={() => rerun(turn.id)}
                    onShowVersion={(index) => showVersion(turn.id, index)}
                    onFollowUp={submit}
                    />
                </div>
              ))}
            </div>
          </div>

          <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center gap-2">
            <SavedLocationChips onSelect={askSavedLocation} addFrom={lastResolvedLocation} />
          </div>
          <Composer
            value={query}
            onChange={setQuery}
            onSubmit={submit}
            disabled={streaming}
            voice={voice}
            isFisherman={persona === "fisherman"}
            centered={false}
            leading={<VesselChip auth={auth} vesselClass={latestVesselClass} variant="icon" />}
          />
          </div>

          {/* Resizer Splitter on Desktop (when map is expanded) */}
          {!mapCollapsed && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-valuenow={mapWidth}
              aria-valuemin={20}
              aria-valuemax={75}
              aria-label="Resize map and chat"
              tabIndex={0}
              onPointerDown={startResizing}
              onDoubleClick={() => {
                setMapWidth(42);
                try {
                  localStorage.setItem(MAP_WIDTH_KEY, "42");
                } catch {}
                window.dispatchEvent(new Event("resize"));
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowLeft") {
                  setMapWidth((w) => {
                    const next = Math.min(w + 3, 75);
                    try {
                      localStorage.setItem(MAP_WIDTH_KEY, String(next));
                    } catch {}
                    window.dispatchEvent(new Event("resize"));
                    return next;
                  });
                } else if (e.key === "ArrowRight") {
                  setMapWidth((w) => {
                    const next = Math.max(w - 3, 20);
                    try {
                      localStorage.setItem(MAP_WIDTH_KEY, String(next));
                    } catch {}
                    window.dispatchEvent(new Event("resize"));
                    return next;
                  });
                }
              }}
              title="Drag to resize map & chat · Double-click to reset (42%)"
              className={`hidden lg:flex w-3 shrink-0 cursor-col-resize select-none items-center justify-center group relative z-20 transition-colors ${
                isResizing ? "bg-ocean-cyan/20" : "hover:bg-shelf-2/60"
              }`}
            >
              <div
                className={`h-12 w-1 rounded-full transition-all flex flex-col items-center justify-center gap-1 ${
                  isResizing
                    ? "bg-ocean-cyan h-20 shadow-sm shadow-ocean-cyan/40"
                    : "bg-hairline group-hover:bg-ocean-cyan group-hover:h-16"
                }`}
              >
                <span className="size-0.5 rounded-full bg-white/70" />
                <span className="size-0.5 rounded-full bg-white/70" />
                <span className="size-0.5 rounded-full bg-white/70" />
              </div>
            </div>
          )}

          <motion.div
            layout={!reduceMotion && !isResizing}
            transition={isResizing ? { duration: 0 } : { duration: 0.25, ease: "easeOut" }}
            style={
              !mapCollapsed
                ? { width: `${mapWidth}%` }
                : undefined
            }
            className={
              mapCollapsed
                ? "pointer-events-none absolute inset-0 -z-10 overflow-hidden rounded-2xl opacity-0 lg:right-0 lg:left-auto"
                : "relative h-64 sm:h-72 w-full shrink-0 overflow-hidden rounded-2xl border border-hairline bg-shelf-1/60 shadow-2xl lg:h-full"
            }
          >
            {!mapCollapsed && (
              <div className="absolute top-2 left-2 z-10 flex items-center gap-1 rounded-lg border border-hairline/80 bg-shelf-1/90 p-1 shadow-sm backdrop-blur-sm">
                <button
                  type="button"
                  onClick={() => setMapCollapsed(true)}
                  aria-label={t("ask.collapseMap")}
                  aria-expanded={true}
                  title={t("ask.collapseMap")}
                  className="flex size-6 items-center justify-center rounded text-ink-dim hover:text-ocean-cyan"
                >
                  <Minimize2 className="size-3.5" />
                </button>

                <div className="hidden lg:flex items-center gap-0.5 border-l border-hairline/60 pl-1 ml-0.5">
                  <button
                    type="button"
                    onClick={() => {
                      setMapWidth(30);
                      try {
                        localStorage.setItem(MAP_WIDTH_KEY, "30");
                      } catch {}
                      window.dispatchEvent(new Event("resize"));
                    }}
                    title="Compact map (30%)"
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-medium transition-colors ${
                      mapWidth <= 35 ? "bg-ocean-cyan/20 text-ocean-cyan font-bold" : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    30%
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMapWidth(42);
                      try {
                        localStorage.setItem(MAP_WIDTH_KEY, "42");
                      } catch {}
                      window.dispatchEvent(new Event("resize"));
                    }}
                    title="Default split (42%)"
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-medium transition-colors ${
                      mapWidth > 35 && mapWidth < 55 ? "bg-ocean-cyan/20 text-ocean-cyan font-bold" : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    42%
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMapWidth(60);
                      try {
                        localStorage.setItem(MAP_WIDTH_KEY, "60");
                      } catch {}
                      window.dispatchEvent(new Event("resize"));
                    }}
                    title="Expanded map (60%)"
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-medium transition-colors ${
                      mapWidth >= 55 ? "bg-ocean-cyan/20 text-ocean-cyan font-bold" : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    60%
                  </button>
                </div>
              </div>
            )}

            {/* No layers on by default — layers are set precisely by query intent */}
            <div className="h-full w-full">
              <MapView
                className="h-full w-full"
                initialLayers={{ wind: false, currents: false, pfz: false, seamarks: false, watchBadges: false, cyclone: false }}
                queryFocus={activeFocus}
                distressMarkers={distressMarkers}
                showLayerPanel={false}
                showRegionSwitcher={false}
                showLegends={false}
                showSoundingHud={false}
              />
            </div>
          </motion.div>
        </div>
      )}

      <AnimatePresence>
        {tour.active && (
          <TourCard
            key={tour.step}
            step={tour.step}
            persona={persona}
            waiting={streaming}
            queryId={lastQueryId}
            onRunPreset={() => {
              submit(TOUR_PRESET[persona]);
              tour.advance();
            }}
            onNext={tour.advance}
            onRunFollowUp={() => submit(TOUR_FOLLOWUP)}
            onFinish={tour.skip}
            onSkip={tour.skip}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
