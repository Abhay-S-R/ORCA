"use client";

import { useRef, useState } from "react";

type AgentSpan = { agent_name: string; status: string };
type FinalResponse = { final_english_response: string; confidence_tier: string };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Ask (§4.2 `/`): conversational entry point, agent activity strip, answer
// card. Phase 0 wires this to the mock SSE stream only — real routing,
// persona-aware rendering and the mini-map land in Phase 1 (§6).
export default function AskPage() {
  const [query, setQuery] = useState("");
  const [spans, setSpans] = useState<AgentSpan[]>([]);
  const [answer, setAnswer] = useState<FinalResponse | null>(null);
  const [streaming, setStreaming] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  function ask(e: React.FormEvent) {
    e.preventDefault();
    sourceRef.current?.close();
    setSpans([]);
    setAnswer(null);
    setStreaming(true);

    const es = new EventSource(`${API_BASE}/query?q=${encodeURIComponent(query)}`);
    sourceRef.current = es;
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type === "agent_span") {
        setSpans((prev) => [...prev, { agent_name: data.agent_name, status: data.status }]);
      } else if (data.type === "final_response") {
        setAnswer(data);
        setStreaming(false);
        es.close();
      }
    };
    es.onerror = () => {
      setStreaming(false);
      es.close();
    };
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold mb-4">Ask ORCA</h1>
      <form onSubmit={ask} className="flex gap-2 mb-6">
        <label htmlFor="query" className="sr-only">
          Ask a question about marine conditions
        </label>
        <input
          id="query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Is it safe to go to sea tomorrow morning near Thoothukudi?"
          className="flex-1 rounded border border-black/20 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2"
        />
        <button
          type="submit"
          disabled={streaming}
          className="rounded bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          {streaming ? "Asking…" : "Ask"}
        </button>
      </form>

      {/* Live activity strip (§4.4) — simplified pending Phase 3's real span/trace UI */}
      {spans.length > 0 && (
        <ul aria-live="polite" className="mb-4 flex flex-wrap gap-2">
          {spans.map((s, i) => (
            <li key={i} className="rounded-full bg-black/5 px-3 py-1 text-xs">
              {s.agent_name}
            </li>
          ))}
        </ul>
      )}

      {answer && (
        <div aria-live="polite" className="rounded border border-black/10 p-4">
          <p className="text-sm">{answer.final_english_response}</p>
          <p className="mt-2 text-xs text-black/50">confidence: {answer.confidence_tier}</p>
        </div>
      )}
    </div>
  );
}
