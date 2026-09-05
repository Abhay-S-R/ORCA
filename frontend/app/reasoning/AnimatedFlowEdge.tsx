"use client";

import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";
import { AlertTriangle } from "lucide-react";

export type FlowEdgeData = {
  kind?: "handoff" | "critic_loop" | "cancelled";
  isActive?: boolean;
  isCompleted?: boolean;
  label?: string;
};

export function AnimatedFlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const edgeData = (data as FlowEdgeData | undefined) ?? {};
  const isCriticLoop = edgeData.kind === "critic_loop";
  const isCancelled = edgeData.kind === "cancelled";
  const isActive = edgeData.isActive;
  const isCompleted = edgeData.isCompleted;

  // Use smoothstep with generous borderRadius for smooth pipeline curves
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 16,
  });

  // Base stroke styling
  let strokeColor = "#17384c"; // hairline
  let strokeWidth = 1.5;
  let strokeDasharray: string | undefined = undefined;

  if (isCriticLoop) {
    strokeColor = "#f0468c"; // chart magenta / critic loop
    strokeWidth = 2;
    strokeDasharray = "4 4";
  } else if (isCancelled) {
    strokeColor = "#24576f";
    strokeDasharray = "3 3";
  } else if (isActive) {
    strokeColor = "#38bdf8"; // cyan active
    strokeWidth = 2.5;
  } else if (isCompleted) {
    strokeColor = "#24576f"; // hairline-strong
    strokeWidth = 2;
  }

  return (
    <>
      {/* Background shadow/glow line */}
      {isActive && (
        <path
          d={edgePath}
          fill="none"
          stroke="#38bdf8"
          strokeWidth={6}
          strokeOpacity={0.25}
          className="blur-[2px]"
        />
      )}

      {/* Main edge path */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth,
          strokeDasharray,
          transition: "stroke 0.3s ease, stroke-width 0.3s ease",
        }}
      />

      {/* Travelling glowing particle when edge is active */}
      {isActive && (
        <circle r="3.5" fill="#38bdf8" className="shadow-lg shadow-sky-400">
          <animateMotion
            path={edgePath}
            dur="1.2s"
            repeatCount="indefinite"
            rotate="auto"
          />
        </circle>
      )}

      {/* Critic loop pulsing particle in reverse */}
      {isCriticLoop && (
        <circle r="3" fill="#f0468c">
          <animateMotion
            path={edgePath}
            dur="1.8s"
            repeatCount="indefinite"
            keyPoints="1;0"
            keyTimes="0;1"
            rotate="auto"
          />
        </circle>
      )}

      {/* Optional edge label for critic loop feedback or stage name */}
      {edgeData.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
            className="nodrag nopan"
          >
            {isCriticLoop ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-abyss/90 px-2 py-0.5 text-[10px] font-medium text-accent shadow-md backdrop-blur-sm">
                <AlertTriangle className="size-2.5 shrink-0" />
                {edgeData.label}
              </span>
            ) : (
              <span className="rounded bg-shelf-1/80 px-1.5 py-0.5 text-[9px] font-medium text-ink-dim border border-hairline backdrop-blur-sm">
                {edgeData.label}
              </span>
            )}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
