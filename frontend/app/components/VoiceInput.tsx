"use client";

// Voice ingress (plan §6 D1 Day 17): push-to-talk -> POST /voice/transcribe
// -> the transcript renders as EDITABLE text and requires an explicit "Ask"
// before it becomes a query — never auto-submitted, because a mishearing on
// a safety query is a safety incident, not a UX annoyance (plan §6 D1 Day 16).
// Full keyboard operation: space starts/stops recording, escape cancels.
//
// While recording, the audio so far is re-sent every ~1.5 s as a `partial`
// (Bhashini only, ~1 s round trip) so the words appear in the speaker's own
// script as they talk; stop sends the whole clip once more, cleaned (VAD,
// denoiser, punctuation), and that final text is what gets confirmed. There
// is no spoken-language picker: the final pass lets Bhashini's audio language
// detection name the language (someone reading the UI in English may still
// speak Kannada), falling back to the navbar language when it is unsure. Live
// captions go through the same detection, so they are in the spoken script too.
//
// Split in two so the mic sits beside the Ask button while the waveform/
// confirm UI renders below the form — both views share one `useVoiceInput`
// state so there's still exactly one recording pipeline.
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Mic, Square, X } from "lucide-react";
import { Button } from "./Button";
import { API_BASE } from "../lib/apiBase";
import { fontClassForLanguage } from "../i18n/languages";

type VoiceState = "idle" | "recording" | "transcribing" | "confirming" | "error";

const PARTIAL_INTERVAL_MS = 1500;

async function postTranscribe(blob: Blob, language: string, partial: boolean) {
  const form = new FormData();
  form.append("audio", blob, "query.webm");
  form.append("language_hint", language);
  if (partial) form.append("partial", "true");
  const res = await fetch(`${API_BASE}/voice/transcribe`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`transcribe failed: ${res.status}`);
  return res.json();
}

export function useVoiceInput({ onTranscriptConfirmed, languageHint }: { onTranscriptConfirmed: (text: string) => void; languageHint?: string }) {
  const [state, setState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState("");
  const [liveTranscript, setLiveTranscript] = useState("");
  // The hint sent with every clip is the navbar language; what Bhashini
  // heard only picks the script font for the caption and transcript.
  const uiLanguage = languageHint ?? "en";
  const [heardLanguage, setHeardLanguage] = useState<string | null>(null);
  const spokenLanguage = heardLanguage ?? uiLanguage;
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [level, setLevel] = useState(0); // 0-1 live amplitude, drives the waveform bars
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const partialTimerRef = useRef<number | null>(null);
  // Bumped on every start/stop/cancel so a partial still in flight from an
  // earlier recording can't overwrite the caption of the current one.
  const sessionRef = useRef(0);

  const stopPartials = useCallback(() => {
    if (partialTimerRef.current) window.clearInterval(partialTimerRef.current);
    partialTimerRef.current = null;
    sessionRef.current += 1;
  }, []);

  const stopWaveform = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
  }, []);

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setState("error");
      setError("This browser does not support microphone capture.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      setLiveTranscript("");
      setHeardLanguage(null);
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stopPartials();
        releaseStream();
        stopWaveform();
        setLevel(0);
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        setState("transcribing");
        try {
          const data = await postTranscribe(blob, uiLanguage, false);
          if (!data.transcript) {
            setState("error");
            setError("Could not hear you — try again.");
            return;
          }
          setTranscript(data.transcript);
          setHeardLanguage(data.detected_language ?? null);
          setNeedsConfirmation(Boolean(data.needs_confirmation));
          setState("confirming");
        } catch {
          setState("error");
          setError("Could not reach the voice service — try again.");
        }
      };
      mediaRecorderRef.current = recorder;
      // Timesliced so chunks accumulate while recording; every prefix of
      // them is a decodable WebM (the header is in the first chunk), which
      // is what lets a partial be "everything said so far".
      recorder.start(250);
      setState("recording");

      const session = ++sessionRef.current;
      let inFlight = false;
      let sentChunks = 0;
      partialTimerRef.current = window.setInterval(async () => {
        if (inFlight || chunksRef.current.length === sentChunks) return;
        inFlight = true;
        sentChunks = chunksRef.current.length;
        try {
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
          const data = await postTranscribe(blob, uiLanguage, true);
          if (session === sessionRef.current && data.transcript) {
            setLiveTranscript(data.transcript);
            setHeardLanguage(data.detected_language ?? null);
          }
        } catch {
          /* a dropped caption is fine — the final pass on stop is what counts */
        } finally {
          inFlight = false;
        }
      }, PARTIAL_INTERVAL_MS);

      // Web Audio live waveform — a single time-domain amplitude read per
      // frame is enough to show "it is listening"; this never claims to be
      // a spectrum analyzer.
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += Math.abs(data[i] - 128);
        setLevel(Math.min(1, (sum / data.length / 128) * 4));
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      setState("error");
      setError("Microphone access was denied or is unavailable.");
    }
  }, [releaseStream, stopWaveform, stopPartials, uiLanguage]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
  }, []);

  const cancel = useCallback(() => {
    stopPartials();
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
    }
    releaseStream();
    stopWaveform();
    setLevel(0);
    setState("idle");
    setTranscript("");
    setLiveTranscript("");
    setError(null);
  }, [releaseStream, stopWaveform, stopPartials]);

  useEffect(() => () => {
    stopPartials();
    stopWaveform();
    releaseStream();
  }, [stopWaveform, releaseStream, stopPartials]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      if (e.code === "Space" && state === "idle") {
        e.preventDefault();
        startRecording();
      } else if (e.code === "Space" && state === "recording") {
        e.preventDefault();
        stopRecording();
      } else if (e.code === "Escape" && (state === "recording" || state === "confirming")) {
        e.preventDefault();
        cancel();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, startRecording, stopRecording, cancel]);

  function confirm() {
    const text = transcript.trim();
    if (!text) return;
    onTranscriptConfirmed(text);
    setState("idle");
    setTranscript("");
  }

  return {
    state,
    transcript,
    setTranscript,
    liveTranscript,
    spokenLanguage,
    needsConfirmation,
    level,
    error,
    startRecording,
    stopRecording,
    cancel,
    confirm,
  };
}

export type VoiceInputState = ReturnType<typeof useVoiceInput>;

// The mic button alone — sits beside the Ask button. P4.4: on the fisherman
// surface the mic IS the primary control, not a smaller secondary one next
// to the "real" Ask button — noticeably larger, filled even at rest rather
// than only while recording, so it reads as the thing to press first. Every
// other persona gets the design system's normal-size, outline-until-active
// control.
export function VoiceMicButton({
  voice,
  isFisherman = false,
  quiet = false,
}: {
  voice: VoiceInputState;
  isFisherman?: boolean;
  // inside the composer pill: a round ghost icon like ChatGPT's, filled only while it is recording
  quiet?: boolean;
}) {
  const { state, startRecording, stopRecording } = voice;
  const isRecording = state === "recording";
  const size = isFisherman ? "h-[52px] w-[52px]" : "h-[38px] w-[38px]";
  const iconSize = isFisherman ? "size-5" : "size-3.5";
  if (quiet) {
    return (
      <button
        type="button"
        aria-label={isRecording ? "Stop recording" : "Ask by voice — space bar also works"}
        title={isRecording ? "Stop recording" : "Ask by voice"}
        onClick={isRecording ? stopRecording : startRecording}
        disabled={state === "transcribing"}
        className={`grid size-10 shrink-0 cursor-pointer place-items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          isRecording ? "bg-ocean-cyan text-on-accent hover:bg-ocean-cyan/90" : "text-ink-dim hover:bg-shelf-2 hover:text-ink"
        }`}
      >
        {isRecording ? <Square className="size-[18px]" /> : <Mic className="size-[18px]" />}
        <span className="sr-only">{isRecording ? "Stop recording" : "Ask by voice"}</span>
      </button>
    );
  }
  return (
    <button
      type="button"
      aria-label={isRecording ? "Stop recording" : "Ask by voice — space bar also works"}
      onClick={isRecording ? stopRecording : startRecording}
      disabled={state === "transcribing"}
      className={`inline-flex ${size} shrink-0 cursor-pointer items-center justify-center rounded-full border-2 font-semibold transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${
        isRecording
          ? "border-ocean-cyan/50 bg-ocean-cyan text-on-accent shadow-sm hover:bg-ocean-cyan/90"
          : isFisherman
            ? "border-ocean-cyan bg-ocean-cyan text-on-accent shadow-md hover:bg-ocean-cyan/90"
            : "rounded-lg border-hairline bg-shelf-2/70 text-ink-muted hover:border-ocean-cyan/50 hover:bg-shelf-3/80 hover:text-ink"
      }`}
    >
      {isRecording ? <Square className={iconSize} /> : <Mic className={iconSize} />}
      <span className="sr-only">{isRecording ? "Stop recording" : "Ask by voice"}</span>
    </button>
  );
}

// Waveform / transcribing / confirm-transcript UI — renders below the form
// while VoiceMicButton stays up beside Ask.
export function VoiceInputPanel({ voice }: { voice: VoiceInputState }) {
  const { state, transcript, setTranscript, liveTranscript, spokenLanguage, needsConfirmation, level, error, confirm, cancel } = voice;
  const scriptFont = fontClassForLanguage(spokenLanguage);

  if (state === "idle") return null;

  return (
    <div className="flex flex-col gap-2">
      {state === "recording" && (
        <div className="flex h-8 items-end gap-0.5 rounded-md border border-hairline bg-shelf-1/60 px-2.5" role="img" aria-label="Listening">
          {Array.from({ length: 32 }).map((_, i) => (
            <span
              key={i}
              className="w-1 flex-1 rounded-full bg-accent"
              style={{ height: `${6 + level * 26 * (0.4 + 0.6 * Math.abs(Math.sin(i * 0.9)))}px` }}
            />
          ))}
        </div>
      )}

      {(state === "recording" || state === "transcribing") && (
        <p aria-live="polite" className={`min-h-[1.25rem] text-sm text-ink ${scriptFont}`}>
          {liveTranscript || <span className="text-ink-dim">{state === "recording" ? "Listening…" : ""}</span>}
        </p>
      )}

      {state === "transcribing" && <span className="text-xs text-ink-muted">Finalizing…</span>}

      {state === "confirming" && (
        <div className="rounded-md border border-hairline bg-shelf-1/60 p-2.5">
          <label htmlFor="voice-transcript" className="mb-1 block text-[11px] font-medium text-ink-dim">
            {needsConfirmation ? "Low confidence — check this before asking:" : "Heard:"}
          </label>
          <textarea
            id="voice-transcript"
            aria-live="polite"
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            rows={2}
            className={`w-full resize-none rounded border border-hairline bg-shelf-1/60 px-2 py-1.5 text-sm text-ink ${scriptFont}`}
          />
          <div className="mt-2 flex gap-2">
            <Button type="button" variant="primary" className="text-xs" icon={<Check className="size-3.5" />} onClick={confirm}>
              Ask
            </Button>
            <Button type="button" variant="ghost" className="text-xs" icon={<X className="size-3.5" />} onClick={cancel}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-xs text-no-go">
          {error}
        </p>
      )}
    </div>
  );
}
