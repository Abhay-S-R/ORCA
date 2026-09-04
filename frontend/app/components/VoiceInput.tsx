"use client";

// Voice ingress (plan §6 D1 Day 17): push-to-talk -> POST /voice/transcribe
// -> the transcript renders as EDITABLE text and requires an explicit "Ask"
// before it becomes a query — never auto-submitted, because a mishearing on
// a safety query is a safety incident, not a UX annoyance (plan §6 D1 Day 16).
// Full keyboard operation: space starts/stops recording, escape cancels.
//
// Split in two so the mic sits beside the Ask button while the waveform/
// confirm UI renders below the form — both views share one `useVoiceInput`
// state so there's still exactly one recording pipeline.
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Mic, Square, X } from "lucide-react";
import { Button } from "./Button";
import { API_BASE } from "../lib/apiBase";

type VoiceState = "idle" | "recording" | "transcribing" | "confirming" | "error";

export function useVoiceInput({ onTranscriptConfirmed }: { onTranscriptConfirmed: (text: string) => void }) {
  const [state, setState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState("");
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [level, setLevel] = useState(0); // 0-1 live amplitude, drives the waveform bars
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

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
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        releaseStream();
        stopWaveform();
        setLevel(0);
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        setState("transcribing");
        try {
          const form = new FormData();
          form.append("audio", blob, "query.webm");
          const res = await fetch(`${API_BASE}/voice/transcribe`, { method: "POST", body: form });
          if (!res.ok) throw new Error(`transcribe failed: ${res.status}`);
          const data = await res.json();
          if (!data.transcript) {
            setState("error");
            setError("Could not hear you — try again.");
            return;
          }
          setTranscript(data.transcript);
          setNeedsConfirmation(Boolean(data.needs_confirmation));
          setState("confirming");
        } catch {
          setState("error");
          setError("Could not reach the voice service — try again.");
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setState("recording");

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
  }, [releaseStream, stopWaveform]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
  }, []);

  const cancel = useCallback(() => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
    }
    releaseStream();
    stopWaveform();
    setLevel(0);
    setState("idle");
    setTranscript("");
    setError(null);
  }, [releaseStream, stopWaveform]);

  useEffect(() => () => {
    stopWaveform();
    releaseStream();
  }, [stopWaveform, releaseStream]);

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

// The mic button alone — sits beside the Ask button. The fisherman persona
// gets the largest touch target (plan §6 D1 Day 17: "the largest touch
// target on the fisherman surface") — every other persona gets the same
// control at the design system's normal button size.
export function VoiceMicButton({ voice, isFisherman = false }: { voice: VoiceInputState; isFisherman?: boolean }) {
  const { state, startRecording, stopRecording } = voice;
  return (
    <Button
      type="button"
      variant={state === "recording" ? "primary" : "ghost"}
      aria-label={state === "recording" ? "Stop recording" : "Ask by voice — space bar also works"}
      icon={state === "recording" ? <Square className="size-4" /> : <Mic className={isFisherman ? "size-6" : "size-4"} />}
      className={isFisherman ? "px-5 py-4" : "px-3"}
      onClick={state === "recording" ? stopRecording : startRecording}
      disabled={state === "transcribing"}
    >
      <span className="sr-only">{state === "recording" ? "Stop recording" : "Ask by voice"}</span>
    </Button>
  );
}

// Waveform / transcribing / confirm-transcript UI — renders below the form
// while VoiceMicButton stays up beside Ask.
export function VoiceInputPanel({ voice }: { voice: VoiceInputState }) {
  const { state, transcript, setTranscript, needsConfirmation, level, error, confirm, cancel } = voice;

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

      {state === "transcribing" && <span className="text-xs text-ink-muted">Transcribing…</span>}

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
            className="w-full resize-none rounded border border-hairline bg-shelf-0/60 px-2 py-1.5 text-sm text-ink"
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
