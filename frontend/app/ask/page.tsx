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
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { motion, useReducedMotion } from "framer-motion";
import { Compass, Fish, History, Maximize2, MapPin, Minimize2, Plus, ShieldCheck, Waves, Wind } from "lucide-react";
import { Button } from "../components/Button";
import { Skeleton } from "../components/States";
import { useVoiceInput } from "../components/VoiceInput";
import { useAuth } from "../lib/auth";
import { usePersona } from "../persona/context";
import { classifyQueryIntent, type QueryIntent } from "../lib/queryIntent";
import { Composer } from "./Composer";
import { ChatTurn } from "./ChatTurn";
import { ChatHistoryRail, CollapsedChatRail } from "./ChatHistoryRail";
import { accountStore, browserStore, chatTitle } from "./chatStore";
import { useAskThread } from "./useAskThread";

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

// Real questions in the users' own words, not feature names — and, since
// ORCA's scope is the Indian coastline as a whole rather than one pilot
// region, spanning a few different coasts rather than repeating one place.
const EXAMPLES = [
  "Is it safe to go out tomorrow morning?",
  "Where are the fishing zones closest to my port?",
  "What is the current speed off the Kerala coast?",
];
const PRESETS = EXAMPLES.map((label) => ({ label, icon: INTENT_ICON[classifyQueryIntent(label)] }));

const RAIL_COLLAPSED_KEY = "orca-ask-rail-collapsed";

export default function AskPage() {
  const { persona } = usePersona();
  const reduceMotion = useReducedMotion();
  const auth = useAuth();
  const store = auth.status === "loading" ? null : auth.status === "signed_in" ? accountStore : browserStore;
  const [query, setQuery] = useState("");
  const [mapCollapsed, setMapCollapsed] = useState(false);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);
  const {
    turns,
    chatId,
    saveFailed,
    streaming,
    activeFocus,
    setActiveFocus,
    ask,
    newChat,
    openChat,
    setRenderedAs,
    applyRender,
  } = useAskThread(persona, store, () => setHistoryVersion((v) => v + 1));

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

  function collapseRail(collapsed: boolean) {
    setRailCollapsed(collapsed);
    try {
      localStorage.setItem(RAIL_COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      /* not remembered — nothing else depends on it */
    }
  }

  function submit(q: string) {
    ask(q);
    setQuery("");
  }

  const voice = useVoiceInput({ onTranscriptConfirmed: submit });
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
      Chats
    </Button>
  );

  return (
    <div className="flex h-full min-h-0 gap-4 p-5 lg:p-7">
      <div className="hidden min-h-0 lg:flex">
        {railCollapsed ? <CollapsedChatRail onExpand={() => collapseRail(false)} onNew={newChat} /> : history("rail")}
      </div>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex bg-abyss/50 lg:hidden" onClick={() => setDrawerOpen(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Chat history"
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
          <div className="max-w-2xl text-center">
            <div className="mb-3 flex items-center justify-center gap-2">
              <span className="size-2 rounded-full bg-ocean-cyan beacon-pulse" aria-hidden="true" />
              <span className="font-mono text-[10px] font-bold tracking-widest text-ocean-cyan uppercase">
                ORCA INTELLIGENCE CONSOLE // VHF &amp; SATELLITE
              </span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">Ask about conditions at sea</h1>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
              Ask in plain English or Tamil. ORCA evaluates live ocean weather, maritime boundary standoff, depth
              contours, and fishing advisories with full citation provenance.
            </p>
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
        </div>
      ) : (
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 lg:flex-row">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4">
            <div className="flex items-center justify-between gap-3 border-b border-hairline/60 pb-3">
              <div className="flex min-w-0 items-baseline gap-2">
                <h1 className="shrink-0 text-xs font-bold uppercase tracking-wider text-ink-dim">Ask ORCA</h1>
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
                    Not saved yet — retrying
                  </span>
                )}
                {historyButton}
                <Button variant="ghost" icon={<Plus className="size-3.5" />} onClick={newChat}>
                  New chat
                </Button>
              </div>
            </div>

            <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-5 overflow-y-auto pr-2">
              {turns.map((turn, i) => (
                <ChatTurn
                  key={turn.id}
                  turn={turn}
                  persona={persona}
                  isMapFocus={activeFocus?.nonce === turn.focus?.nonce}
                  hadEarlierAnswers={turns.slice(0, i).some((t) => t.answer)}
                  onViewOnMap={() => {
                    setActiveFocus(turn.focus);
                    setMapCollapsed(false);
                  }}
                  onRetry={() => ask(turn.askedQuery)}
                  onFollowUp={submit}
                  onPersonaChange={(p) => setRenderedAs(turn.id, p)}
                  onRendered={(result) => applyRender(turn.id, result)}
                />
              ))}
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
            className={`relative shrink-0 overflow-hidden rounded-2xl border border-hairline bg-shelf-1/60 shadow-2xl ${mapCollapsed ? "h-11 w-full lg:h-full lg:w-11" : "h-64 w-full lg:h-full lg:w-[42%]"
              }`}
          >
            <button
              type="button"
              onClick={() => setMapCollapsed((c) => !c)}
              aria-label={mapCollapsed ? "Expand map" : "Collapse map"}
              aria-expanded={!mapCollapsed}
              className="absolute top-2 left-2 z-10 flex size-7 items-center justify-center rounded-lg border border-hairline/80 bg-shelf-1/90 text-ink-dim shadow-sm backdrop-blur-sm transition-colors hover:border-ocean-cyan/60 hover:text-ocean-cyan"
            >
              {mapCollapsed ? <Maximize2 className="size-3.5" /> : <Minimize2 className="size-3.5" />}
            </button>

            {/* Depth shading + surface currents on by default (plan §9) — the
                only Ask-specific default; /map and /voyage keep their own tuned
                defaults via the same `initialLayers` prop. Kept mounted while
                collapsed (opacity only) — one MapLibre instance for the whole
                session, per MapView's own layout thesis. */}
            <div className={mapCollapsed ? "pointer-events-none h-full w-full opacity-0" : "h-full w-full transition-opacity duration-200"}>
              <MapView
                className="h-full w-full"
                initialLayers={{ srvBathymetry: true, currents: true }}
                queryFocus={activeFocus}
                showLayerPanel={false}
                showRegionSwitcher={false}
                showLegends={false}
                showSoundingHud={false}
              />
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
