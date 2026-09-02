"use client";

import { useRef, useState } from "react";
import { Badge, confidenceTone } from "./components/Badge";
import { Card } from "./components/Card";
import { SourceChip } from "./components/SourceChip";

type AgentSpan = { agent_name: string; status: string };
type Citation = { agent_name: string; dataset: string; acquisition_timestamp: string };
type FinalResponse = {
  final_english_response: string;
  confidence_tier: "HIGH" | "MEDIUM" | "LOW_DATA";
  citations?: Citation[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Ask (§4.2 `/`): conversational entry point, agent activity strip,
// progressively-rendering answer card (plan §4 S6 Day 5). SSE consumption
// against S1's `/query` endpoint; real routing and citations arrive once
// S1 wires the live graph in — this renders whatever shape lands, citations
// included when present, so the swap from mock to real payload is silent.
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
        <Card className="[&_*]:motion-safe:transition-opacity">
          <p aria-live="polite" className="text-sm">
            {answer.final_english_response}
          </p>
          <div className="mt-3 flex items-center gap-2">
            <Badge tone={confidenceTone(answer.confidence_tier)}>{answer.confidence_tier.replace("_", "-")}</Badge>
          </div>
          {answer.citations && answer.citations.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1">
              {answer.citations.map((c, i) => (
                <li key={i}>
                  <SourceChip dataset={c.dataset} acquisitionTimestamp={c.acquisition_timestamp} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}
