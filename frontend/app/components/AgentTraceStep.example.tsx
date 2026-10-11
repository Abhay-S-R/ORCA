// Example usage of AgentTraceStep component
// This file demonstrates how to use the AgentTraceStep component
// in various scenarios within the Agent Trace UI.

import React from "react";
import { AgentTraceStep } from "./AgentTraceStep";
import type { TraceNode } from "../reasoning/fixture";

// Example 1: Basic completed agent step
export function BasicExample() {
  const basicNode: TraceNode = {
    id: "planning",
    agent_name: "Planning",
    depth: 2,
    status: "ok",
    confidence_tier: "HIGH",
    latency_ms: 610,
    reasoning_summary: "Matched SAFETY_CHECK on the keyword rules",
    source_count: 0,
    used_llm: false,
    model: null,
    tier: null,
    engine: "Deterministic",
    run_count: 1,
  };

  return (
    <ol className="flex flex-col gap-1">
      <AgentTraceStep node={basicNode} />
    </ol>
  );
}

// Example 2: Degraded agent with confidence badge
export function DegradedExample() {
  const degradedNode: TraceNode = {
    id: "ocean_analytics",
    agent_name: "Ocean Analytics",
    depth: 4,
    status: "degraded",
    confidence_tier: "MEDIUM",
    latency_ms: 260,
    reasoning_summary: "Falling tide, nearest PFZ 4.2 km. SOI table gap forced a Stormglass fallback.",
    source_count: 2,
    used_llm: false,
    model: null,
    tier: null,
    engine: "Deterministic",
    run_count: 1,
  };

  return (
    <ol className="flex flex-col gap-1">
      <AgentTraceStep node={degradedNode} />
    </ol>
  );
}

// Example 3: Failed agent
export function FailedExample() {
  const failedNode: TraceNode = {
    id: "weather_intelligence",
    agent_name: "Weather Intelligence",
    depth: 4,
    status: "failed",
    confidence_tier: "LOW_DATA",
    latency_ms: 120,
    reasoning_summary: "Failed to fetch weather data from API",
    source_count: 0,
    used_llm: false,
    model: null,
    tier: null,
    engine: "WeatherAPI",
    run_count: 1,
  };

  return (
    <ol className="flex flex-col gap-1">
      <AgentTraceStep node={failedNode} />
    </ol>
  );
}

// Example 4: Skipped agent with skip reason
export function SkippedExample() {
  const skippedNode: TraceNode = {
    id: "geospatial",
    agent_name: "Geospatial",
    depth: 4,
    status: "skipped",
    confidence_tier: "LOW_DATA",
    latency_ms: 0,
    reasoning_summary: "",
    source_count: 0,
    used_llm: false,
    model: null,
    tier: null,
    skip_reason: "No location provided in query",
    run_count: 1,
  };

  return (
    <ol className="flex flex-col gap-1">
      <AgentTraceStep node={skippedNode} />
    </ol>
  );
}

// Example 5: Running agent
export function RunningExample() {
  const runningNode: TraceNode = {
    id: "reporting",
    agent_name: "Reporting",
    depth: 6,
    status: "ok", // Will be overridden by isRunning prop
    confidence_tier: "HIGH",
    latency_ms: 0, // No latency yet
    reasoning_summary: "",
    source_count: 0,
    used_llm: true,
    model: null,
    tier: null,
    run_count: 1,
  };

  return (
    <ol className="flex flex-col gap-1">
      <AgentTraceStep node={runningNode} isRunning={true} />
    </ol>
  );
}

// Example 6: Parallel execution group
export function ParallelGroupExample() {
  const nodes: TraceNode[] = [
    {
      id: "weather_intelligence",
      agent_name: "Weather Intelligence",
      depth: 4,
      status: "ok",
      confidence_tier: "HIGH",
      latency_ms: 480,
      reasoning_summary: "Hs 2.4 m vs small_fishing class band 2.0 m → exceeded",
      source_count: 2,
      used_llm: false,
      model: null,
      tier: null,
      engine: "Deterministic",
      run_count: 1,
    },
    {
      id: "geospatial",
      agent_name: "Geospatial",
      depth: 4,
      status: "ok",
      confidence_tier: "HIGH",
      latency_ms: 190,
      reasoning_summary: "0.8 nm from the Sri Lanka EEZ (IMBL proxy)",
      source_count: 3,
      used_llm: false,
      model: null,
      tier: null,
      engine: "Deterministic",
      run_count: 1,
    },
    {
      id: "ocean_analytics",
      agent_name: "Ocean Analytics",
      depth: 4,
      status: "ok",
      confidence_tier: "MEDIUM",
      latency_ms: 260,
      reasoning_summary: "Falling tide, nearest PFZ 4.2 km",
      source_count: 2,
      used_llm: false,
      model: null,
      tier: null,
      engine: "Deterministic",
      run_count: 1,
    },
  ];

  return (
    <ol className="flex flex-col gap-1">
      {/* First agent in group shows the group label */}
      <AgentTraceStep
        node={nodes[0]}
        indent={1}
        showGroupLabel="Parallel execution (3 agents):"
      />
      {/* Other agents in the group */}
      <AgentTraceStep node={nodes[1]} indent={1} />
      <AgentTraceStep node={nodes[2]} indent={1} />
    </ol>
  );
}

// Example 7: Multi-run agent (critic loop)
export function MultiRunExample() {
  const multiRunNode: TraceNode = {
    id: "reporting",
    agent_name: "Reporting",
    depth: 6,
    status: "ok",
    confidence_tier: "HIGH",
    latency_ms: 1440, // Cumulative time for 2 runs
    reasoning_summary: "Assembled the English narrative, citing 4 sources",
    source_count: 4,
    used_llm: true,
    model: "gemini-3.5-flash-lite",
    tier: "mid",
    engine: "Gemini",
    run_count: 2, // Ran twice due to critic loop
  };

  return (
    <ol className="flex flex-col gap-1">
      <AgentTraceStep node={multiRunNode} />
    </ol>
  );
}

// Example 8: Critic loop re-invocation (indented)
export function CriticLoopExample() {
  const reportingNode: TraceNode = {
    id: "reporting",
    agent_name: "Reporting",
    depth: 6,
    status: "ok",
    confidence_tier: "HIGH",
    latency_ms: 720,
    reasoning_summary: "Assembled the English narrative",
    source_count: 4,
    used_llm: true,
    model: "gemini-3.5-flash-lite",
    tier: "mid",
    engine: "Gemini",
    run_count: 2,
  };

  const criticNode: TraceNode = {
    id: "critic",
    agent_name: "Critic",
    depth: 7,
    status: "ok",
    confidence_tier: "HIGH",
    latency_ms: 1400,
    reasoning_summary: "Found issues with the narrative, requesting revision",
    source_count: 0,
    used_llm: true,
    model: "gemini-3.5-flash-lite",
    tier: "reasoning",
    engine: "Gemini",
    run_count: 1,
  };

  const reportingReinvokeNode: TraceNode = {
    id: "reporting_reinvoke",
    agent_name: "Reporting",
    depth: 8,
    status: "ok",
    confidence_tier: "HIGH",
    latency_ms: 720,
    reasoning_summary: "Revised narrative addressing critic feedback",
    source_count: 4,
    used_llm: true,
    model: "gemini-3.5-flash-lite",
    tier: "mid",
    engine: "Gemini",
    run_count: 1,
  };

  return (
    <ol className="flex flex-col gap-1">
      <AgentTraceStep node={reportingNode} />
      <AgentTraceStep node={criticNode} />
      {/* Re-invocation marker */}
      <div className="pl-4 text-[10px] font-mono text-ink-dim">
        ↻ Critic calls Reporting again (×2)
      </div>
      {/* Re-invoked agent indented */}
      <AgentTraceStep node={reportingReinvokeNode} indent={2} />
    </ol>
  );
}

// Example 9: Complete trace with all features
export function CompleteTraceExample() {
  const nodes: TraceNode[] = [
    {
      id: "planning",
      agent_name: "Planning",
      depth: 2,
      status: "ok",
      confidence_tier: "HIGH",
      latency_ms: 610,
      reasoning_summary: "Matched SAFETY_CHECK on the keyword rules",
      source_count: 0,
      used_llm: false,
      model: null,
      tier: null,
      engine: "Deterministic",
      run_count: 1,
    },
    {
      id: "weather_intelligence",
      agent_name: "Weather Intelligence",
      depth: 4,
      status: "ok",
      confidence_tier: "HIGH",
      latency_ms: 480,
      reasoning_summary: "Hs 2.4 m vs small_fishing class band 2.0 m",
      source_count: 2,
      used_llm: false,
      model: null,
      tier: null,
      engine: "Deterministic",
      run_count: 1,
    },
    {
      id: "geospatial",
      agent_name: "Geospatial",
      depth: 4,
      status: "degraded",
      confidence_tier: "MEDIUM",
      latency_ms: 190,
      reasoning_summary: "Using cached data, live data unavailable",
      source_count: 3,
      used_llm: false,
      model: null,
      tier: null,
      engine: "Deterministic",
      run_count: 1,
    },
    {
      id: "reporting",
      agent_name: "Reporting",
      depth: 6,
      status: "ok",
      confidence_tier: "HIGH",
      latency_ms: 720,
      reasoning_summary: "Assembled the English narrative",
      source_count: 4,
      used_llm: true,
      model: "gemini-3.5-flash-lite",
      tier: "mid",
      engine: "Gemini",
      run_count: 2,
    },
  ];

  return (
    <ol className="flex flex-col gap-1" role="list" aria-label="Agent execution steps">
      {/* Base level step */}
      <AgentTraceStep node={nodes[0]} />

      {/* Parallel group */}
      <AgentTraceStep
        node={nodes[1]}
        indent={1}
        showGroupLabel="Parallel execution (2 agents):"
      />
      <AgentTraceStep node={nodes[2]} indent={1} />

      {/* Multi-run agent */}
      <AgentTraceStep node={nodes[3]} />
    </ol>
  );
}
