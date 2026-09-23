"use client";

// Ask (§4.2, now at `/ask` — `/` itself is the public landing page) — the
// conversational entry point to a map-first product. A real multi-turn
// thread now (was single-turn, replaced on every ask): the composer starts
// centered on a blank page and docks to the bottom of the thread once the
// first question lands, Claude-style. The map stays alongside the thread
// once it starts, collapsible, and every answer's "view on map" chip can
// re-point the one shared map instance back to that answer's context.
//
// Past chats sit in a rail to the left (a drawer below lg, where a third
// column would squeeze the thread and the chart); they are kept in this
// browser for guests and in the account once signed in (./chatStore).
import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Compass, Fish, History, Maximize2, MapPin, Minimize2, PanelLeftOpen, Plus, ShieldCheck, Waves, Wind } from "lucide-react";
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
import { accountStore, browserStore, chatTitle } from "./chatStore";
import { useAskThread, type InheritedValue, type Turn } from "./useAskThread";
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
  current: Wind,
  wave: Waves,
  general: MapPin,
};

// Iconic PS SIH26176 queries in the fishermen & maritime users' own words
const EXAMPLES = [
  "Is it safe to venture into the sea tomorrow morning?",
  "Where is the nearest Potential Fishing Zone (PFZ) today?",
  "Which regions show high chlorophyll & favourable SST?",
  "What is the safest route considering sea-state conditions?",
];
const PRESETS = EXAMPLES.map((label) => ({ label, icon: INTENT_ICON[classifyQueryIntent(label)] }));

const RAIL_COLLAPSED_KEY = "orca-ask-rail-collapsed";

export default function AskPage() {
  const { persona } = usePersona();
  const reduceMotion = useReducedMotion();
  const auth = useAuth();
  const t = useT();
  const { language } = useLanguage();
  const store = auth.status === "loading" ? null : auth.status === "signed_in" ? accountStore : browserStore;
  const [query, setQuery] = useState("");
  const [mapCollapsed, setMapCollapsed] = useState(false);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);
  // Auto-scroll: threadRef is the scrollable container, threadBottomRef is a
  // zero-height sentinel at the end of the list. Scrolling the sentinel into
  // view on every turns/streaming change keeps the latest message visible
  // without manual scrolling — same mechanic as most chat UIs.
  const threadRef = useRef<HTMLDivElement>(null);
  const threadBottomRef = useRef<HTMLDivElement>(null);
  const {
    turns,
    chatId,
    saveFailed,
    streaming,
    activeFocus,
    setActiveFocus,
    ask,
    rerun,
    showVersion,
    newChat,
    openChat,
    setRenderedAs,
    applyRender,
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
  // the chip above the composer shows what is real rather than an assumption.
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
    } catch {
      /* storage disabled — the rail just starts expanded */
    }
  }, []);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  // Scroll to the bottom sentinel whenever a new turn is added or the
  // streaming state changes (each chunk that arrives extends the answer).
  // `block: "end"` keeps the sentinel flush at the bottom of the container
  // rather than centering it, and `behavior: "smooth"` gives the same feel
  // as the Framer Motion entrance animation on each new ChatTurn.
  useEffect(() => {
    threadBottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, streaming]);

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

  // P2.9 — the user rejecting a value this answer inherited from an earlier
  // turn. Re-asks the SAME question and tells the backend which inheritance to
  // refuse. The first version rewrote the question ("… (not Kannur — I have not
  // said where yet)"), which put the place name straight back into the text,
  // so the resolver found Kannur again — and without the name the session
  // handed it back anyway. Neither layer can be talked out of a carry-over by
  // the wording of the question; only a parameter reaches the code that does it.
  function dropInherited(turn: Turn, value: InheritedValue) {
    submit(turn.askedQuery, { drop: [value.field] });
  }

  const voice = useVoiceInput({ onTranscriptConfirmed: submit, languageHint: language });
  const hasStarted = turns.length > 0;
  const firstQuestion = turns[0]?.askedQuery ?? null;

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
                ORCA INTELLIGENCE CONSOLE // VHF &amp; SATELLITE
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
            <VesselChip auth={auth} vesselClass={latestVesselClass} />
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
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col gap-4 lg:flex-row">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4">
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
                {firstQuestion && (
                  <span className="truncate text-xs text-ink-muted" title={firstQuestion}>
                    {/* The live title comes from the rail's list; the first
                        question is the same fallback it shows for an unnamed chat. */}
                    {chatTitle({ title: null, first_question: firstQuestion })}
                  </span>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {saveFailed && (
                  <span role="status" className="text-[11px] text-caution">
                    {t("ask.notSaved")}
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
                <Button variant="ghost" icon={<Plus className="size-3.5" />} onClick={newChat}>
                  {t("common.newChat")}
                </Button>
              </div>
            </div>

            {/* `relative` is load-bearing, not decoration: it makes this
                scroller the containing block for the absolutely positioned
                bits inside a turn (the agent pills' sr-only status spans).
                Without it those resolve against the panel wrapper below,
                escape this box's clipping, and stretch the page's own scroll
                area by the full height of the thread — the empty scroll
                space that appeared under the composer, map and history once a
                thread ran past one screen. */}
            <div ref={threadRef} className="relative flex min-h-0 min-w-0 flex-1 flex-col gap-5 overflow-y-auto pr-2">
              {turns.map((turn, i) => (
                <ChatTurn
                  key={turn.id}
                  turn={turn}
                  persona={persona}
                  isMapFocus={activeFocus?.nonce === turn.focus?.nonce}
                  hadEarlierAnswers={hadEarlierAnswers(turns, i)}
                  onViewOnMap={() => {
                    setActiveFocus(turn.focus);
                    setMapCollapsed(false);
                  }}
                  onRetry={() => ask(turn.askedQuery)}
                  onRerun={() => rerun(turn.id)}
                  onShowVersion={(index) => showVersion(turn.id, index)}
                  onFollowUp={submit}
                  onDropInherited={(value) => dropInherited(turn, value)}
                  onPersonaChange={(p) => setRenderedAs(turn.id, p)}
                  onRendered={(result) => applyRender(turn.id, result)}
                />
              ))}
              {/* Sentinel: scrolled into view whenever a new turn arrives or
                  a streaming answer updates, keeping the latest exchange
                  visible without the user having to scroll manually. */}
              <div ref={threadBottomRef} />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <SavedLocationChips onSelect={askSavedLocation} addFrom={lastResolvedLocation} />
              <VesselChip auth={auth} vesselClass={latestVesselClass} />
            </div>
            <Composer
              value={query}
              onChange={setQuery}
              onSubmit={submit}
              disabled={streaming}
              voice={voice}
              isFisherman={persona === "fisherman"}
              centered={false}
            />
          </div>

          <motion.div
            layout={!reduceMotion}
            transition={{ duration: 0.25, ease: "easeOut" }}
            // Collapsed: pulled out of the flex flow entirely (absolute,
            // zero-opacity, non-interactive) so the thread covers the full
            // width instead of yielding a reserved strip — but still
            // rendered at its normal target size, kept mounted, one
            // MapLibre instance for the whole session, per MapView's own
            // layout thesis. Expanded: a normal flex sibling again.
            className={
              mapCollapsed
                ? "pointer-events-none absolute inset-0 -z-10 overflow-hidden rounded-2xl opacity-0 lg:right-0 lg:left-auto lg:w-[42%]"
                : "relative h-64 w-full shrink-0 overflow-hidden rounded-2xl border border-hairline bg-shelf-1/60 shadow-2xl lg:h-full lg:w-[42%]"
            }
          >
            {!mapCollapsed && (
              <button
                type="button"
                onClick={() => setMapCollapsed(true)}
                aria-label={t("ask.collapseMap")}
                aria-expanded={true}
                className="absolute top-2 left-2 z-10 flex size-7 items-center justify-center rounded-lg border border-hairline/80 bg-shelf-1/90 text-ink-dim shadow-sm backdrop-blur-sm transition-colors hover:border-ocean-cyan/60 hover:text-ocean-cyan"
              >
                <Minimize2 className="size-3.5" />
              </button>
            )}

            {/* Depth shading + surface currents on by default (plan §9) — the
                only Ask-specific default; /map and /voyage keep their own tuned
                defaults via the same `initialLayers` prop. */}
            <div className="h-full w-full">
              <MapView
                className="h-full w-full"
                initialLayers={{ srvBathymetry: true, currents: true }}
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
