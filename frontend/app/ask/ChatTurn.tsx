"use client";

// One turn of the thread: the user's bubble, the live agent trace while it
// streams, and the full answer card once it lands. Split out of page.tsx
// because that file renders one of these per turn now instead of exactly
// one ever — keeping it here is what keeps the thread's map() call readable.
import { motion } from "framer-motion";
import { ChevronDown, History, PowerOff, Radio } from "lucide-react";
import { AgentPill, AgentStrip, AGENT_ORDER, nextRunningAgent, type AgentStatus } from "../components/AgentPill";
import { Button } from "../components/Button";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { Panel } from "../components/Panel";
import { PersonaAnswerMatrix } from "../components/PersonaAnswerMatrix";
import { ProfilePrompt } from "../components/ProfilePrompt";
import { AnswerSpeaker } from "../components/AnswerSpeaker";
import { FormattedResponse } from "../components/FormattedResponse";
import { SourceChip } from "../components/SourceChip";
import { SourceNarration } from "../components/SourceNarration";
import { ErrorState, Skeleton } from "../components/States";
import { type QueryIntent } from "../lib/queryIntent";
import { type Persona } from "../persona/config";
import type { AgentSpan, Turn } from "./useAskThread";
import { turnVersions } from "./useAskThread";
import { RerunControl, CopyControl } from "./RerunControl";
import { IntentActions } from "./IntentActions";
import { RefusalCard, ResetNotice } from "./Disclosures";
import { SkippedNotice } from "./ReasoningEvidence";
import { useT } from "../i18n/useT";


const FOLLOW_UPS: Record<QueryIntent, string[]> = {
  safety: ["What are the wind and wave timings for the next 24 hours?", "Where is the nearest fishing zone right now?"],
  fishing: ["Is it safe to venture there tomorrow?", "How far is that zone from the maritime boundary?"],
  boundary: ["Is it safe to go out tomorrow morning?", "Where are the fishing zones closest to my position?"],
  current: ["Is it safe to go out tomorrow morning?", "What are the wave conditions right now?"],
  wave: ["Is it safe to go out tomorrow morning?", "What is the surface current speed and direction?"],
  wind: ["Is it safe to go out tomorrow morning?", "What are the wave conditions right now?"],
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
  hadEarlierAnswers,
  onRetry,
  onRerun,
  onShowVersion,
  onFollowUp,
}: {
  turn: Turn;
  persona: Persona;
  hadEarlierAnswers: boolean;
  onRetry: () => void;
  onRerun: () => void;
  onShowVersion: (index: number) => void;
  // `options` carries P2.11's LLM-off re-run, so the same handler that asks a
  // follow-up can also re-ask this question deterministically. `position` is a
  // place chip's own coordinates, so picking a place re-asks the same question there.
  onFollowUp: (q: string, options?: { llm?: "off"; position?: { lat: number; lon: number } }) => void;
  // P2.9 — the user rejecting an inherited value. Re-asks the question with
  // that value explicitly overridden rather than silently carried again.
}) {
  const t = useT();
  const { askedQuery, spans, answer, streaming, failed, renderedAs, focus } = turn;
  // P2.11 — read from the answer, which persists with the chat, rather than
  // from a flag on the turn, which the account store does not round-trip: a
  // deterministic answer must still say so after the chat is reopened.
  const llmOff = Boolean(turn.llmDisabled) || answer?.llm_enabled === false;
  // Re-running an SOS would re-file it on the authority queue, so the control
  // is absent there rather than disabled — there is nothing to explain.
  const versions = turnVersions(turn);
  // The action row under EVERY response, in the same order as a chat product's: copy, play, try
  // again. It is the same row on an answer, a chat reply and a distress answer; only try again is
  // absent on a distress answer.
  const answerText = answer ? answer.final_vernacular_response || answer.final_english_response || "" : "";
  const actionRow = answer && (
    <span className="flex flex-wrap items-center gap-0.5">
      <CopyControl text={answerText} />
      <AnswerSpeaker
        text={answerText}
        language={answer.detected_language ?? "en"}
        persona={renderedAs ?? persona}
        queryId={answer.query_id}
      />
      {!answer.distress_flag && (
        <RerunControl
          versionCount={versions.length}
          versionIndex={turn.versionIndex ?? 0}
          streaming={streaming}
          onRerun={onRerun}
          onShowVersion={onShowVersion}
        />
      )}
    </span>
  );

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
        <span className="font-mono text-[10px] font-semibold tracking-wider text-ink-dim uppercase">{t("chatTurn.you")}</span>
        <span className="min-w-0 break-words">{askedQuery}</span>
      </p>

      {/* Differentiator 1 (§4.5): up to twelve agents run per query. Inline
          while it thinks, staying permanently inspectable once the answer
          lands — with tick marks on all completed agents. */}
      {(displaySpans.length > 0 || runningAgent) && (
        <div className="flex min-w-0 max-w-full flex-col gap-1.5">
          {streaming && (
            <span className="inline-flex items-center gap-1.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
              <Radio className="size-3" aria-hidden="true" />
              {t("chatTurn.agentTrace")}
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
        </div>
      )}

      {failed && (
        <ErrorState
          title={t("chatTurn.backendErrorTitle")}
          body={t("chatTurn.backendErrorBody")}
          action={
            <Button variant="ghost" onClick={onRetry}>
              {t("chatTurn.askAgain")}
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
        <RefusalCard answer={answer} askedQuery={askedQuery} onFollowUp={onFollowUp} actions={actionRow} />
      )}

      {answer && (answer.outcome == null || answer.outcome === "ANSWERED" || answer.outcome === "DISTRESS") && (
        <>
          {/* Nothing is drawn above the answer (the user, 2026-10-10): no disclosure banner and no "carried over"
              chips. This is a chat: the model reads the last 20 turns to work out which place a message means, and the
              user corrects it by saying so. `answer.disclosures` and `answer.inherited` are still on the wire. */}
          <Panel title="Answer">
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
                  confidenceReason={answer.confidence_reason}
                  showBoundary={(answer.routing?.matched_intent_rows ?? []).includes("ZONES_TO_AVOID")}
                  weather={answer.weather_summary ?? { wave_height_m: null, wind_speed_ms: null, lightning_active: false, cyclone_alert: null }}
                  hazard={answer.hazard_breakdown ?? { imbl_distance_nm: null, imbl_alert_level: null, mpa_violation: false, mpa_alert_level: null }}
                  ocean={answer.ocean_summary ?? { tide: null, nearest_pfz: null, sector_status: null, productivity_diagnosis: null }}
                  citations={answer.citations ?? []}
                  thresholds={answer.risk_assessment.thresholds}
                  rawAnswer={answer}
                />
              )}

              {/* The chat's context window (orca/session.py). Only the WARNING is shown: when the
                  thread has earlier answers the backend no longer holds, this one was answered as a
                  new question, and saying so beats letting a follow-up fail silently. The routine
                  "Following on from N earlier messages" line and the "View on map" re-sync link were
                  removed from the card (the "Carried over" chips above the answer still name what
                  was inherited, and the shared map moves by itself when a question is asked). */}
              {answer.context_turns === 0 && hadEarlierAnswers && (
                <p className="flex items-center gap-1.5 text-[11px] text-caution">
                  <History className="size-3 shrink-0" aria-hidden="true" />
                  {t("chatTurn.contextExpired")}
                </p>
              )}

              {(() => {
                const answerBody = answer.final_vernacular_response || answer.final_english_response;
                // Always rendered. This used to be hidden whenever it equalled
                // the "VERDICT: reason" status line — which is exactly what a
                // provider outage produced, so the Response went blank
                // (chatbot plan C0.2e). The fallback now carries the readings,
                // and says when no model wrote it.
                const unwritten = answer.response_engine?.startsWith("Deterministic") ?? false;
                return (
                  <div className="flex flex-col gap-2.5">
                    <FormattedResponse
                      text={answerBody}
                      language={answer.detected_language}
                      large={(renderedAs ?? persona) === "fisherman"}
                    />
                    {unwritten && (
                      <p className="text-[11px] text-ink-dim">{t("chatTurn.writtenWithoutModel")}</p>
                    )}
                    {/* Under the text, in one row: copy, play, try again. */}
                    <div className="-ml-2">{actionRow}</div>
                  </div>
                );
              })()}

              <IntentActions actions={answer.intent_actions ?? []} />

              {answer.final_vernacular_response &&
                answer.detected_language !== "en" &&
                answer.final_vernacular_response !== answer.final_english_response && (
                  <div className="rounded-xl border border-hairline/60 bg-shelf-0/40 p-3 text-xs text-ink-muted">
                    <span className="font-semibold text-ink-dim block mb-1.5">{t("chatTurn.englishTranslation")}</span>
                    <FormattedResponse text={answer.final_english_response} />
                  </div>
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
                  the card, not buried in the trace. A dropdown, closed by default (2026-10-06):
                  the source narrations are long, and the card should lead with the answer. */}
              {((answer.source_selections && answer.source_selections.length > 0) ||
                (answer.citations && answer.citations.length > 0)) && (
                <details className="group border-t border-hairline/50 pt-3.5">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
                    <span>{t("chatTurn.sourcesProvenance")}</span>
                    <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />
                  </summary>
                  <div className="mt-2.5 flex flex-col gap-2">
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
                          detail={t("chatTurn.readBy", { agent: c.agent_name })}
                          agentName={c.agent_name}
                        />
                      ))}
                    </div>
                  )}
                  </div>
                </details>
              )}

              {/* Follow-up suggestions — the response never dead-ends into a
                  blank input; each chip re-asks with the new question. */}
              {focus && (
                <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline/50 pt-3.5">
                  <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
                    {t("chatTurn.followUp")}
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

              {/* P2.11 (`R-NEW-3`): the "Re-run this without any LLM" button was removed from the card
                  (2026-10-06). The backend still honours `llm=off`, and an answer that WAS produced
                  that way still says so just below. */}
              {llmOff && (
                <p className="flex items-start gap-1.5 rounded-lg border border-accent/40 bg-accent/5 p-2.5 text-[11px] leading-snug text-ink-muted">
                  <PowerOff className="mt-0.5 size-3 shrink-0 text-accent" aria-hidden="true" />
                  <span>
                    <span className="font-medium text-ink">{t("chatTurn.llmOffTitle")}</span>{" "}
                    {t("chatTurn.llmOffBody")}
                  </span>
                </p>
              )}

              {answer.profile_prompt && (
                <ProfilePrompt
                  prompt={answer.profile_prompt}
                  location={answer.user_location}
                  language={answer.detected_language}
                />
              )}
            </div>
          </Panel>

        </>
      )}
    </motion.div>
  );
}
