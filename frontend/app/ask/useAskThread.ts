"use client";

// Thread state for the Ask chat: one EventSource pipeline (unchanged from the
// original single-turn version) fanning its events into a growing list of
// turns. The thread is one saved chat out of many — kept by a ChatStore
// (./chatStore: this browser for guests, the account when signed in) — and
// "New chat" or opening a chat from history swaps which one is on screen.
import { useEffect, useRef, useState } from "react";
import type { AgentStatus } from "../components/AgentPill";
import type { ConfidenceTier, Verdict } from "../components/Badge";
import type { HazardBreakdown, OceanSummary, WeatherSummary, Citation, SafetyThresholds } from "../components/PersonaAnswerMatrix";
import type { RenderResult } from "../components/PersonaCorrection";
import type { SourceSelection } from "../components/SourceNarration";
import type { QueryFocus } from "../components/MapView";
import type { ChartSpec } from "../lib/chartSpec";
import { type Persona } from "../persona/config";
import { API_BASE } from "../lib/apiBase";
import { tokenParam } from "../lib/auth";
import { useCriticalAlert, type CriticalCondition } from "../lib/criticalAlert";
import { useGeolocation } from "../lib/useGeolocation";
import { classifyQueryIntent, matchRegionInQuery } from "../lib/queryIntent";
import { ChatRequestError, confidenceFromTrace, readActiveChat, restoreContext, withCachedConfidence, writeActiveChat, type ChatStore } from "./chatStore";
import type { IntentAction } from "./IntentActions";

// confidence_tier: the band of the agent's measured score (orca/confidence_score.py).
// Only the label travels here — the number stays on /reasoning.
export type AgentSpan = {
  agent_name: string;
  status: AgentStatus;
  confidence_tier?: ConfidenceTier;
  // P2.1 (`R-JUDGE-1`) — what computed this span: "Deterministic" for the
  // safety path, the IndicTrans2 weights for Agent 1, a model id for a span
  // that actually reached one. Never absent on a live span.
  engine?: string;
  // P2.3 — why that confidence tier.
  confidence_rationale?: string | null;
  // P2.10 (`R-NEW-4`) — per-agent latency, already on the wire and unused.
  latency_ms?: number;
  // P2.7/P2.12 — why a span did not run, when it did not.
  skip_reason?: string | null;
};

// P2.4 (`R-PS-5`) — one comparison between two sources covering the same
// variable. `status` is "agree" | "diverged" | "not_comparable"; only the
// last two produce a sentence, and a divergence also drops confidence a tier.
export type Reconciliation = {
  variable: string;
  label: string;
  unit: string;
  primary: { value: number | boolean; source: string; timestamp?: string | null };
  secondary: { value: number | boolean; source: string; timestamp?: string | null };
  divergence: number | null;
  divergence_pct: number | null;
  time_gap_minutes: number | null;
  status: "agree" | "diverged" | "not_comparable";
  used_value: number | boolean;
  used_source: string;
  confidence_penalty: boolean;
  statement: string;
};

// P2.9 / orca_final §16.2 — a value this answer took from earlier in the
// conversation rather than from the question. Rendered as a removable chip:
// carrying context is correct, carrying it invisibly is indistinguishable
// from guessing.
export type InheritedValue = {
  field: "place" | "intent" | "vessel_class";
  label: string;
  value: string;
  detail: string;
};

// P2.7 (`R-JUDGE-3`) — the routing decision, so a compound query visibly
// dispatches a larger agent set than a simple one.
export type RoutingSummary = {
  matched_intent_rows: string[];
  execution_plan: string[];
  routing_tier?: string | null;
  routing_scores: { row: string; score: number }[];
  agents_dispatched: number;
  multi_intent: boolean;
};
export type FinalResponse = {
  query_id?: string;
  final_english_response: string;
  final_vernacular_response?: string;
  detected_language?: string;
  confidence_tier: ConfidenceTier;
  citations?: Citation[];
  source_selections?: SourceSelection[];
  risk_assessment?: { go_no_go: Verdict; reason: string; thresholds?: SafetyThresholds | null } | null;
  // P2.2 — whether the verdict leads this answer. False only for a GO on a
  // question that was not about safety; a CAUTION or NO_GO always leads.
  lead_with_verdict?: boolean;
  weather_summary?: WeatherSummary;
  hazard_breakdown?: HazardBreakdown;
  // Agent 8 — P4.8 reads `chart_specs` for the wave/wind time series;
  // `map_layers` stays unused here, MapView reads the map-layers route instead.
  visualization_payload?: { chart_specs?: ChartSpec[] } | null;
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
  // "RESET" (P2.14) is not an answer at all: the conversation was cleared and
  // this is the one-line confirmation. It must render as neither an answer
  // nor a refusal, and it clears the inherited chips.
  outcome?: "ANSWERED" | "OUT_OF_SCOPE" | "NEEDS_PLACE" | "OUT_OF_RANGE" | "DISTRESS" | "RESET";
  // P2.3 — the inputs the confidence tier is the worst OF, each with its own
  // tier and rationale. Null on refusals and distress, which skip Reporting.
  confidence_inputs?: { agent_name: string; tier: ConfidenceTier; rationale: string }[] | null;
  // P2.4 — every pair of sources compared for this answer. The disagreements
  // are also in `disclosures`, above the answer; this is the full record.
  reconciliation?: Reconciliation[];
  // P2.7 — what the plan decided not to run, and why.
  skipped_agents?: { agent_name: string; status: string; reason: string }[];
  routing?: RoutingSummary;
  // P2.10 — per-agent latency and the summed agent time. `agent_time_ms` is a
  // SUM of spans, not wall clock: three specialists run in parallel, so it
  // overstates elapsed time rather than understating it.
  latency?: {
    per_agent: { agent_name: string; latency_ms: number }[];
    agent_time_ms: number;
    slowest: { agent_name: string; latency_ms: number } | null;
  };
  // P2.13 — measured provider calls for this query, not an estimate.
  llm_call_count?: number;
  // P2.11 — whether any LLM was reachable for this query.
  llm_enabled?: boolean;
  // Chatbot plan C0.2 — which engine wrote the answer text. "Deterministic — …"
  // is the last-resort facts paragraph, which the chat labels as such.
  response_engine?: string | null;
  // A refused message that was only a greeting or small talk: rendered
  // without the "Not something ORCA can answer" heading.
  small_talk?: boolean;
  // P2.9 — values carried from earlier turns, as removable chips.
  inherited?: InheritedValue[];
  vessel_class?: string | null;
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
  // P3.4 — "ask at the moment it first matters." Signed-in only; null on
  // every anonymous answer and once the account already has an answer for
  // the one field this particular question would have used.
  profile_prompt?: {
    field: "vessel_class" | "home_port";
    question: string;
    input_type: "choice" | "confirm";
    options?: { value: string; label: string }[];
  } | null;
};

// One run of a question. A turn starts with exactly one; "try again" adds
// another. Kept as a separate list rather than replacing `answer`/`spans`
// because those two are read by the export, the context restore and the map's
// distress pins — they stay mirrored to whichever version is on screen, so
// none of that had to change, and a turn saved before versions existed loads
// as a single-version turn without a migration.
export type TurnVersion = { answer: FinalResponse | null; spans: AgentSpan[] };

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
  // P2.11 — this turn was deliberately asked with the LLM switched off. Held
  // on the turn so the card can say so even after a reload, rather than the
  // deterministic answer looking like an ordinary one that happened to be terse.
  llmDisabled?: boolean;
  // Absent on turns that were never re-run, and on every turn saved before
  // this existed. `versions[versionIndex]` is what `answer`/`spans` mirror.
  versions?: TurnVersion[];
  versionIndex?: number;
};

/** Every run of a turn, oldest first — synthesized for turns that predate versions. */
export function turnVersions(turn: Turn): TurnVersion[] {
  return turn.versions?.length ? turn.versions : [{ answer: turn.answer, spans: turn.spans }];
}

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

// P4.12 — the same hard-block reading every answer already carries
// (`geospatial.py`'s `_alert_level`: DANGER ≤1 nm, INSIDE; cyclone Red from
// weather_intelligence) becomes the full-screen takeover's trigger. Never a
// second computation of the threshold, just a read of what risk_assessment
// already decided this answer against.
function criticalConditionFrom(data: {
  query_id?: string;
  hazard_breakdown?: { imbl_distance_nm?: number | null; imbl_alert_level?: string | null } | null;
  weather_summary?: { cyclone_alert?: string | null } | null;
}): Omit<CriticalCondition, "raisedAt"> | null {
  const level = data.hazard_breakdown?.imbl_alert_level;
  if (level === "DANGER" || level === "INSIDE") {
    return {
      kind: "boundary",
      level,
      distanceNm: data.hazard_breakdown?.imbl_distance_nm ?? null,
      queryId: data.query_id ?? null,
    };
  }
  if (data.weather_summary?.cyclone_alert === "Red") {
    return { kind: "cyclone", level: "Red", distanceNm: null, queryId: data.query_id ?? null };
  }
  return null;
}

export function useAskThread(persona: Persona, store: ChatStore | null, onChatSaved?: () => void) {
  const { raise: raiseCriticalAlert } = useCriticalAlert();
  // null means "not yet hydrated" — distinct from a real empty thread ([]).
  // Starting at null (rather than reading storage in useState's initializer)
  // avoids mismatching the server-rendered HTML, the exact pitfall
  // persona/context.tsx documents for its own storage read. It also stays null
  // until auth has resolved which store the chat lives in.
  const [savedTurns, setSavedTurns] = useState<Turn[] | null>(null);
  const turns = savedTurns ?? [];
  const [chatId, setChatId] = useState<string | null>(null);
  const [activeFocus, setActiveFocus] = useState<QueryFocus | null>(null);
  // "retrying": a save failed and the next change will try it again.
  // "rejected": the server said this chat is not ours (404) — final, so it is
  // said once rather than retried forever (chatbot plan C0.1).
  const [saveFailed, setSaveFailed] = useState<false | "retrying" | "rejected">(false);
  // The browser's GPS fix, shared with MapView's marker through the one hook
  // so the map and the answer are never about two different positions.
  // Backend rule (api/main.py): an explicit lat/lon always beats a place name
  // parsed out of the text, so sending this is what stops a query naming a
  // harbour outside the gazetteer being answered at the pilot-region default.
  const { position: geoPosition, status: geoStatus } = useGeolocation();
  // useGeolocation stores [lon, lat] (GeoJSON order), so unpack, don't index blind.
  // Only sent on a "granted" fix: a denied or still-loading permission must
  // fall through to resolving the place from the query text, not to a stale
  // or half-resolved position. Shared by `ask` and `rerun`: a re-run that
  // dropped the fix would answer the same question at a different position.
  const [geoLon, geoLat] = geoPosition ?? [];
  const geoParam =
    geoStatus === "granted" && geoLat !== undefined && geoLon !== undefined
      ? `&fix_lat=${geoLat}&fix_lon=${geoLon}`
      : "";
  const sourceRef = useRef<EventSource | null>(null);
  const focusNonce = useRef(0);
  const lastPersona = useRef(persona);
  const chatIdRef = useRef<string | null>(null);
  const storeRef = useRef<ChatStore | null>(null);
  // The object last handed to the store for each turn id — a turn is saved
  // again only when it actually changed (an answer landed, a re-render).
  const persisted = useRef(new Map<string, Turn>());
  const restoring = useRef<Promise<void>>(Promise.resolve());
  // Read by rerun() when its answer lands: `turns` in a stream callback is the
  // value captured when the stream opened, which is exactly the wrong one.
  const turnsRef = useRef<Turn[]>([]);
  turnsRef.current = turns;

  function show(id: string | null, shown: Turn[]) {
    let previous: QueryFocus | null = null;
    const ready = shown.map((t) => {
      // A turn still marked "streaming" belongs to a tab that closed mid
      // answer — its EventSource is gone, so it would hang forever as is.
      const settled = withCachedConfidence(t.streaming ? { ...t, streaming: false, failed: true } : t);
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
        .saveTurn(id, withCachedConfidence(turn), persona)
        .then(() => {
          if (!turn.streaming) {
            setSaveFailed(false);
            onChatSaved?.();
          }
        })
        .catch((err: unknown) => {
          if (err instanceof ChatRequestError && err.status === 404) {
            setSaveFailed("rejected");
            return;
          }
          // Forget it was handed over, so the next change retries this turn.
          persisted.current.delete(turn.id);
          setSaveFailed("retrying");
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- persona/onChatSaved are read at save time, not triggers
  }, [savedTurns, store]);

  // Confidence for turns saved before spans carried it — fetched once per turn
  // from the trace store and written back, so the repair happens on the first
  // open of an old chat and never again. Runs after render: the strip appears
  // immediately with plain ticks and gains its confidence a moment later,
  // rather than the whole chat waiting on a fetch per turn.
  const traceRepairTried = useRef(new Set<string>());
  useEffect(() => {
    const needing = (savedTurns ?? []).filter(
      (t) =>
        !t.streaming &&
        t.answer &&
        t.spans.length > 0 &&
        t.spans.some((s) => !s.confidence_tier) &&
        !traceRepairTried.current.has(t.id),
    );
    if (!needing.length) return;
    let cancelled = false;
    void (async () => {
      for (const turn of needing) {
        traceRepairTried.current.add(turn.id);
        const spans = await confidenceFromTrace(turn);
        if (cancelled) return;
        if (spans) updateTurn(turn.id, { spans });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [savedTurns]);

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

  // P2.11 (`R-NEW-3`) — re-ask the same question with every LLM provider
  // disabled. `llm` is threaded to the query string rather than held as
  // component state, so the deterministic run is a distinct request the
  // backend caches separately (see main.py's cache_key) and the two answers
  // can sit side by side in the thread.
  // `drop` (P2.9) — inherited values the user rejected with the ✕ on a
  // "Carried over" chip, sent as `drop=place,vessel_class,intent`. The backend
  // refuses to inherit exactly those, at the point each is inherited; the
  // question itself is sent unchanged.
  function ask(q: string, options?: { llm?: "off"; drop?: string[]; position?: { lat: number; lon: number } }) {
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
        llmDisabled: options?.llm === "off",
      },
    ]);
    setActiveFocus(focus);

    // Persona is an explicit rendering choice only — Agent 9 renders with it,
    // no classifier reads it (Ground Rule 1). "unresolved" = don't send one.
    const personaParam = persona !== "unresolved" ? `&persona=${persona}` : "";
    const sessionParam = `&session_id=${encodeURIComponent(sessionId)}`;
    const llmParam = options?.llm === "off" ? "&llm=off" : "";
    const dropParam = options?.drop?.length ? `&drop=${encodeURIComponent(options.drop.join(","))}` : "";
    // P3.10 — a saved-location chip's own coordinates, an explicit position
    // that beats both the query text and the ambient GPS fix (api/main.py:
    // `lat`/`lon` given at all skips text/fix resolution entirely) — the
    // one case where a chip's own stored spot must win even indoors or over
    // a text place name it doesn't share the gazetteer's spelling of.
    const positionParam = options?.position
      ? `&lat=${options.position.lat}&lon=${options.position.lon}`
      : "";
    // The token rides on the URL: an EventSource cannot send a header, and
    // without it /query answers a signed-in user as a guest — no home port,
    // and a chat row nobody owns (chatbot plan C0.1).
    void Promise.all([restoring.current, tokenParam()]).then(([, authParam]) => {
      // The user may have switched chats while the context was restoring.
      if (chatIdRef.current !== sessionId) return;
      const es = new EventSource(
        `${API_BASE}/query?q=${encodeURIComponent(q)}${personaParam}${sessionParam}${positionParam || geoParam}${llmParam}${dropParam}${authParam}`,
      );
      sourceRef.current = es;
      es.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        if (data.type === "agent_span") {
          updateTurn(id, (t) => ({
            spans: [
              ...t.spans,
              {
                agent_name: data.agent_name,
                status: data.status,
                confidence_tier: data.confidence_tier,
                // P2.1 / P2.3 / P2.10 / P2.12 — all already on the wire.
                engine: data.engine,
                confidence_rationale: data.confidence_rationale,
                latency_ms: data.latency_ms,
                skip_reason: data.skip_reason,
              },
            ],
          }));
        } else if (data.type === "final_response") {
          updateTurn(id, (t) => {
            const loc = data.user_location as { lat?: number; lon?: number } | undefined;
            const coords: [number, number] | undefined =
              loc?.lon != null && loc?.lat != null ? [loc.lon, loc.lat] : undefined;
            const focus: QueryFocus | null = t.focus
              ? { ...t.focus, coords: coords ?? t.focus.coords }
              : coords
              ? { intent: "general", coords, nonce: focusNonce.current }
              : null;
            if (focus) setActiveFocus(focus);
            return { answer: data, streaming: false, focus };
          });
          const critical = criticalConditionFrom(data);
          if (critical) raiseCriticalAlert(critical);
          es.close();
        }
      };
      es.onerror = () => {
        updateTurn(id, { streaming: false, failed: true });
        es.close();
      };
    });
  }

  /** "Try again" — re-runs the question with every agent, keeping the answer
   *  it replaces as a version you can flip back to. Never offered on a distress
   *  answer: re-running an SOS re-files it on the authority queue. */
  function rerun(id: string) {
    const turn = turnsRef.current.find((t) => t.id === id);
    const sessionId = chatIdRef.current;
    if (!turn || !sessionId || turn.streaming || turn.answer?.distress_flag) return;
    sourceRef.current?.close();

    // The run that is on screen becomes version 1 (or stays wherever it
    // already was), and the new run is appended after it.
    const history = turnVersions(turn);
    updateTurn(id, {
      versions: [...history, { answer: null, spans: [] }],
      versionIndex: history.length,
      answer: null,
      spans: [],
      streaming: true,
      failed: false,
      renderedAs: null,
    });

    const personaParam = persona !== "unresolved" ? `&persona=${persona}` : "";
    // Same token as ask() sends, for the same reason (chatbot plan C0.1).
    void tokenParam().then((authParam) => {
      if (chatIdRef.current !== sessionId) return;
      const url = `${API_BASE}/query?q=${encodeURIComponent(turn.askedQuery)}${personaParam}&session_id=${encodeURIComponent(sessionId)}${geoParam}&fresh=1${authParam}`;
      const es = new EventSource(url);
      sourceRef.current = es;
      es.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        if (data.type === "agent_span") {
          updateTurn(id, (t) => ({ spans: [...t.spans, { agent_name: data.agent_name, status: data.status, confidence_tier: data.confidence_tier }] }));
        } else if (data.type === "final_response") {
          updateTurn(id, (t) => {
            const loc = data.user_location as { lat?: number; lon?: number } | undefined;
            const coords: [number, number] | undefined =
              loc?.lon != null && loc?.lat != null ? [loc.lon, loc.lat] : undefined;
            const focus: QueryFocus | null = t.focus
              ? { ...t.focus, coords: coords ?? t.focus.coords }
              : coords
              ? { intent: "general", coords, nonce: focusNonce.current }
              : null;
            if (focus) setActiveFocus(focus);
            return {
              answer: data,
              streaming: false,
              focus,
              versions: (t.versions ?? []).map((v, i) => (i === t.versionIndex ? { answer: data, spans: t.spans } : v)),
            };
          });
          {
            const critical = criticalConditionFrom(data);
            if (critical) raiseCriticalAlert(critical);
          }
          es.close();
          // /query?fresh=1 deliberately does NOT remember the turn — the question
          // is already in the window with the answer this one replaces. Push the
          // whole window again so it carries the new answer instead.
          const updated = turnsRef.current.map((t) => (t.id === id ? { ...t, answer: data } : t));
          void restoreContext(sessionId, updated).catch(() => {});
        }
      };
      es.onerror = () => {
        updateTurn(id, { streaming: false, failed: true });
        es.close();
      };
    });
  }

  /** Flip between the runs of one question. `answer`/`spans` mirror the chosen
   *  one so everything downstream reads a single answer, as it always has. */
  function showVersion(id: string, index: number) {
    updateTurn(id, (t) => {
      const v = turnVersions(t)[index];
      return v ? { versionIndex: index, answer: v.answer, spans: v.spans } : {};
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
              // P3.13 — a persona-only re-render (no `language` in the
              // request) still returns no vernacular text, same as before;
              // a language switch's translated text (or `null` on a
              // Bhashini/IndicTrans2 miss, degrading to English) replaces it.
              final_vernacular_response: result.final_vernacular_response ?? undefined,
              detected_language: result.language ?? t.answer.detected_language,
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
    rerun,
    showVersion,
    newChat,
    openChat,
    setRenderedAs,
    applyRender,
  };
}
