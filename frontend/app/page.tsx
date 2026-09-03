"use client";

// Ask (§4.2 `/`) — the conversational entry point to a map-first product.
// Two columns: the question and its answer on the left, the live chart on the
// right, because almost every answer here is spatial and a user should never
// have to navigate somewhere else to see where the answer applies.
import { useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Mic, Send } from "lucide-react";
import { AgentPill, AgentStrip, type AgentStatus } from "./components/AgentPill";
import { Button } from "./components/Button";
import { ConfidenceMeter } from "./components/ConfidenceMeter";
import { Panel } from "./components/Panel";
import { SourceChip } from "./components/SourceChip";
import { SourceNarration, type SourceSelection } from "./components/SourceNarration";
import { EmptyState, ErrorState, Skeleton } from "./components/States";
import { type ConfidenceTier } from "./components/Badge";
import { usePersona } from "./persona/context";

const MapView = dynamic(() => import("./components/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full" />,
});

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type AgentSpan = { agent_name: string; status: AgentStatus };
type Citation = { agent_name: string; dataset: string; acquisition_timestamp: string };
type FinalResponse = {
  final_english_response: string;
  final_vernacular_response?: string;
  detected_language?: string;
  confidence_tier: ConfidenceTier;
  citations?: Citation[];
  source_selections?: SourceSelection[];
};

// Real questions in the users' own words, not feature names. These double as
// the fastest way to try the product with no typing on a phone at sea.
const EXAMPLES = [
  "Is it safe to go out tomorrow morning near Thoothukudi?",
  "Where are the fishing zones closest to my port?",
  "How far am I from the maritime boundary?",
];

export default function AskPage() {
  const { persona } = usePersona();
  const [query, setQuery] = useState("");
  const [spans, setSpans] = useState<AgentSpan[]>([]);
  const [answer, setAnswer] = useState<FinalResponse | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [failed, setFailed] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  function ask(q: string) {
    if (!q.trim()) return;
    sourceRef.current?.close();
    setSpans([]);
    setAnswer(null);
    setFailed(false);
    setStreaming(true);

    // Persona is an explicit rendering choice only — Agent 9 renders with it,
    // no classifier reads it (Ground Rule 1). "unresolved" = don't send one.
    const personaParam = persona !== "unresolved" ? `&persona=${persona}` : "";
    const es = new EventSource(`${API_BASE}/query?q=${encodeURIComponent(q)}${personaParam}`);
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
      setFailed(true);
      es.close();
    };
  }

  return (
    <div className="grid h-full grid-rows-[auto_1fr] gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-rows-1">
      <div className="flex min-h-0 flex-col gap-4 lg:overflow-y-auto lg:pr-1">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Ask about conditions at sea
          </h1>
          <p className="mt-1 max-w-[58ch] text-sm text-ink-muted">
            Ask in plain English or Tamil. ORCA reads live weather, boundaries, depth and fishing
            advisories, then tells you what it found and where the numbers came from.
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(query);
          }}
          className="flex gap-2"
        >
          <label htmlFor="query" className="sr-only">
            Your question about marine conditions
          </label>
          <input
            id="query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Is it safe to go out tomorrow morning?"
            className="min-w-0 flex-1 rounded-md border border-hairline bg-shelf-1/80 px-3.5 py-3 text-sm text-ink placeholder:text-ink-dim transition-colors hover:border-hairline-strong focus:border-accent/60"
          />
          <Button
            type="button"
            variant="ghost"
            aria-label="Ask by voice"
            icon={<Mic className="size-4" />}
            className="px-3"
          >
            <span className="sr-only">Ask by voice</span>
          </Button>
          <Button type="submit" variant="primary" disabled={streaming || !query.trim()} icon={<Send className="size-4" />}>
            {streaming ? "Asking" : "Ask"}
          </Button>
        </form>

        {/* Differentiator 1 (§4.5): twelve agents run per query, and this is
            where a user watches that happen instead of a spinner. */}
        {spans.length > 0 && (
          <AgentStrip>
            {spans.map((s, i) => (
              <AgentPill key={`${s.agent_name}-${i}`} name={s.agent_name} status={s.status} />
            ))}
            {streaming && <AgentPill name="working" status="running" />}
          </AgentStrip>
        )}

        {failed && (
          <ErrorState
            title="ORCA could not reach the backend"
            body="The answer service did not respond. Check that the API is running, then ask again."
            action={
              <Button variant="ghost" onClick={() => ask(query)}>
                Ask again
              </Button>
            }
          />
        )}

        {streaming && !answer && (
          <Panel>
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="mt-2 h-4 w-full" />
            <Skeleton className="mt-2 h-4 w-5/6" />
          </Panel>
        )}

        {answer && (
          <Panel title="Answer">
            <p className="text-[15px] leading-relaxed text-ink">
              {answer.final_vernacular_response || answer.final_english_response}
            </p>
            {answer.final_vernacular_response &&
              answer.detected_language !== "en" &&
              answer.final_vernacular_response !== answer.final_english_response && (
                <div className="mt-3 rounded border border-hairline/60 bg-shelf-0/40 p-2.5 text-xs text-ink-muted">
                  <span className="font-semibold text-ink-dim block mb-1">English translation:</span>
                  <p className="leading-relaxed">{answer.final_english_response}</p>
                </div>
            )}
            <div className="mt-4 border-t border-hairline pt-3">
              <ConfidenceMeter tier={answer.confidence_tier} />
            </div>
            {/* Differentiator 4 — Agent 3's source-selection reasoning, on
                the card, not buried in the trace. */}
            {answer.source_selections && answer.source_selections.length > 0 && (
              <div className="mt-3 flex flex-col gap-1.5">
                {answer.source_selections.map((s) => (
                  <SourceNarration key={s.data_type} selection={s} />
                ))}
              </div>
            )}
            {answer.citations && answer.citations.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {answer.citations.map((c, i) => (
                  <SourceChip
                    key={i}
                    dataset={c.dataset}
                    acquisitionTimestamp={c.acquisition_timestamp}
                    detail={`Read by ${c.agent_name}.`}
                  />
                ))}
              </div>
            )}
          </Panel>
        )}

        {!answer && !streaming && !failed && (
          <EmptyState
            title="Start with one of these"
            body="Every answer carries the dataset it came from and how fresh that data is, so you can check the reasoning rather than trust it."
            action={
              <div className="flex flex-col items-start gap-1.5">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    onClick={() => {
                      setQuery(ex);
                      ask(ex);
                    }}
                    className="border-l border-hairline-strong py-0.5 pl-2.5 text-left text-sm text-ink-muted transition-colors hover:border-accent hover:text-ink"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            }
          />
        )}
      </div>

      <div className="min-h-75 lg:min-h-0">
        <MapView className="h-full w-full" showPanels={false} />
      </div>
    </div>
  );
}
