"use client";

// Advisory feedback (plan §4.10) — Helpful / Not accurate / Report issue on
// every advisory card. One tap, no dialog; "Report issue" reveals an
// optional free-text box. Icons ALWAYS carry a visible text label (fisherman
// surface rule), placed below the verdict, never competing with it.
//
// The drill-down is the feature: after "Not accurate", the control offers
// "Open the full reasoning trace" -> D3's /reasoning?query_id=… .
import { useState } from "react";
import Link from "next/link";
import { Flag, ThumbsDown, ThumbsUp, Workflow } from "lucide-react";
import { inputClass } from "./Field";
import { submitFeedback } from "../lib/watches";

type Kind = "helpful" | "not_accurate" | "report_issue";

export function FeedbackControl({ queryId, advisoryRef }: { queryId: string; advisoryRef?: string }) {
  const [sent, setSent] = useState<Kind | null>(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [traceRoute, setTraceRoute] = useState<string | null>(null);
  const [error, setError] = useState(false);

  async function send(kind: Kind, withComment?: string) {
    setError(false);
    try {
      const res = await submitFeedback({ query_id: queryId, kind, advisory_ref: advisoryRef, comment: withComment });
      setSent(kind);
      setTraceRoute(res.trace_route);
      if (kind === "report_issue") setShowComment(false);
    } catch {
      setError(true);
    }
  }

  const BTN =
    "inline-flex items-center gap-1.5 rounded-sm border border-hairline px-2.5 py-1.5 text-xs text-ink-muted transition-colors hover:border-hairline-strong hover:text-ink disabled:opacity-50";

  return (
    <div className="mt-3 border-t border-hairline pt-3">
      <p className="mb-2 text-[11px] font-medium text-ink-dim">Was this advisory useful?</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={BTN} onClick={() => send("helpful")} disabled={sent === "helpful"} aria-pressed={sent === "helpful"}>
          <ThumbsUp className="size-3.5" aria-hidden="true" /> Helpful
        </button>
        <button
          type="button"
          className={BTN}
          onClick={() => send("not_accurate")}
          disabled={sent === "not_accurate"}
          aria-pressed={sent === "not_accurate"}
        >
          <ThumbsDown className="size-3.5" aria-hidden="true" /> Not accurate
        </button>
        <button type="button" className={BTN} onClick={() => setShowComment((v) => !v)} aria-expanded={showComment}>
          <Flag className="size-3.5" aria-hidden="true" /> Report issue
        </button>
      </div>

      {showComment && (
        <form
          className="mt-2"
          onSubmit={(e) => {
            e.preventDefault();
            send("report_issue", comment.trim() || undefined);
          }}
        >
          <label htmlFor="fb-comment" className="mb-1 block text-[11px] text-ink-dim">
            What was wrong? (optional)
          </label>
          <textarea
            id="fb-comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
            className={inputClass}
          />
          <button type="submit" className={`${BTN} mt-2`}>
            Send report
          </button>
        </form>
      )}

      <p aria-live="polite" className="mt-2 text-[11px] text-ink-dim">
        {error && "Could not send your feedback — try again."}
        {!error && sent === "helpful" && "Thanks — logged."}
        {!error && sent === "report_issue" && "Report received — logged against this advisory."}
        {!error && sent === "not_accurate" && (
          <>
            Logged. {traceRoute && (
              <Link href={traceRoute} className="inline-flex items-center gap-1 text-accent underline">
                <Workflow className="size-3" aria-hidden="true" /> Open the full reasoning trace
              </Link>
            )}
          </>
        )}
      </p>
    </div>
  );
}
