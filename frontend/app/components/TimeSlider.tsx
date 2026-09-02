"use client";

// Forecast frame scrubber (§4.8). It swaps frames already fetched — it never
// re-runs the agent graph, so it is a plain range input over an index, not a
// query trigger. Keeping it dumb is the design.
import { Pause, Play } from "lucide-react";
import { useEffect } from "react";

export function TimeSlider({
  frames,
  index,
  onIndexChange,
  playing = false,
  onPlayingChange,
}: {
  frames: { t: string }[];
  index: number;
  onIndexChange: (next: number) => void;
  playing?: boolean;
  onPlayingChange?: (next: boolean) => void;
}) {
  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const id = setInterval(() => onIndexChange((index + 1) % frames.length), 900);
    return () => clearInterval(id);
  }, [playing, index, frames.length, onIndexChange]);

  if (frames.length === 0) return null;
  const current = frames[Math.min(index, frames.length - 1)];

  return (
    <div className="glass flex items-center gap-3 rounded-md px-3 py-2">
      {onPlayingChange && (
        <button
          type="button"
          onClick={() => onPlayingChange(!playing)}
          aria-label={playing ? "Pause forecast animation" : "Play forecast animation"}
          className="rounded-sm p-1 text-ink-muted transition-colors hover:bg-shelf-2 hover:text-ink"
        >
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </button>
      )}
      <input
        type="range"
        min={0}
        max={frames.length - 1}
        step={1}
        value={index}
        onChange={(e) => onIndexChange(Number(e.target.value))}
        aria-label="Forecast time"
        aria-valuetext={formatFrame(current.t)}
        className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-hairline accent-[var(--color-accent)]"
      />
      {/* The time is stated in text, always. The slider position alone is
          never the answer to "when is this?" (§4.11). */}
      <time dateTime={current.t} data-readout className="shrink-0 text-xs text-ink">
        {formatFrame(current.t)}
      </time>
    </div>
  );
}

function formatFrame(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });
}
