"use client";

// Voice egress (plan §6 D1 Day 17): TTS playback of the answer via
// POST /voice/speak. Manual only — every persona, including fisherman,
// gets the same speaker icon, in the action row under every response. Never autoplays; playback starts
// and stops only on explicit user action.
//
// Performance: on mount, fires a /voice/prefetch to warm the backend's
// TTS cache in the background. By the time the user reads the answer
// and clicks Play, the audio is already synthesized and cached — the
// /voice/speak call then returns a cache hit in <50ms instead of 5-15s.
import { useEffect, useRef, useState } from "react";
import { Volume2, Square } from "lucide-react";
import { type Persona } from "../persona/config";
import { API_BASE } from "../lib/apiBase";
import { ghostBtn } from "../ask/RerunControl";

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

  // Same quiet ghost icon as copy and try again, in the row under the answer (since 2026-10-08;
  // it was a round blue 52 px button). An icon recognised on sight rather than a label to read
  // (P4.5, R-NEW-6): the same tap plays, the same tap stops, and while it plays it is tinted.
  return (
    <>
      <button
        type="button"
        onClick={playing ? stop : speak}
        aria-label={playing ? "Stop playing the answer" : "Play the answer aloud"}
        title={playing ? "Stop" : "Play the answer aloud"}
        className={`${ghostBtn} ${playing ? "text-ocean-cyan" : ""}`}
      >
        {playing ? <Square className="size-[18px]" aria-hidden="true" /> : <Volume2 className="size-[18px]" aria-hidden="true" />}
      </button>
      {error && <span className="text-[11px] text-no-go">{error}</span>}
    </>
  );
}
