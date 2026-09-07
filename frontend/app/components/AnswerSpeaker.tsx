"use client";

// Voice egress (plan §6 D1 Day 17): TTS playback of the verdict via
// POST /voice/speak. Manual only — every persona, including fisherman,
// gets the same "Play verdict" button. Never autoplays; playback starts
// and stops only on explicit user action.
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

  function stop() {
    audioRef.current?.pause();
    setPlaying(false);
  }

  async function speak() {
    if (!text.trim()) return;
    setPlaying(true);
    setError(null);
    try {
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
      setRung(res.headers.get("x-tts-rung"));
      const blob = await res.blob();
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
