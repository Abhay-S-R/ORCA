"use client";

// Thread state for the Ask chat: one EventSource pipeline (unchanged from the
// original single-turn version) fanning its events into a growing list of
// turns. The thread is one saved chat out of many — kept by a ChatStore
// (./chatStore: this browser for guests, the account when signed in) — and
// "New chat" or opening a chat from history swaps which one is on screen.
import { useEffect, useRef, useState } from "react";
import type { AgentStatus } from "../components/AgentPill";
import type { ConfidenceTier, Verdict } from "../components/Badge";
import type { HazardBreakdown, OceanSummary, WeatherSummary, Citation } from "../components/PersonaAnswerMatrix";
import type { RenderResult } from "../components/PersonaCorrection";
import type { SourceSelection } from "../components/SourceNarration";
import type { QueryFocus } from "../components/MapView";
import { type Persona } from "../persona/config";
import { API_BASE } from "../lib/apiBase";
import { useGeolocation } from "../lib/useGeolocation";
import { classifyQueryIntent, matchRegionInQuery } from "../lib/queryIntent";
import { readActiveChat, restoreContext, writeActiveChat, type ChatStore } from "./chatStore";
import type { IntentAction } from "./IntentActions";

// confidence_tier: the band of the agent's measured score (orca/confidence_score.py).
// Only the label travels here — the number stays on /reasoning.
export type AgentSpan = { agent_name: string; status: AgentStatus; confidence_tier?: ConfidenceTier };
export type FinalResponse = {
  query_id?: string;
  final_english_response: string;
  final_vernacular_response?: string;
  detected_language?: string;
  confidence_tier: ConfidenceTier;
  citations?: Citation[];
  source_selections?: SourceSelection[];
  risk_assessment?: { go_no_go: Verdict; reason: string } | null;
  weather_summary?: WeatherSummary;
  hazard_breakdown?: HazardBreakdown;
  ocean_summary?: OceanSummary;
  // Earlier turns of this chat the backend answered with (its context window,
  // orca/session.py). Absent on answers cached before the field existed.
  context_turns?: number;
  // Per-agent scored labels (orca/api/main.py). A query-cache hit streams no
  // agent_span events, so this is what the strip falls back to.
  agent_confidence?: AgentSpan[];
  // A distress answer bypasses every agent but the distress check; the map
  // pins the caller's position from these (P4.16).
  // One concrete action per ROUTE / META / EXPORT / … intent (P5.29).
  intent_actions?: IntentAction[];
  distress_flag?: boolean;
  user_location?: { lat: number; lon: number; place_name?: string | null; place_source?: string } | null;
  // Phase 1 (contracts.QueryOutcome). Anything but "ANSWERED"/"DISTRESS" is a
  // refusal or a question back, and must NOT be drawn as an answer with a
  // verdict badge. Absent on answers cached before the field existed, which is
  // why every read defaults to "ANSWERED".
  outcome?: "ANSWERED" | "OUT_OF_SCOPE" | "NEEDS_PLACE" | "OUT_OF_RANGE" | "DISTRESS";
  // Sentences that belong ABOVE the answer, not below it: the position was a
  // fallback, the sector was a fallback, the reading is past its staleness
  // ceiling. A fallback that is not disclosed is a lie (plan principle 3).
  disclosures?: string[];
  // Present when the backend could not settle on one position. `candidates`
  // are the places to offer back, with coordinates, so the chip can re-ask.
  place_resolution?: {
    status: "resolved" | "ambiguous" | "unresolvable" | "fallback";
    place_name?: string | null;
    place_source?: string | null;
    candidates?: { name: string; lat: number; lon: number }[];
    disclosure?: string | null;
  } | null;
};

export type Turn = {
  id: string;
  askedQuery: string;
  // When it was asked — orders turns when a guest chat is imported into an
  // account. Absent on turns saved before it existed.
  askedAt?: string;
  spans: AgentSpan[];
  answer: FinalResponse | null;
  streaming: boolean;
  failed: boolean;
  renderedAs: Persona | null;
  focus: QueryFocus | null;
};

// Chart focus reacts to the question itself, not the answer. A follow-up that
// names no topic or region of its own ("what about tomorrow?") keeps the map
// where the conversation already is — the same carry-over the backend applies
// to its intent and place.
function focusFor(q: string, previous: QueryFocus | null | undefined, nonce: number): QueryFocus {
  const intent = classifyQueryIntent(q);
  return {
    intent: intent === "general" && previous ? previous.intent : intent,
    regionId: matchRegionInQuery(q) ?? previous?.regionId,
    nonce,
  };
}

export function useAskThread(persona: Persona, store: ChatStore | null, onChatSaved?: () => void) {
  // null means "not yet hydrated" — distinct from a real empty thread ([]).
  // Starting at null (rather than reading storage in useState's initializer)
  // avoids mismatching the server-rendered HTML, the exact pitfall
  // persona/context.tsx documents for its own storage read. It also stays null
  // until auth has resolved which store the chat lives in.
  const [savedTurns, setSavedTurns] = useState<Turn[] | null>(null);
  const turns = savedTurns ?? [];
  const [chatId, setChatId] = useState<string | null>(null);
  const [activeFocus, setActiveFocus] = useState<QueryFocus | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  // The browser's GPS fix, shared with MapView's marker through the one hook
  // so the map and the answer are never about two different positions.
  // Backend rule (api/main.py): an explicit lat/lon always beats a place name
  // parsed out of the text, so sending this is what stops a query naming a
  // harbour outside the gazetteer being answered at the pilot-region default.
  const { position: geoPosition, status: geoStatus } = useGeolocation();
  const sourceRef = useRef<EventSource | null>(null);
  const focusNonce = useRef(0);
  const lastPersona = useRef(persona);
  const chatIdRef = useRef<string | null>(null);
  const storeRef = useRef<ChatStore | null>(null);
  // The object last handed to the store for each turn id — a turn is saved
  // again only when it actually changed (an answer landed, a re-render).
  const persisted = useRef(new Map<string, Turn>());
  const restoring = useRef<Promise<void>>(Promise.resolve());

  function show(id: string | null, shown: Turn[]) {
    let previous: QueryFocus | null = null;
    const ready = shown.map((t) => {
      // A turn still marked "streaming" belongs to a tab that closed mid
      // answer — its EventSource is gone, so it would hang forever as is.
      const settled = t.streaming ? { ...t, streaming: false, failed: true } : t;
      focusNonce.current += 1;
      const focus = settled.focus ?? focusFor(settled.askedQuery, previous, focusNonce.current);
      previous = focus;
      return { ...settled, focus };
    });
    persisted.current = new Map(ready.map((t) => [t.id, t]));
    chatIdRef.current = id;
    setChatId(id);
    setSavedTurns(ready);
    setActiveFocus(ready[ready.length - 1]?.focus ?? null);
    setSaveFailed(false);
    writeActiveChat(id);
    // Put the reopened chat's earlier turns back into the backend's context
    // window (it lapses after 30 minutes), so a follow-up continues it. ask()
    // waits on this before opening its stream.
    restoring.current = id ? restoreContext(id, ready).catch(() => {}) : Promise.resolve();
  }

  // Load the active chat once the store is known. A later store change is a
  // sign-out (or a session that expired): whatever chat was on screen belonged
  // to the account, so it must not stay visible — start a new chat instead.
  useEffect(() => {
    if (!store) return;
    const firstLoad = storeRef.current === null;
    storeRef.current = store;
    sourceRef.current?.close();
    const activeId = firstLoad ? readActiveChat() : null;
    let cancelled = false;
    if (!activeId) {
      show(null, []);
      return;
    }
    store
      .load(activeId)
      .then((chat) => {
        if (!cancelled) show(chat ? activeId : null, chat?.turns ?? []);
      })
      .catch(() => {
        if (!cancelled) show(null, []);
      });
    return () => {
      cancelled = true;
    };
  }, [store]);

  // Save every turn that changed. Streaming span updates reach the browser
  // store too (a reload mid-answer then shows the question with "Ask again",
  // as before); the account store only keeps answered turns.
  useEffect(() => {
    const id = chatIdRef.current;
    if (!store || !id || savedTurns === null) return;
    for (const turn of savedTurns) {
      if (persisted.current.get(turn.id) === turn) continue;
      persisted.current.set(turn.id, turn);
      store
        .saveTurn(id, turn, persona)
        .then(() => {
          if (!turn.streaming) {
            setSaveFailed(false);
            onChatSaved?.();
          }
        })
        .catch(() => {
          // Forget it was handed over, so the next change retries this turn.
          persisted.current.delete(turn.id);
          setSaveFailed(true);
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- persona/onChatSaved are read at save time, not triggers
  }, [savedTurns, store]);

  // Switching persona (nav-wide setting) changes how an answer would render,
  // so start a new chat rather than mix renderings in one — the previous chat
  // is already saved and stays in history. usePersona() itself always starts
  // a mount at "unresolved" and syncs the real value from localStorage a
  // moment later (hydration-safe pattern) — that first resolution is not a
  // real switch, so it must not replace a restored thread.
  useEffect(() => {
    if (lastPersona.current === persona) return;
    const previous = lastPersona.current;
    lastPersona.current = persona;
    // ponytail: treats every unresolved-origin transition as hydration, so a
    // user who explicitly sets persona to Unresolved then picks one won't
    // start a new chat either — narrow the check to "first render only" if
    // that mid-session case needs to as well.
    if (previous === "unresolved") return;
    newChat();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- newChat only touches refs and setters
  }, [persona]);

  function newChat() {
    sourceRef.current?.close();
    show(null, []);
  }

  async function openChat(id: string) {
    if (!store || id === chatIdRef.current) return;
    sourceRef.current?.close();
    const chat = await store.load(id);
    if (chat) show(id, chat.turns);
    return Boolean(chat);
  }

  function updateTurn(id: string, patch: Partial<Turn> | ((t: Turn) => Partial<Turn>)) {
    setSavedTurns((prev) =>
      (prev ?? []).map((t) => (t.id === id ? { ...t, ...(typeof patch === "function" ? patch(t) : patch) } : t)),
    );
  }

  function ask(q: string) {
    if (!q.trim()) return;
    sourceRef.current?.close();

    if (!chatIdRef.current) {
      // Minted on the first question, not on "New chat" — an empty chat is
      // never saved and never appears in history.
      chatIdRef.current = crypto.randomUUID();
      setChatId(chatIdRef.current);
      writeActiveChat(chatIdRef.current);
    }
    const sessionId = chatIdRef.current;

    const id = crypto.randomUUID();
    focusNonce.current += 1;
    const focus = focusFor(q, turns[turns.length - 1]?.focus, focusNonce.current);
    setSavedTurns((prev) => [
      ...(prev ?? []),
      {
        id,
        askedQuery: q,
        askedAt: new Date().toISOString(),
        spans: [],
        answer: null,
        streaming: true,
        failed: false,
        renderedAs: null,
        focus,
      },
    ]);
    setActiveFocus(focus);

    // Persona is an explicit rendering choice only — Agent 9 renders with it,
    // no classifier reads it (Ground Rule 1). "unresolved" = don't send one.
    const personaParam = persona !== "unresolved" ? `&persona=${persona}` : "";
    const sessionParam = `&session_id=${encodeURIComponent(sessionId)}`;
    // useGeolocation stores [lon, lat] (GeoJSON order), so unpack, don't index blind.
    // Only sent on a "granted" fix: a denied or still-loading permission must
    // fall through to resolving the place from the query text, not to a stale
    // or half-resolved position.
    const [geoLon, geoLat] = geoPosition ?? [];
    const geoParam =
      geoStatus === "granted" && geoLat !== undefined && geoLon !== undefined
        ? `&fix_lat=${geoLat}&fix_lon=${geoLon}`
        : "";
    void restoring.current.then(() => {
      // The user may have switched chats while the context was restoring.
      if (chatIdRef.current !== sessionId) return;
      const es = new EventSource(`${API_BASE}/query?q=${encodeURIComponent(q)}${personaParam}${sessionParam}${geoParam}`);
      sourceRef.current = es;
      es.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        if (data.type === "agent_span") {
          updateTurn(id, (t) => ({ spans: [...t.spans, { agent_name: data.agent_name, status: data.status, confidence_tier: data.confidence_tier }] }));
        } else if (data.type === "final_response") {
          updateTurn(id, { answer: data, streaming: false });
          es.close();
        }
      };
      es.onerror = () => {
        updateTurn(id, { streaming: false, failed: true });
        es.close();
      };
    });
  }

  function setRenderedAs(id: string, p: Persona | null) {
    updateTurn(id, { renderedAs: p });
  }

  function applyRender(id: string, result: RenderResult) {
    updateTurn(id, (t) =>
      t.answer
        ? {
            answer: {
              ...t.answer,
              final_english_response: result.final_english_response,
              final_vernacular_response: undefined, // /render is English-only (translation stays at the edge, Agent 1)
              confidence_tier: result.confidence_tier as ConfidenceTier,
              citations: result.citations,
            },
          }
        : {},
    );
  }

  return {
    turns,
    hydrated: savedTurns !== null,
    chatId,
    saveFailed,
    streaming: turns.some((t) => t.streaming),
    activeFocus,
    setActiveFocus,
    ask,
    newChat,
    openChat,
    setRenderedAs,
    applyRender,
  };
}
