"use client";

// Ask (§4.2, now at `/ask` — `/` itself is the public landing page) — the
// conversational entry point to a map-first product.
// Two columns: the question and its answer on the left, the live chart on the
// right, because almost every answer here is spatial and a user should never
// have to navigate somewhere else to see where the answer applies.
import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Compass, Fish, MapPin, Radio, Send, Waves } from "lucide-react";
import { AgentPill, AgentStrip, type AgentStatus } from "../components/AgentPill";
import { Button } from "../components/Button";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { Panel } from "../components/Panel";
import { PersonaAnswerMatrix, type HazardBreakdown, type OceanSummary, type WeatherSummary } from "../components/PersonaAnswerMatrix";
import { SourceChip } from "../components/SourceChip";
import { SourceNarration, type SourceSelection } from "../components/SourceNarration";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { type ConfidenceTier, type Verdict } from "../components/Badge";
import { AnswerSpeaker } from "../components/AnswerSpeaker";
import { FormattedResponse } from "../components/FormattedResponse";
import { PersonaCorrection } from "../components/PersonaCorrection";
import { useVoiceInput, VoiceMicButton, VoiceInputPanel } from "../components/VoiceInput";
import { usePersona } from "../persona/context";
import { type Persona } from "../persona/config";
import { API_BASE } from "../lib/apiBase";
import { classifyQueryIntent, INTENT_LABEL, type QueryIntent } from "../lib/queryIntent";
import type { QueryFocus } from "../components/MapView";

const MapView = dynamic(() => import("../components/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full" />,
});

const INTENT_ICON: Record<QueryIntent, typeof Waves> = {
  fishing: Fish,
  boundary: Compass,
  safety: Waves,
  general: MapPin,
};

type AgentSpan = { agent_name: string; status: AgentStatus };
type Citation = { agent_name: string; dataset: string; acquisition_timestamp: string };
type FinalResponse = {
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

// Real questions in the users' own words, not feature names. These double as
// the fastest way to try the product with no typing on a phone at sea.
const EXAMPLES = [
  "Is it safe to go out tomorrow morning near Thoothukudi?",
  "Where are the fishing zones closest to my port?",
  "How far am I from the maritime boundary?",
];

export default function AskPage() {
  const { persona } = usePersona();
  const reduceMotion = useReducedMotion();
  const [query, setQuery] = useState("");
  const [spans, setSpans] = useState<AgentSpan[]>([]);
  const [answer, setAnswer] = useState<FinalResponse | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [failed, setFailed] = useState(false);
  // Set only by the persona-correction control (differentiator 7) — never
  // by ask(). Tracked separately from `persona` (the nav-wide setting) so
  // correcting one answer's rendering never silently changes what the next
  // /query call sends.
  const [renderedAs, setRenderedAs] = useState<Persona | null>(null);
  const [focus, setFocus] = useState<QueryFocus | null>(null);
  // Separate from `query` (the live input value) so editing the box after
  // an answer arrives — without re-asking — never mismatches the echoed
  // question against the answer still on screen.
  const [askedQuery, setAskedQuery] = useState("");
  const sourceRef = useRef<EventSource | null>(null);
  const focusNonce = useRef(0);

  // Switching persona (nav-wide setting) changes how an answer would render,
  // so a stale answer from the old persona stays around — clear the
  // conversation rather than leave a mismatched one on screen. Skips the
  // mount render (ref starts already caught up) so landing on /ask never
  // wipes a fresh query.
  const lastPersona = useRef(persona);
  useEffect(() => {
    if (lastPersona.current === persona) return;
    lastPersona.current = persona;
    sourceRef.current?.close();
    setQuery("");
    setSpans([]);
    setAnswer(null);
    setRenderedAs(null);
    setFailed(false);
    setStreaming(false);
    setFocus(null);
  }, [persona]);

  const voice = useVoiceInput({
    onTranscriptConfirmed: (text) => {
      setQuery(text);
      ask(text);
    },
  });

  function ask(q: string) {
    if (!q.trim()) return;
    sourceRef.current?.close();
    setSpans([]);
    setAnswer(null);
    setRenderedAs(null);
    setFailed(false);
    setStreaming(true);
    // Chart focus reacts to the question itself, not the answer — real
    // layers (boundaries/PFZ) and a real fit-to-geometry, so the map moves
    // the moment you ask rather than waiting on the round trip (plan §7/§8).
    focusNonce.current += 1;
    setFocus({ intent: classifyQueryIntent(q), nonce: focusNonce.current });
    setAskedQuery(q);

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
    <div className="grid h-full grid-rows-[auto_1fr] gap-6 p-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:grid-rows-1 lg:p-7">
      <div className="flex min-h-0 flex-col gap-5 lg:overflow-y-auto lg:pr-2">
        <div className="border-b border-hairline/60 pb-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="size-2 rounded-full bg-ocean-cyan beacon-pulse" aria-hidden="true" />
            <span className="font-mono text-[10px] font-bold tracking-widest text-ocean-cyan uppercase">
              ORCA INTELLIGENCE CONSOLE // VHF & SATELLITE
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">
            Ask about conditions at sea
          </h1>
          <p className="mt-1.5 max-w-[62ch] text-sm leading-relaxed text-ink-muted">
            Ask in plain English or Tamil. ORCA evaluates live ocean weather, maritime boundary standoff,
            depth contours, and fishing advisories with full citation provenance.
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(query);
          }}
          className="flex flex-col gap-3 rounded-xl border border-hairline/70 bg-shelf-1/30 p-3.5 shadow-inner"
        >
          <div className="flex gap-2">
            <label htmlFor="query" className="sr-only">
              Your question about marine conditions
            </label>
            <div className="relative flex-1">
              <input
                id="query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Is it safe to go out tomorrow morning near Thoothukudi?"
                className="w-full rounded-xl border border-hairline bg-shelf-1/90 px-4 py-3 text-sm text-ink placeholder:text-ink-dim/60 transition-all hover:border-hairline-strong focus:border-ocean-cyan/70 focus:bg-shelf-2/90 shadow-inner"
              />
            </div>
            {/* Voice ingress (plan §6 D1 Day 16-17): mic sits right next to
                Ask since both feed the same query pipeline — voice is a
                pre-step onto the text box, not a second, separate control. */}
            <VoiceMicButton voice={voice} isFisherman={persona === "fisherman"} />
            <Button
              type="submit"
              variant="primary"
              disabled={streaming || !query.trim()}
              icon={<Send className="size-4" />}
              className="px-5 font-bold"
            >
              {streaming ? "Asking" : "Ask"}
            </Button>
          </div>

          {/* Quick preset sector query chips — each icon reflects the same
              intent classifier that drives the chart's query focus, so a
              chip already previews what asking it will do to the map. */}
          <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline/50 pt-2.5">
            <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
              Presets
            </span>
            {EXAMPLES.map((ex) => {
              const Icon = INTENT_ICON[classifyQueryIntent(ex)];
              return (
              <button
                key={ex}
                type="button"
                onClick={() => {
                  setQuery(ex);
                  ask(ex);
                }}
                disabled={streaming}
                className="inline-flex items-center gap-1.5 rounded-lg border border-hairline/60 bg-shelf-2/50 px-2.5 py-1.5 text-[11px] text-ink-muted transition-colors hover:border-ocean-cyan/60 hover:bg-shelf-2 hover:text-ink disabled:opacity-50"
              >
                <Icon className="size-3 shrink-0 text-ink-dim" aria-hidden="true" />
                {ex}
              </button>
              );
            })}
          </div>
        </form>

        {/* Waveform while recording, transcript confirmation once done —
            requires an explicit "Ask" before it becomes a query, never
            auto-submitted (a mishearing on a safety query is a safety
            incident, not a UX annoyance). */}
        <VoiceInputPanel voice={voice} />

        {/* Differentiator 1 (§4.5): twelve agents run per query, and this is
            where a user watches that happen instead of a spinner. */}
        {spans.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="inline-flex items-center gap-1.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
              <Radio className="size-3" aria-hidden="true" />
              Agent trace
            </span>
            <AgentStrip>
              {spans.map((s, i) => (
                <AgentPill key={`${s.agent_name}-${i}`} name={s.agent_name} status={s.status} />
              ))}
              {streaming && <AgentPill name="working" status="running" />}
            </AgentStrip>
          </div>
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
          <>
            <p className="flex items-start gap-2 self-end rounded-2xl rounded-tr-sm border border-hairline-strong bg-shelf-3 px-4 py-2 text-sm text-ink shadow-sm">
              <span className="font-mono text-[10px] font-semibold tracking-wider text-ink-dim uppercase">You</span>
              <span className="min-w-0 break-words">{askedQuery}</span>
            </p>
          <Panel title="Answer">
            <div className="flex flex-col gap-4">
              {/* Architecture §2.6 rendering matrix — same facts, structure
                  differs by persona (fisherman banner, navigator readout,
                  researcher stats + export, authority threat level + CAP
                  preview). Only rendered once risk_assessment exists — the
                  distress bypass path never reaches Reporting/risk_assessment. */}
              {answer.risk_assessment && (
                <PersonaAnswerMatrix
                  persona={renderedAs ?? persona}
                  queryId={answer.query_id}
                  verdict={answer.risk_assessment.go_no_go}
                  reason={answer.risk_assessment.reason}
                  confidenceTier={answer.confidence_tier}
                  weather={answer.weather_summary ?? { wave_height_m: null, wind_speed_ms: null, lightning_active: false, cyclone_alert: null }}
                  hazard={answer.hazard_breakdown ?? { imbl_distance_nm: null, imbl_alert_level: null, mpa_violation: false, mpa_alert_level: null }}
                  ocean={answer.ocean_summary ?? { tide: null, nearest_pfz: null, sector_status: null, productivity_diagnosis: null }}
                  citations={answer.citations ?? []}
                />
              )}

              {/* The chart already moved for this question (ask() sets focus
                  immediately) — this line is what ties the answer to that
                  move, rather than leaving the map to look like a second,
                  unrelated panel. */}
              {focus && (
                <p className="flex items-center gap-1.5 text-[11px] text-ink-dim">
                  <MapPin className="size-3 text-accent" aria-hidden="true" />
                  Chart focused on {INTENT_LABEL[focus.intent]}
                </p>
              )}

              {(() => {
                const answerBody = answer.final_vernacular_response || answer.final_english_response;
                // Agent 9 emits "VERDICT: reason" as the whole English
                // response today — identical to what VerdictBadge already
                // shows above. Rendering it again here would just be the
                // same sentence twice; skip it and keep this space for
                // content that isn't already on screen (a vernacular
                // translation still differs, so it still renders).
                const verdictLine = answer.risk_assessment
                  ? `${answer.risk_assessment.go_no_go}: ${answer.risk_assessment.reason}`
                  : null;
                const isRedundant = verdictLine != null && answerBody.trim() === verdictLine.trim();
                return (
                  <div className="flex flex-col gap-2.5">
                    {!isRedundant && <FormattedResponse text={answerBody} />}
                    <AnswerSpeaker
                      text={answerBody}
                      language={answer.detected_language ?? "en"}
                      persona={renderedAs ?? persona}
                      queryId={answer.query_id}
                    />
                  </div>
                );
              })()}

              {answer.final_vernacular_response &&
                answer.detected_language !== "en" &&
                answer.final_vernacular_response !== answer.final_english_response && (
                  <div className="rounded-xl border border-hairline/60 bg-shelf-0/40 p-3 text-xs text-ink-muted">
                    <span className="font-semibold text-ink-dim block mb-1.5">English translation:</span>
                    <FormattedResponse text={answer.final_english_response} />
                  </div>
              )}

              <div className="border-t border-hairline pt-3.5">
                <ConfidenceMeter tier={answer.confidence_tier} />
              </div>

              {/* Differentiator 4 — Agent 3's source-selection reasoning, on
                  the card, not buried in the trace. */}
              {((answer.source_selections && answer.source_selections.length > 0) ||
                (answer.citations && answer.citations.length > 0)) && (
                <div className="flex flex-col gap-2 border-t border-hairline/50 pt-3.5">
                  <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
                    Sources &amp; provenance
                  </span>
                  {answer.source_selections && answer.source_selections.length > 0 && (
                    <div className="flex flex-col gap-1.5">
                      {answer.source_selections.map((s) => (
                        <SourceNarration key={s.data_type} selection={s} />
                      ))}
                    </div>
                  )}
                  {answer.citations && answer.citations.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
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
                </div>
              )}

              <PersonaCorrection
                queryId={answer.query_id}
                currentPersona={renderedAs ?? persona}
                onPersonaChange={setRenderedAs}
                onRendered={(result) =>
                  setAnswer((prev) =>
                    prev
                      ? {
                          ...prev,
                          final_english_response: result.final_english_response,
                          final_vernacular_response: undefined, // /render is English-only (translation stays at the edge, Agent 1)
                          confidence_tier: result.confidence_tier as ConfidenceTier,
                          citations: result.citations,
                        }
                      : prev,
                  )
                }
              />
            </div>
          </Panel>
          </>
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

      <div className="relative min-h-[400px] overflow-hidden rounded-2xl border border-hairline bg-shelf-1/60 shadow-2xl lg:min-h-0">
        {/* Depth shading + surface currents on by default (plan §9) — the
            only Ask-specific default; /map and /voyage keep their own tuned
            defaults via the same `initialLayers` prop. */}
        <MapView
          className="h-full w-full"
          initialLayers={{ srvBathymetry: true, currents: true }}
          queryFocus={focus}
          showLayerPanel={false}
          showRegionSwitcher={false}
          showLegends={false}
          showSoundingHud={false}
        />
      </div>
    </div>
  );
}
