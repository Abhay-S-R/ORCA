"use client";

import { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Clock,
  Gauge,
  Pause,
  Play,
  RotateCcw,
} from "lucide-react";

export type PipelineStage = {
  id: string;
  label: string;
  nodeIds: string[];
  depth: number;
};

export const PIPELINE_STAGES: PipelineStage[] = [
  { id: "distress", label: "01 Distress Check", nodeIds: ["distress", "distress_check"], depth: 0 },
  { id: "ingress", label: "02 Language Ingress", nodeIds: ["language_ingress"], depth: 1 },
  { id: "planning", label: "03 Planning & Intent", nodeIds: ["planning"], depth: 2 },
  {
    id: "specialists",
    label: "04 Parallel Specialists",
    nodeIds: ["weather_intelligence", "geospatial", "ocean_analytics"],
    depth: 3,
  },
  {
    id: "synthesis",
    label: "05 Synthesis & Assets",
    nodeIds: ["risk_assessment", "visualization"],
    depth: 4,
  },
  { id: "reporting", label: "06 Narrative Assembly", nodeIds: ["reporting"], depth: 5 },
  { id: "critic", label: "07 Critic Review", nodeIds: ["critic"], depth: 6 },
  { id: "egress", label: "08 Language Egress", nodeIds: ["language_egress"], depth: 7 },
];

interface ReasoningTimelineProps {
  currentStageIndex: number;
  maxStages: number;
  isPlaying: boolean;
  playbackSpeed: number;
  totalLatencyMs: number;
  activeStageLatencyMs: number;
  onSelectStage: (stageIndex: number) => void;
  onTogglePlay: () => void;
  onChangeSpeed: (speed: number) => void;
  onReset: () => void;
}

export function ReasoningTimeline({
  currentStageIndex,
  maxStages,
  isPlaying,
  playbackSpeed,
  totalLatencyMs,
  activeStageLatencyMs,
  onSelectStage,
  onTogglePlay,
  onChangeSpeed,
  onReset,
}: ReasoningTimelineProps) {
  const currentStage = PIPELINE_STAGES[Math.min(currentStageIndex, PIPELINE_STAGES.length - 1)];

  return (
    <div className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-3 rounded-2xl border border-hairline-strong/80 bg-shelf-1/90 px-4 py-2.5 shadow-2xl shadow-black/80 backdrop-blur-xl">
      {/* Playback Controls */}
      <div className="flex items-center gap-1 border-r border-hairline pr-3">
        <button
          type="button"
          onClick={() => onSelectStage(0)}
          disabled={currentStageIndex <= 0}
          className="rounded p-1 text-ink-dim hover:bg-shelf-2 hover:text-ink disabled:opacity-30"
          title="Jump to Start"
          aria-label="Jump to Start"
        >
          <ChevronsLeft className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => onSelectStage(Math.max(0, currentStageIndex - 1))}
          disabled={currentStageIndex <= 0}
          className="rounded p-1 text-ink-dim hover:bg-shelf-2 hover:text-ink disabled:opacity-30"
          title="Previous Stage"
          aria-label="Previous Stage"
        >
          <ChevronLeft className="size-4" />
        </button>
        <button
          type="button"
          onClick={onTogglePlay}
          className={`grid size-8 place-items-center rounded-lg border transition-all ${
            isPlaying
              ? "border-caution/40 bg-caution/15 text-caution shadow-md shadow-caution/20"
              : "border-sky-400/50 bg-sky-950/40 text-sky-300 shadow-md shadow-sky-950/50 hover:border-sky-400"
          }`}
          title={isPlaying ? "Pause playback" : "Play step-by-step trace"}
          aria-label={isPlaying ? "Pause playback" : "Play step-by-step trace"}
        >
          {isPlaying ? <Pause className="size-4" /> : <Play className="size-4 ml-0.5" />}
        </button>
        <button
          type="button"
          onClick={() => onSelectStage(Math.min(maxStages - 1, currentStageIndex + 1))}
          disabled={currentStageIndex >= maxStages - 1}
          className="rounded p-1 text-ink-dim hover:bg-shelf-2 hover:text-ink disabled:opacity-30"
          title="Next Stage"
          aria-label="Next Stage"
        >
          <ChevronRight className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => onSelectStage(maxStages - 1)}
          disabled={currentStageIndex >= maxStages - 1}
          className="rounded p-1 text-ink-dim hover:bg-shelf-2 hover:text-ink disabled:opacity-30"
          title="Jump to End"
          aria-label="Jump to End"
        >
          <ChevronsRight className="size-4" />
        </button>
      </div>

      {/* Stage Dots / Progress Scrubber */}
      <div className="flex flex-col gap-1.5 min-w-[260px]">
        <div className="flex items-center justify-between text-[11px]">
          <span className="font-semibold text-ink">
            {currentStage?.label ?? "All Stages Complete"}
          </span>
          <span className="font-mono text-[10px] text-ink-dim">
            Step {currentStageIndex + 1} of {maxStages}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {Array.from({ length: maxStages }).map((_, idx) => {
            const isCompleted = idx < currentStageIndex;
            const isCurrent = idx === currentStageIndex;
            return (
              <button
                key={idx}
                type="button"
                onClick={() => onSelectStage(idx)}
                className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${
                  isCurrent
                    ? "bg-ocean-cyan shadow-sm shadow-sky-400 ring-1 ring-sky-400/50"
                    : isCompleted
                    ? "bg-sky-800"
                    : "bg-shelf-2"
                }`}
                title={`Jump to step ${idx + 1}`}
                aria-label={`Jump to step ${idx + 1}`}
              />
            );
          })}
        </div>
      </div>

      {/* Telemetry / Speed / Reset */}
      <div className="flex items-center gap-2 border-l border-hairline pl-3">
        <div className="flex items-center gap-1 font-mono text-[11px] text-ink-dim" title="Cumulative Execution Latency">
          <Clock className="size-3 text-sky-400" />
          <span className="text-ink">{activeStageLatencyMs || totalLatencyMs}ms</span>
        </div>

        {/* Speed toggle */}
        <button
          type="button"
          onClick={() => onChangeSpeed(playbackSpeed === 1 ? 2 : playbackSpeed === 2 ? 0.5 : 1)}
          className="rounded-md border border-hairline bg-shelf-2/60 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ink-dim hover:text-ink"
          title="Toggle playback speed"
        >
          {playbackSpeed}x
        </button>

        <button
          type="button"
          onClick={onReset}
          className="rounded p-1 text-ink-dim hover:bg-shelf-2 hover:text-ink"
          title="Reset trace to step 1"
          aria-label="Reset trace"
        >
          <RotateCcw className="size-3.5" />
        </button>
      </div>
    </div>
  );
}
