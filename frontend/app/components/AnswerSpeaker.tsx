"use client";

// Voice egress (plan §6 D1 Day 17): TTS playback of the verdict via
// POST /voice/speak. Manual only — every persona, including fisherman,
// gets the same "Play verdict" button. Never autoplays; playback starts
// and stops only on explicit user action.
//
// Performance: on mount, fires a /voice/prefetch to warm the backend's
// TTS cache in the background. By the time the user reads the answer
// and clicks Play, the audio is already synthesized and cached — the
// /voice/speak call then returns a cache hit in <50ms instead of 5-15s.
import { useEffect, useRef, useState } from "react";
import { Volume2, Square } from "lucide-react";
import { Button } from "./Button";
import { type Persona } from "../persona/config";
import { API_BASE } from "../lib/apiBase";

export function AnswerSpeaker({
  text,
  language,
  persona,
  queryId,
}: {
  text: string;
  language: string;
  persona: Persona;
  queryId: string | undefined;
}) {
  const [playing, setPlaying] = useState(false);
  const [rung, setRung] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // Client-side cache: once we have the audio blob, don't fetch again.
  const cachedBlobRef = useRef<{ text: string; blob: Blob; rung: string } | null>(null);

  // Fire-and-forget prefetch as soon as the answer text is known —
  // this warms the backend's TTS cache so /voice/speak is instant later.
  useEffect(() => {
    if (!text.trim()) return;
    // Don't prefetch if we already have this text cached client-side
    if (cachedBlobRef.current?.text === text) return;
    const controller = new AbortController();
    fetch(`${API_BASE}/voice/prefetch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language }),
      signal: controller.signal,
    }).catch(() => {/* prefetch is best-effort, ignore failures */});
    return () => controller.abort();
  }, [text, language]);

  function stop() {
    audioRef.current?.pause();
    setPlaying(false);
  }

  async function speak() {
    if (!text.trim()) return;
    setPlaying(true);
    setError(null);
    try {
      let blob: Blob;
      let ttsRung: string;

      // Use client-side cached blob if available for this exact text
      if (cachedBlobRef.current?.text === text) {
        blob = cachedBlobRef.current.blob;
        ttsRung = cachedBlobRef.current.rung;
      } else {
        const res = await fetch(`${API_BASE}/voice/speak`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, language }),
        });
        if (!res.ok) {
          setPlaying(false);
          setError("Voice playback is unavailable right now — the text answer above is unchanged.");
          return;
        }
        ttsRung = res.headers.get("x-tts-rung") || "";
        blob = await res.blob();
        // Cache for subsequent clicks
        cachedBlobRef.current = { text, blob, rung: ttsRung };
      }

      setRung(ttsRung);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setPlaying(false);
      audio.onerror = () => setPlaying(false);
      await audio.play();
    } catch {
      setPlaying(false);
      setError("Voice playback is unavailable right now — the text answer above is unchanged.");
    }
  }

  // Stop and release any in-flight audio when the answer being narrated
  // changes or the component unmounts — never let a stale clip keep
  // playing over a new one.
  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, [queryId, persona]);

  // P4.5 (R-NEW-6) — "full voice operability without reading": the mic
  // button (P4.4) is already the loudest control on this persona's screen;
  // hearing the answer back needs the same treatment, an icon a fisherman
  // recognizes on sight rather than a label they have to read first.
  if (persona === "fisherman") {
    return (
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          onClick={playing ? stop : speak}
          aria-label={playing ? "Stop playing the answer" : "Play the answer aloud"}
          className="inline-flex h-[52px] w-[52px] shrink-0 cursor-pointer items-center justify-center rounded-full border-2 border-ocean-cyan bg-ocean-cyan text-on-accent shadow-md transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {playing ? <Square className="size-6" aria-hidden="true" /> : <Volume2 className="size-6" aria-hidden="true" />}
        </button>
        {error && <span className="text-sm text-no-go">{error}</span>}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Button
        type="button"
        variant="ghost"
        className="text-xs"
        icon={<Volume2 className="size-3.5" />}
        onClick={speak}
        disabled={playing}
      >
        {playing ? "Playing…" : "Play verdict"}
      </Button>
      {playing && (
        <Button type="button" variant="ghost" className="text-xs" icon={<Square className="size-3.5" />} onClick={stop}>
          Stop
        </Button>
      )}
      {rung && <span className="text-[11px] text-ink-dim">via {rung === "mms_tts" ? "MMS-TTS (local)" : rung}</span>}
      {error && <span className="text-[11px] text-no-go">{error}</span>}
    </div>
  );
}

