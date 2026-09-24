"use client";

// P6.6 — a minimal EventSource consumer for one pinned scenario query.
// Deliberately not useAskThread (650 lines of chat-thread/version/chip
// machinery this surface has none of): a scenario card runs exactly one
// query, once, with no follow-ups, no chat history and no persistence — the
// same `/query` SSE contract, the smallest client that reads it correctly.
import { useRef, useState } from "react";
import type { AgentSpan, FinalResponse } from "../ask/useAskThread";
import { API_BASE } from "../lib/apiBase";

export type ScenarioRunState = {
  spans: AgentSpan[];
  answer: FinalResponse | null;
  streaming: boolean;
  failed: boolean;
};

export function useScenarioRun() {
  const [state, setState] = useState<ScenarioRunState>({ spans: [], answer: null, streaming: false, failed: false });
  const sourceRef = useRef<EventSource | null>(null);

  function run(url: string) {
    sourceRef.current?.close();
    setState({ spans: [], answer: null, streaming: true, failed: false });
    const es = new EventSource(`${API_BASE}${url}`);
    sourceRef.current = es;
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type === "agent_span") {
        setState((s) => ({
          ...s,
          spans: [
            ...s.spans,
            {
              agent_name: data.agent_name,
              status: data.status,
              confidence_tier: data.confidence_tier,
              engine: data.engine,
              confidence_rationale: data.confidence_rationale,
              latency_ms: data.latency_ms,
              skip_reason: data.skip_reason,
            },
          ],
        }));
      } else if (data.type === "final_response") {
        setState((s) => ({ ...s, answer: data, streaming: false }));
        es.close();
      }
    };
    es.onerror = () => {
      setState((s) => ({ ...s, streaming: false, failed: true }));
      es.close();
    };
  }

  function reset() {
    sourceRef.current?.close();
    setState({ spans: [], answer: null, streaming: false, failed: false });
  }

  return { ...state, run, reset };
}
