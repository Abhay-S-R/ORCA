import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/jest-globals";
import { describe, it, expect, jest } from "@jest/globals";
import { AgentTraceExpanded } from "./AgentTraceExpanded";
import type { TraceGraph, TraceNode } from "../reasoning/fixture";

function createNode(
  id: string,
  agent_name: string,
  depth: number = 0,
  overrides: Partial<TraceNode> = {}
): TraceNode {
  return {
    id,
    agent_name,
    depth,
    status: "ok",
    confidence_tier: "HIGH",
    latency_ms: 100,
    reasoning_summary: "Test summary",
    source_count: 0,
    used_llm: false,
    model: null,
    tier: null,
    engine: "Deterministic",
    run_count: 1,
    skip_reason: null,
    ...overrides,
  };
}

describe("AgentTraceExpanded", () => {
  it("renders steps in chronological execution order", () => {
    const graph: TraceGraph = {
      query_id: "test-order",
      nodes: [
        createNode("distress", "distress", 0),
        createNode("language_ingress", "language_ingress", 1),
        createNode("planning", "planning", 2),
      ],
      edges: [
        { from: "distress", to: "language_ingress", kind: "handoff" },
        { from: "language_ingress", to: "planning", kind: "handoff" },
      ],
      groups: [],
    };

    render(
      <AgentTraceExpanded
        traceGraph={graph}
        streaming={false}
        onCollapse={() => {}}
      />
    );

    expect(screen.getByText("Distress Check")).toBeInTheDocument();
    expect(screen.getByText("Language Ingress")).toBeInTheDocument();
    expect(screen.getByText("Planning")).toBeInTheDocument();
  });

  it("renders parallel agent groups with grouping label and indentation", () => {
    const graph: TraceGraph = {
      query_id: "test-parallel",
      nodes: [
        createNode("planning", "planning", 0),
        createNode("weather_intelligence", "weather_intelligence", 1),
        createNode("geospatial", "geospatial", 1),
      ],
      edges: [
        { from: "planning", to: "weather_intelligence", kind: "handoff" },
        { from: "planning", to: "geospatial", kind: "handoff" },
      ],
      groups: [
        {
          id: "fanout_1",
          node_ids: ["weather_intelligence", "geospatial"],
          reason: "parallel_fanout",
        },
      ],
    };

    render(
      <AgentTraceExpanded
        traceGraph={graph}
        streaming={false}
        onCollapse={() => {}}
      />
    );

    expect(screen.getByText("Parallel execution (2 agents):")).toBeInTheDocument();
    expect(screen.getByText("Weather Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Geospatial")).toBeInTheDocument();
  });

  it("renders critic loop re-invocation notice", () => {
    const reportingNode = createNode("reporting", "reporting", 0, { run_count: 2 });
    const criticNode = createNode("critic", "critic", 1);

    const graph: TraceGraph = {
      query_id: "test-critic",
      nodes: [reportingNode, criticNode],
      edges: [
        { from: "reporting", to: "critic", kind: "handoff" },
        { from: "critic", to: "reporting", kind: "critic_loop" },
      ],
      groups: [],
    };

    render(
      <AgentTraceExpanded
        traceGraph={graph}
        streaming={false}
        onCollapse={() => {}}
      />
    );

    expect(screen.getByText(/↻ Critic calls Reporting again/)).toBeInTheDocument();
  });

  it("calls onCollapse when close button is clicked", () => {
    const handleCollapse = jest.fn();
    const graph: TraceGraph = {
      query_id: "test-collapse",
      nodes: [createNode("distress", "distress", 0)],
      edges: [],
      groups: [],
    };

    render(
      <AgentTraceExpanded
        traceGraph={graph}
        streaming={false}
        onCollapse={handleCollapse}
      />
    );

    fireEvent.click(screen.getByLabelText("Collapse trace to summary view"));
    expect(handleCollapse).toHaveBeenCalledTimes(1);
  });

  it("handles empty trace graph gracefully", () => {
    const graph: TraceGraph = {
      query_id: "test-empty",
      nodes: [],
      edges: [],
      groups: [],
    };

    render(
      <AgentTraceExpanded
        traceGraph={graph}
        streaming={false}
        onCollapse={() => {}}
      />
    );

    expect(screen.getByText("No agent execution data available")).toBeInTheDocument();
  });
});
