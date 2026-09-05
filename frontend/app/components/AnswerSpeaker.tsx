"use client";

// Voice egress (plan §6 D1 Day 17): TTS playback of the verdict via
// POST /voice/speak. Auto-plays for the fisherman persona only — every
// other persona gets the same control as a manual "Play verdict" button,
// never an autoplay.
import { useEffect, useRef, useState } from "react";
import { Volume2 } from "lucide-react";
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
  const autoplayedFor = useRef<string | undefined>(undefined);

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
      audio.onended = () => setPlaying(false);
      audio.onerror = () => setPlaying(false);
      await audio.play();
    } catch {
      setPlaying(false);
      setError("Voice playback is unavailable right now — the text answer above is unchanged.");
    }
  }

  // Once per answer (queryId), fisherman persona only — never re-triggers on
  // a persona-correction re-render that keeps the same query_id, and never
  // fires for the other three personas.
  useEffect(() => {
    if (persona === "fisherman" && queryId && autoplayedFor.current !== queryId) {
      autoplayedFor.current = queryId;
      speak();
    }
    return () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona, queryId]);

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
      {rung && <span className="text-[11px] text-ink-dim">via {rung === "mms_tts" ? "MMS-TTS (local)" : rung}</span>}
      {error && <span className="text-[11px] text-no-go">{error}</span>}
    </div>
  );
}
