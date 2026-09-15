"use client";

// Thread state for the Ask chat: one EventSource pipeline (unchanged from the
// original single-turn version) fanning its events into a growing list of
// turns instead of replacing a single answer. Persisted to localStorage so
// the thread survives a refresh (and a new tab); "New chat" is the explicit
// way to clear it rather than relying on storage boundaries to do that.
import { useEffect, useRef, useState } from "react";
import type { AgentStatus } from "../components/AgentPill";
import type { ConfidenceTier, Verdict } from "../components/Badge";
import type { HazardBreakdown, OceanSummary, WeatherSummary, Citation } from "../components/PersonaAnswerMatrix";
import type { RenderResult } from "../components/PersonaCorrection";
import type { SourceSelection } from "../components/SourceNarration";
import type { QueryFocus } from "../components/MapView";
import { type Persona } from "../persona/config";
import { API_BASE } from "../lib/apiBase";
import { classifyQueryIntent, matchRegionInQuery } from "../lib/queryIntent";
import { getSessionId } from "../lib/session";

export type AgentSpan = { agent_name: string; status: AgentStatus };
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
};

export type Turn = {
  id: string;
  askedQuery: string;
  spans: AgentSpan[];
  answer: FinalResponse | null;
  streaming: boolean;
  failed: boolean;
  renderedAs: Persona | null;
  focus: QueryFocus | null;
};

const STORAGE_KEY = "orca-ask-thread";

function loadTurns(): Turn[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    // A turn still marked "streaming" belongs to a tab that reloaded mid
    // answer — its EventSource is gone, so it would hang forever if left as is.
    const turns = JSON.parse(raw) as Turn[];
    return turns.map((t) => (t.streaming ? { ...t, streaming: false, failed: true } : t));
  } catch {
    return [];
  }
}

export function useAskThread(persona: Persona) {
  // null means "not yet hydrated" — distinct from a real empty thread ([]).
  // Starting at null (rather than reading localStorage in useState's
  // initializer) avoids mismatching the server-rendered HTML and crashing
  // hydration, the exact pitfall persona/context.tsx documents for its own
  // storage read. Checking `savedTurns === null` (state), not a one-shot
  // ref flag, is what keeps the write effect from firing with a stale empty
  // array — a ref flag gets consumed by React Strict Mode's dev-only double
  // effect invocation before the restore's setSavedTurns ever lands.
  const [savedTurns, setSavedTurns] = useState<Turn[] | null>(null);
  const turns = savedTurns ?? [];
  const [activeFocus, setActiveFocus] = useState<QueryFocus | null>(null);
  const sourceRef = useRef<EventSource | null>(null);
  const focusNonce = useRef(0);
  const lastPersona = useRef(persona);

  useEffect(() => {
    // Same client-only external-store sync as persona/context.tsx's own
    // localStorage read — not a case the "avoid setState in effect" rule
    // has an exception for, but the standard hydration-safe pattern for it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSavedTurns(loadTurns());
  }, []);

  useEffect(() => {
    if (savedTurns === null) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(savedTurns));
    } catch {
      /* private mode / storage disabled — thread just won't survive a refresh */
    }
  }, [savedTurns]);

  // Switching persona (nav-wide setting) changes how an answer would render,
  // so a stale thread from the old persona stays around — clear it rather
  // than leave mismatched answers on screen. usePersona() itself always
  // starts a mount at "unresolved" and syncs the real value from
  // localStorage a moment later (hydration-safe pattern) — that first
  // resolution is not a real switch, so it must not wipe a restored thread.
  useEffect(() => {
    if (lastPersona.current === persona) return;
    const previous = lastPersona.current;
    lastPersona.current = persona;
    // ponytail: treats every unresolved-origin transition as hydration, so a
    // user who explicitly sets persona to Unresolved then picks one won't
    // clear the thread either — narrow the check to "first render only" if
    // that mid-session case needs to clear too.
    if (previous === "unresolved") return;
    newChat();
  }, [persona]);

  function newChat() {
    sourceRef.current?.close();
    setSavedTurns([]);
    setActiveFocus(null);
  }

  function updateTurn(id: string, patch: Partial<Turn> | ((t: Turn) => Partial<Turn>)) {
    setSavedTurns((prev) =>
      (prev ?? []).map((t) => (t.id === id ? { ...t, ...(typeof patch === "function" ? patch(t) : patch) } : t)),
    );
  }

  function ask(q: string) {
    if (!q.trim()) return;
    sourceRef.current?.close();

    const id = crypto.randomUUID();
    // Chart focus reacts to the question itself, not the answer — real
    // layers (boundaries/PFZ) and a real fit-to-geometry, so the map moves
    // the moment you ask rather than waiting on the round trip (plan §7/§8).
    focusNonce.current += 1;
    const focus: QueryFocus = { intent: classifyQueryIntent(q), regionId: matchRegionInQuery(q), nonce: focusNonce.current };
    setSavedTurns((prev) => [
      ...(prev ?? []),
      { id, askedQuery: q, spans: [], answer: null, streaming: true, failed: false, renderedAs: null, focus },
    ]);
    setActiveFocus(focus);

    // Persona is an explicit rendering choice only — Agent 9 renders with it,
    // no classifier reads it (Ground Rule 1). "unresolved" = don't send one.
    const personaParam = persona !== "unresolved" ? `&persona=${persona}` : "";
    const sessionParam = `&session_id=${encodeURIComponent(getSessionId())}`;
    const es = new EventSource(`${API_BASE}/query?q=${encodeURIComponent(q)}${personaParam}${sessionParam}`);
    sourceRef.current = es;
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type === "agent_span") {
        updateTurn(id, (t) => ({ spans: [...t.spans, { agent_name: data.agent_name, status: data.status }] }));
      } else if (data.type === "final_response") {
        updateTurn(id, { answer: data, streaming: false });
        es.close();
      }
    };
    es.onerror = () => {
      updateTurn(id, { streaming: false, failed: true });
      es.close();
    };
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
    streaming: turns.some((t) => t.streaming),
    activeFocus,
    setActiveFocus,
    ask,
    newChat,
    setRenderedAs,
    applyRender,
  };
}
