"use client";

// Ask (§4.2, now at `/ask` — `/` itself is the public landing page) — the
// conversational entry point. A real multi-turn thread (was single-turn,
// replaced on every ask): the composer starts centered on a blank page and
// docks to the bottom of the thread once the first question lands,
// Claude-style. There is no map on this page (removed 2026-10-09, PLAN-ASK-1):
// the answer card carries the facts, and the maps live on their own pages.
// The thread and the composer share ONE centred column of fixed maximum
// width (PLAN-ASK-3), so the input box is the same size whether the chat
// sidebar is open or closed.
//
// Past chats sit in a rail to the left (a drawer below lg, where a third
// column would squeeze the thread and the chart); they are kept in this
// browser for guests and in the account once signed in (./chatStore).
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Compass, Fish, History, MapPin, PanelLeftOpen, Plus, ShieldCheck, Waves, Wind } from "lucide-react";
import { Button } from "../components/Button";
import { Greeting } from "../components/Greeting";
import { SavedLocationChips } from "../components/SavedLocationChips";
import { VesselChip } from "../components/VesselChip";
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

export default function AskPage() {
  const { persona } = usePersona();
  const reduceMotion = useReducedMotion();
  const auth = useAuth();
  const t = useT();
  const { language } = useLanguage();
  const store = auth.status === "loading" ? null : auth.status === "signed_in" ? accountStore : browserStore;
  const [query, setQuery] = useState("");
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
    ask,
    rerun,
    showVersion,
    newChat,
    openChat,
  } = useAskThread(persona, store, () => setHistoryVersion((v) => v + 1));

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
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col gap-4">
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
                  {t(saveFailed === "rejected" ? "ask.saveRejected" : "ask.notSaved")}
                </span>
              )}
              {historyButton}
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
              space that appeared under the composer and history once a
              thread ran past one screen. The scroller spans the full width
              (so its scrollbar sits at the edge); the column inside it is
              the same centred max-w-4xl the composer uses. */}
          <div ref={threadRef} className="relative min-h-0 min-w-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-4xl flex-col gap-5 pr-2">
              {turns.map((turn, i) => (
                <ChatTurn
                  key={turn.id}
                  turn={turn}
                  persona={persona}
                  hadEarlierAnswers={hadEarlierAnswers(turns, i)}
                  onRetry={() => ask(turn.askedQuery)}
                  onRerun={() => rerun(turn.id)}
                  onShowVersion={(index) => showVersion(turn.id, index)}
                  onFollowUp={submit}
                  onDropInherited={(value) => dropInherited(turn, value)}
                />
              ))}
              {/* Sentinel: scrolled into view whenever a new turn arrives or
                  a streaming answer updates, keeping the latest exchange
                  visible without the user having to scroll manually. */}
              <div ref={threadBottomRef} />
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
