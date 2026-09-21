"use client";

// One turn of the thread: the user's bubble, the live agent trace while it
// streams, and the full answer card once it lands. Split out of page.tsx
// because that file renders one of these per turn now instead of exactly
// one ever — keeping it here is what keeps the thread's map() call readable.
import { motion } from "framer-motion";
import { History, MapPin, PowerOff, Radio } from "lucide-react";
import { AgentPill, AgentStrip, AGENT_ORDER, nextRunningAgent, type AgentStatus } from "../components/AgentPill";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { Panel } from "../components/Panel";
import { PersonaAnswerMatrix } from "../components/PersonaAnswerMatrix";
import { PersonaCorrection, type RenderResult } from "../components/PersonaCorrection";
import { Readout, ReadoutGrid } from "../components/Readout";
import { AnswerSpeaker } from "../components/AnswerSpeaker";
import { FormattedResponse } from "../components/FormattedResponse";
import { SourceChip } from "../components/SourceChip";
import { SourceNarration } from "../components/SourceNarration";
import { ErrorState, Skeleton } from "../components/States";
import { intentLabel, type QueryIntent } from "../lib/queryIntent";
import { type Persona } from "../persona/config";
import type { AgentSpan, InheritedValue, Turn } from "./useAskThread";
import { turnVersions } from "./useAskThread";
import { RerunControl } from "./RerunControl";
import { IntentActions } from "./IntentActions";
import { DisclosureBanner, RefusalCard, ResetNotice } from "./Disclosures";
import { InheritedChips, ReconciliationPanel, RoutingLine, SkippedNotice } from "./ReasoningEvidence";

const FOLLOW_UPS: Record<QueryIntent, string[]> = {
  safety: ["What are the wind and wave timings for the next 24 hours?", "Where is the nearest fishing zone right now?"],
  fishing: ["Is it safe to venture there tomorrow?", "How far is that zone from the maritime boundary?"],
  boundary: ["Is it safe to go out tomorrow morning?", "Where are the fishing zones closest to my position?"],
  current: ["Is it safe to go out tomorrow morning?", "What are the wave conditions right now?"],
  wave: ["Is it safe to go out tomorrow morning?", "What is the surface current speed and direction?"],
  general: ["Is it safe to go out tomorrow morning?", "Where are the fishing zones closest to my port?"],
};

// One pill per AGENT, not per span. A Critic-driven re-invocation makes the named specialist,
// Reporting and the Critic report a second time; drawing each span put the Critic in the strip twice
// (and pushed the strip to three rows) while the reasoning graph, which draws one node per agent,
// showed it once. Grouping keeps the two surfaces saying the same thing: one pill, a x2 marker, the
// summed time, and the LAST run's status and confidence (that is the state the answer was left in).
function groupRuns(spans: AgentSpan[]): { span: AgentSpan; runs: number; latency: number | undefined }[] {
  const order: string[] = [];
  const byAgent = new Map<string, { span: AgentSpan; runs: number; latency: number | undefined }>();
  for (const s of spans) {
    const seen = byAgent.get(s.agent_name);
    if (!seen) {
      order.push(s.agent_name);
      byAgent.set(s.agent_name, { span: s, runs: 1, latency: s.latency_ms });
    } else {
      byAgent.set(s.agent_name, {
        span: s,
        runs: seen.runs + 1,
        latency: (seen.latency ?? 0) + (s.latency_ms ?? 0),
      });
    }
  }
  return order.map((name) => byAgent.get(name)!);
}

export function ChatTurn({
  turn,
  persona,
  isMapFocus,
  hadEarlierAnswers,
  onViewOnMap,
  onRetry,
  onRerun,
  onShowVersion,
  onFollowUp,
  onDropInherited,
  onPersonaChange,
  onRendered,
}: {
  turn: Turn;
  persona: Persona;
  isMapFocus: boolean;
  hadEarlierAnswers: boolean;
  onViewOnMap: () => void;
  onRetry: () => void;
  onRerun: () => void;
  onShowVersion: (index: number) => void;
  // `options` carries P2.11's LLM-off re-run, so the same handler that asks a
  // follow-up can also re-ask this question deterministically.
  onFollowUp: (q: string, options?: { llm?: "off" }) => void;
  // P2.9 — the user rejecting an inherited value. Re-asks the question with
  // that value explicitly overridden rather than silently carried again.
  onDropInherited: (value: InheritedValue) => void;
  onPersonaChange: (p: Persona) => void;
  onRendered: (result: RenderResult) => void;
}) {
  const { askedQuery, spans, answer, streaming, failed, renderedAs, focus } = turn;
  // P2.11 — read from the answer, which persists with the chat, rather than
  // from a flag on the turn, which the account store does not round-trip: a
  // deterministic answer must still say so after the chat is reopened.
  const llmOff = Boolean(turn.llmDisabled) || answer?.llm_enabled === false;
  // Re-running an SOS would re-file it on the authority queue, so the control
  // is absent there rather than disabled — there is nothing to explain.
  const versions = turnVersions(turn);
  const rerunControl = answer && !answer.distress_flag && (
    <RerunControl
      versionCount={versions.length}
      versionIndex={turn.versionIndex ?? 0}
      streaming={streaming}
      onRerun={onRerun}
      onShowVersion={onShowVersion}
    />
  );
  const weatherCitation = answer?.citations?.find((c) => c.agent_name === "weather_intelligence");
  const runningAgent = streaming ? nextRunningAgent(spans) : null;
  const displaySpans: typeof spans =
    spans.length > 0
      ? spans
      : answer?.agent_confidence?.length
      ? answer.agent_confidence
      : answer
      ? AGENT_ORDER.map((name) => ({ agent_name: name, status: "ok" as AgentStatus }))
      : [];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="flex flex-col gap-3"
    >
      <p className="flex items-start gap-2 self-end rounded-2xl rounded-tr-sm border border-hairline-strong bg-shelf-3 px-4 py-2 text-sm text-ink shadow-sm">
        <span className="font-mono text-[10px] font-semibold tracking-wider text-ink-dim uppercase">You</span>
        <span className="min-w-0 break-words">{askedQuery}</span>
      </p>

      {/* Differentiator 1 (§4.5): up to ten agents run per query. Inline
          while it thinks, staying permanently inspectable once the answer
          lands — with tick marks on all completed agents. */}
      {(displaySpans.length > 0 || runningAgent) && (
        <div className="flex min-w-0 max-w-full flex-col gap-1.5">
          {streaming && (
            <span className="inline-flex items-center gap-1.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
              <Radio className="size-3" aria-hidden="true" />
              Agent trace
            </span>
          )}
          <AgentStrip>
            {groupRuns(displaySpans).map(({ span: s, runs, latency }, i) => (
              <AgentPill
                key={`${s.agent_name}-${i}`}
                name={s.agent_name}
                status={s.status}
                runs={runs}
                confidence={s.confidence_tier}
                // P2.1 — every pill names its engine; the safety pill reads
                // "Deterministic". P2.10 — the latency was already on the
                // wire and the pill already had a slot for it.
                engine={s.engine}
                latencyMs={latency}
                skipReason={s.skip_reason}
              />
            ))}
            {runningAgent && <AgentPill name={runningAgent} status="running" />}
          </AgentStrip>

          {/* P2.7 (`R-JUDGE-3`) — the routing decision, said out loud, so a
              compound query is visibly a compound query. P2.10 — the total
              beside it, because "how long did that take" is the other
              question every judge asks about an agent graph. */}
          {answer?.routing && answer.routing.matched_intent_rows.length > 0 && (
            <RoutingLine routing={answer.routing} latency={answer.latency} llmCalls={answer.llm_call_count} />
          )}
        </div>
      )}

      {failed && (
        <ErrorState
          title="ORCA could not reach the backend"
          body="The answer service did not respond. Check that the API is running, then ask again."
          action={
            <Button variant="ghost" onClick={onRetry}>
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

      {/* Phase 1 (P1.2/P1.3 render). A refused or unplaceable question is the
          WHOLE response — no verdict badge, no gauges, no weather panel, so
          there is nothing on screen to mistake for an answer. Answers cached
          before `outcome` existed have no field and render as before. */}
      {/* P2.14 — a reset is neither an answer nor a refusal. */}
      {answer && answer.outcome === "RESET" && <ResetNotice answer={answer} />}

      {answer && answer.outcome != null && answer.outcome !== "ANSWERED" && answer.outcome !== "DISTRESS" && answer.outcome !== "RESET" && (
        <RefusalCard answer={answer} onFollowUp={onFollowUp} actions={rerunControl} />
      )}

      {answer && (answer.outcome == null || answer.outcome === "ANSWERED" || answer.outcome === "DISTRESS") && (
        <>
          {/* Above the answer, never below it — see Disclosures.tsx. */}
          <DisclosureBanner disclosures={answer.disclosures} />

          {/* P2.9 / orca_final §16.2 — what this answer inherited from earlier
              turns, above the answer for the same reason a disclosure is:
              it changes what the answer is about. Removing a chip re-asks the
              question with that value explicitly dropped. */}
          {answer.inherited && answer.inherited.length > 0 && (
            <InheritedChips inherited={answer.inherited} onRemove={onDropInherited} />
          )}
          <Panel title="Answer" action={rerunControl}>
            <div className="flex flex-col gap-4">
              {/* Architecture §2.6 rendering matrix — same facts, structure
                  differs by persona. Only rendered once risk_assessment
                  exists — the distress bypass path never reaches
                  Reporting/risk_assessment. */}
              {/* `?.go_no_go`, not just truthiness: a safety agent that failed leaves
                  an EMPTY verdict object, which is truthy, and indexed the verdict
                  icon table with undefined — a hard render crash of the whole
                  card. No verdict means no verdict panel, and the answer text
                  (which then reads "UNKNOWN: no verdict computed") still shows. */}
              {answer.risk_assessment?.go_no_go && (
                <PersonaAnswerMatrix
                  persona={renderedAs ?? persona}
                  queryId={answer.query_id}
                  intent={focus?.intent ?? "general"}
                  agentsVerified={spans.filter((s) => s.status === "ok").length}
                  verdict={answer.risk_assessment.go_no_go}
                  // P2.2 (`R-JUDGE-2`) — a GO on a question that was not about
                  // safety is rendered as a quiet inline line, not a chip.
                  // CAUTION and NO_GO lead whatever was asked. The backend
                  // already decides this (reporting.should_lead_with_verdict,
                  // shipped as `lead_with_verdict`); the frontend ignored it
                  // and banner-ed every answer, which teaches people to skim
                  // the one line that matters when it is not GO.
                  leadWithVerdict={answer.lead_with_verdict ?? true}
                  reason={answer.risk_assessment.reason}
                  confidenceTier={answer.confidence_tier}
                  weather={answer.weather_summary ?? { wave_height_m: null, wind_speed_ms: null, lightning_active: false, cyclone_alert: null }}
                  hazard={answer.hazard_breakdown ?? { imbl_distance_nm: null, imbl_alert_level: null, mpa_violation: false, mpa_alert_level: null }}
                  ocean={answer.ocean_summary ?? { tide: null, nearest_pfz: null, sector_status: null, productivity_diagnosis: null }}
                  citations={answer.citations ?? []}
                />
              )}

              {/* The chat's context window (orca/session.py). Stated both
                  ways: which earlier messages this answer followed on from,
                  or — when the thread has earlier answers the backend no
                  longer holds — that it was answered as a new question,
                  rather than letting a follow-up fail silently. */}
              {answer.context_turns != null && (answer.context_turns > 0 || hadEarlierAnswers) && (
                <p
                  className={`flex items-center gap-1.5 text-[11px] ${
                    answer.context_turns > 0 ? "text-ink-dim" : "text-caution"
                  }`}
                >
                  <History className="size-3 shrink-0" aria-hidden="true" />
                  {answer.context_turns > 0
                    ? `Following on from ${answer.context_turns} earlier ${answer.context_turns === 1 ? "message" : "messages"} in this chat`
                    : "Earlier messages in this chat have expired, so this was answered as a new question — name your location again if it matters."}
                </p>
              )}

              {/* The shared map already moved for this question the moment it
                  was asked — clicking re-syncs it, useful once other turns
                  have moved it elsewhere. */}
              {focus && (
                <button
                  type="button"
                  onClick={onViewOnMap}
                  className="flex items-center gap-1.5 self-start text-[11px] text-ink-dim transition-colors hover:text-accent"
                >
                  <MapPin className="size-3 text-accent" aria-hidden="true" />
                  {(() => {
                    const label = intentLabel(focus.intent, answer?.user_location?.place_source === "regional_default");
                    return isMapFocus ? `Map focused on ${label}` : `View on map — ${label}`;
                  })()}
                </button>
              )}

              {(() => {
                const answerBody = answer.final_vernacular_response || answer.final_english_response;
                // Agent 9 emits "VERDICT: reason" as the whole English
                // response today — identical to what PersonaAnswerMatrix's
                // status row already shows above. Skip the repeat; a
                // vernacular translation still differs, so it still renders.
                const verdictLine = answer.risk_assessment?.go_no_go
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

              <IntentActions actions={answer.intent_actions ?? []} />

              {answer.final_vernacular_response &&
                answer.detected_language !== "en" &&
                answer.final_vernacular_response !== answer.final_english_response && (
                  <div className="rounded-xl border border-hairline/60 bg-shelf-0/40 p-3 text-xs text-ink-muted">
                    <span className="font-semibold text-ink-dim block mb-1.5">English translation:</span>
                    <FormattedResponse text={answer.final_english_response} />
                  </div>
              )}

              {/* P2.4 (`R-PS-5`) — where two sources covering the same
                  variable were compared. The disagreements are already above
                  the answer as disclosures; this is the full record, including
                  the pairs that agreed, because "how do you know your sources
                  agree" deserves the comparison and not a reassurance. */}
              {answer.reconciliation && answer.reconciliation.length > 0 && (
                <ReconciliationPanel rows={answer.reconciliation} />
              )}

              {/* P2.7/P2.12 — work deliberately not done, and why. */}
              {answer.skipped_agents && answer.skipped_agents.length > 0 && (
                <SkippedNotice skipped={answer.skipped_agents} />
              )}

              <div className="border-t border-hairline pt-3.5">
                {/* P2.3 (`R-JUDGE-4`) — the derivation, not just the tier. */}
                <ConfidenceMeter tier={answer.confidence_tier} inputs={answer.confidence_inputs} />
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

              {/* Follow-up suggestions — the response never dead-ends into a
                  blank input; each chip re-asks with the new question. */}
              {focus && (
                <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline/50 pt-3.5">
                  <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
                    Follow-up
                  </span>
                  {FOLLOW_UPS[focus.intent].map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => onFollowUp(q)}
                      className="rounded-lg border border-hairline/60 bg-shelf-2/50 px-2.5 py-1.5 text-[11px] text-ink-muted transition-colors hover:border-ocean-cyan/60 hover:bg-shelf-2 hover:text-ink"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}

              {/* P2.11 (`R-NEW-3`) — prove the LLM is optional, live. Re-asks
                  this exact question with every provider disabled; the verdict,
                  thresholds, geofence, citations and confidence all still
                  render, and only the prose degrades to the deterministic
                  line. The two answers sit side by side in the thread, which
                  is the whole demonstration. */}
              {!llmOff && (
                <button
                  type="button"
                  onClick={() => onFollowUp(askedQuery, { llm: "off" })}
                  className="flex w-fit items-center gap-1.5 self-start rounded-lg border border-hairline/60 bg-shelf-2/50 px-2.5 py-1.5 text-[11px] text-ink-muted transition-colors hover:border-ocean-cyan/60 hover:bg-shelf-2 hover:text-ink"
                >
                  <PowerOff className="size-3 text-accent" aria-hidden="true" />
                  Re-run this without any LLM
                </button>
              )}

              {llmOff && (
                <p className="flex items-start gap-1.5 rounded-lg border border-accent/40 bg-accent/5 p-2.5 text-[11px] leading-snug text-ink-muted">
                  <PowerOff className="mt-0.5 size-3 shrink-0 text-accent" aria-hidden="true" />
                  <span>
                    <span className="font-medium text-ink">Answered with every LLM provider disabled.</span>{" "}
                    The verdict, thresholds, boundary distance, citations and confidence above are all
                    deterministic code — only the wording degrades to the plain verdict line.
                  </span>
                </p>
              )}

              <PersonaCorrection
                queryId={answer.query_id}
                currentPersona={renderedAs ?? persona}
                onPersonaChange={onPersonaChange}
                onRendered={onRendered}
              />
            </div>
          </Panel>

          {/* Weather banner — same Panel/ReadoutGrid pattern /safety already
              uses, kept below the prediction response rather than above it. */}
          {answer.weather_summary && (
            <Panel
              title="Weather"
              action={
                weatherCitation && (
                  <SourceChip dataset={weatherCitation.dataset} acquisitionTimestamp={weatherCitation.acquisition_timestamp} />
                )
              }
            >
              <ReadoutGrid cols={4}>
                <Readout label="Wave height" value={answer.weather_summary.wave_height_m ?? "—"} unit="m" />
                <Readout
                  label="Wind speed"
                  value={
                    answer.weather_summary.wind_speed_ms != null
                      ? (answer.weather_summary.wind_speed_ms * 3.6).toFixed(1)
                      : "—"
                  }
                  unit="km/h"
                />
                <Readout
                  label="Lightning"
                  value={
                    <Badge tone={answer.weather_summary.lightning_active ? "no-go" : "go"}>
                      {answer.weather_summary.lightning_active ? "Active" : "Clear"}
                    </Badge>
                  }
                />
                <Readout
                  label="Cyclone alert"
                  value={
                    <Badge tone={answer.weather_summary.cyclone_alert ? "no-go" : "go"}>
                      {answer.weather_summary.cyclone_alert ?? "None"}
                    </Badge>
                  }
                />
              </ReadoutGrid>
            </Panel>
          )}
        </>
      )}
    </motion.div>
  );
}
