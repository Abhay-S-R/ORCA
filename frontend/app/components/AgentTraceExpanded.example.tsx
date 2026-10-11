// Example usage of AgentTraceExpanded component
// This file demonstrates how to use the AgentTraceExpanded component
// to display a detailed trace view with chronological agent steps.

import React from "react";
import { AgentTraceExpanded } from "./AgentTraceExpanded";
import type { TraceGraph } from "../reasoning/fixture";

// Example 1: Simple linear trace
export function SimpleLinearTraceExample() {
  const simpleTrace: TraceGraph = {
    query_id: "example-simple",
    nodes: [
      {
        id: "planning",
        agent_name: "Planning",
        depth: 0,
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
        id: "reporting",
        agent_name: "Reporting",
        depth: 1,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 720,
        reasoning_summary: "Assembled the English narrative",
        source_count: 4,
        used_llm: true,
        model: "gemini-3.5-flash-lite",
        tier: "mid",
        engine: "Gemini",
        run_count: 1,
      },
      {
        id: "language_egress",
        agent_name: "Language Egress",
        depth: 2,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 410,
        reasoning_summary: "Translated the verdict back to Tamil",
        source_count: 0,
        used_llm: false,
        model: null,
        tier: null,
        engine: "IndicTrans2",
        run_count: 1,
      },
    ],
    edges: [
      { from: "planning", to: "reporting", kind: "handoff" },
      { from: "reporting", to: "language_egress", kind: "handoff" },
    ],
    groups: [],
  };

  const handleCollapse = () => console.log("Collapsed to summary view");

  return (
    <div className="max-w-3xl p-4">
      <AgentTraceExpanded
        traceGraph={simpleTrace}
        streaming={false}
        onCollapse={handleCollapse}
      />
    </div>
  );
}

// Example 2: Parallel execution trace
export function ParallelExecutionExample() {
  const parallelTrace: TraceGraph = {
    query_id: "example-parallel",
    nodes: [
      {
        id: "planning",
        agent_name: "Planning",
        depth: 0,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 610,
        reasoning_summary: "Matched SAFETY_CHECK pattern",
        source_count: 0,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "weather",
        agent_name: "Weather Intelligence",
        depth: 1,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 480,
        reasoning_summary: "Hs 2.4 m vs threshold 2.0 m → exceeded",
        source_count: 2,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "geo",
        agent_name: "Geospatial",
        depth: 1,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 190,
        reasoning_summary: "0.8 nm from EEZ boundary",
        source_count: 3,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "ocean",
        agent_name: "Ocean Analytics",
        depth: 1,
        status: "degraded",
        confidence_tier: "MEDIUM",
        latency_ms: 260,
        reasoning_summary: "Fallback data source used",
        source_count: 2,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "reporting",
        agent_name: "Reporting",
        depth: 2,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 720,
        reasoning_summary: "Assembled narrative from 3 specialists",
        source_count: 4,
        used_llm: true,
        model: "gemini-3.5-flash-lite",
        tier: "mid",
        engine: "Gemini",
        run_count: 1,
      },
    ],
    edges: [
      { from: "planning", to: "weather", kind: "handoff" },
      { from: "planning", to: "geo", kind: "handoff" },
      { from: "planning", to: "ocean", kind: "handoff" },
      { from: "weather", to: "reporting", kind: "handoff" },
      { from: "geo", to: "reporting", kind: "handoff" },
      { from: "ocean", to: "reporting", kind: "handoff" },
    ],
    groups: [
      {
        id: "parallel-specialists",
        node_ids: ["weather", "geo", "ocean"],
        reason: "parallel_fanout",
      },
    ],
  };

  const handleCollapse = () => console.log("Collapsed to summary view");

  return (
    <div className="max-w-3xl p-4">
      <AgentTraceExpanded
        traceGraph={parallelTrace}
        streaming={false}
        onCollapse={handleCollapse}
      />
    </div>
  );
}

// Example 3: Critic loop trace
export function CriticLoopExample() {
  const criticTrace: TraceGraph = {
    query_id: "example-critic-loop",
    nodes: [
      {
        id: "planning",
        agent_name: "Planning",
        depth: 0,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 610,
        reasoning_summary: "Query requires deep analysis",
        source_count: 0,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "reporting",
        agent_name: "Reporting",
        depth: 1,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 720,
        reasoning_summary: "Generated initial narrative",
        source_count: 4,
        used_llm: true,
        model: "gemini-3.5-flash-lite",
        tier: "mid",
        engine: "Gemini",
        run_count: 2, // Ran twice due to critic feedback
      },
      {
        id: "critic",
        agent_name: "Critic",
        depth: 2,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 1400,
        reasoning_summary: "Found issue with causal claims, requesting revision",
        source_count: 0,
        used_llm: true,
        model: "gemini-3.5-flash-lite",
        tier: "reasoning",
        engine: "Gemini",
        run_count: 1,
      },
      {
        id: "reporting_reinvoke",
        agent_name: "Reporting",
        depth: 3,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 680,
        reasoning_summary: "Revised narrative addressing critic feedback",
        source_count: 4,
        used_llm: true,
        model: "gemini-3.5-flash-lite",
        tier: "mid",
        engine: "Gemini",
        run_count: 1,
      },
      {
        id: "language_egress",
        agent_name: "Language Egress",
        depth: 4,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 410,
        reasoning_summary: "Translated approved narrative",
        source_count: 0,
        used_llm: false,
        model: null,
        tier: null,
        engine: "IndicTrans2",
        run_count: 1,
      },
    ],
    edges: [
      { from: "planning", to: "reporting", kind: "handoff" },
      { from: "reporting", to: "critic", kind: "handoff" },
      { from: "critic", to: "reporting_reinvoke", kind: "critic_loop" },
      { from: "reporting_reinvoke", to: "language_egress", kind: "handoff" },
    ],
    groups: [],
  };

  const handleCollapse = () => console.log("Collapsed to summary view");

  return (
    <div className="max-w-3xl p-4">
      <AgentTraceExpanded
        traceGraph={criticTrace}
        streaming={false}
        onCollapse={handleCollapse}
      />
    </div>
  );
}

// Example 4: Streaming trace (agents still running)
export function StreamingTraceExample() {
  const streamingTrace: TraceGraph = {
    query_id: "example-streaming",
    nodes: [
      {
        id: "planning",
        agent_name: "Planning",
        depth: 0,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 610,
        reasoning_summary: "Query analysis complete",
        source_count: 0,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "weather",
        agent_name: "Weather Intelligence",
        depth: 1,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 480,
        reasoning_summary: "Weather data retrieved",
        source_count: 2,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      // More agents would be added as they complete
    ],
    edges: [{ from: "planning", to: "weather", kind: "handoff" }],
    groups: [],
  };

  const handleCollapse = () => console.log("Collapsed to summary view");

  return (
    <div className="max-w-3xl p-4">
      <AgentTraceExpanded
        traceGraph={streamingTrace}
        streaming={true} // Shows "Processing..." indicator
        onCollapse={handleCollapse}
      />
    </div>
  );
}

// Example 5: Complex trace with all features
export function CompleteTraceExample() {
  const completeTrace: TraceGraph = {
    query_id: "example-complete",
    nodes: [
      {
        id: "distress_check",
        agent_name: "Distress Check",
        depth: 0,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 2,
        reasoning_summary: "No distress flag detected",
        source_count: 0,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "planning",
        agent_name: "Planning",
        depth: 1,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 610,
        reasoning_summary: "Matched SAFETY_CHECK pattern, deep mode",
        source_count: 0,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "weather",
        agent_name: "Weather Intelligence",
        depth: 2,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 480,
        reasoning_summary: "Hs 2.4 m exceeded threshold",
        source_count: 2,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "geo",
        agent_name: "Geospatial",
        depth: 2,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 190,
        reasoning_summary: "Near EEZ boundary",
        source_count: 3,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "ocean",
        agent_name: "Ocean Analytics",
        depth: 2,
        status: "degraded",
        confidence_tier: "MEDIUM",
        latency_ms: 260,
        reasoning_summary: "Using fallback data",
        source_count: 2,
        used_llm: false,
        model: null,
        tier: null,
        engine: "Deterministic",
        run_count: 1,
      },
      {
        id: "reporting",
        agent_name: "Reporting",
        depth: 3,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 720,
        reasoning_summary: "Initial narrative generated",
        source_count: 4,
        used_llm: true,
        model: "gemini-3.5-flash-lite",
        tier: "mid",
        engine: "Gemini",
        run_count: 2,
      },
      {
        id: "critic",
        agent_name: "Critic",
        depth: 4,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 1400,
        reasoning_summary: "Requested narrative revision",
        source_count: 0,
        used_llm: true,
        model: "gemini-3.5-flash-lite",
        tier: "reasoning",
        engine: "Gemini",
        run_count: 1,
      },
      {
        id: "reporting_reinvoke",
        agent_name: "Reporting",
        depth: 5,
        status: "ok",
        confidence_tier: "HIGH",
        latency_ms: 680,
        reasoning_summary: "Revised narrative approved",
        source_count: 4,
        used_llm: true,
        model: "gemini-3.5-flash-lite",
        tier: "mid",
        engine: "Gemini",
        run_count: 1,
      },
    ],
    edges: [
      { from: "distress_check", to: "planning", kind: "handoff" },
      { from: "planning", to: "weather", kind: "handoff" },
      { from: "planning", to: "geo", kind: "handoff" },
      { from: "planning", to: "ocean", kind: "handoff" },
      { from: "weather", to: "reporting", kind: "handoff" },
      { from: "geo", to: "reporting", kind: "handoff" },
      { from: "ocean", to: "reporting", kind: "handoff" },
      { from: "reporting", to: "critic", kind: "handoff" },
      { from: "critic", to: "reporting_reinvoke", kind: "critic_loop" },
    ],
    groups: [
      {
        id: "parallel-specialists",
        node_ids: ["weather", "geo", "ocean"],
        reason: "parallel_fanout",
      },
    ],
  };

  const handleCollapse = () => console.log("Collapsed to summary view");

  return (
    <div className="max-w-3xl p-4">
      <AgentTraceExpanded
        traceGraph={completeTrace}
        streaming={false}
        onCollapse={handleCollapse}
      />
    </div>
  );
}
