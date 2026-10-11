import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/jest-globals";
import { describe, it, expect } from "@jest/globals";
import { AgentTraceStep } from "./AgentTraceStep";
import type { TraceNode } from "../reasoning/fixture";

function createMockNode(overrides: Partial<TraceNode> = {}): TraceNode {
  return {
    id: "weather_intelligence",
    agent_name: "weather_intelligence",
    depth: 4,
    status: "ok",
    confidence_tier: "HIGH",
    latency_ms: 1200,
    reasoning_summary: "Forecast computed from Open-Meteo",
    source_count: 1,
    used_llm: false,
    model: null,
    tier: null,
    engine: "Deterministic",
    run_count: 1,
    skip_reason: null,
    ...overrides,
  };
}

describe("AgentTraceStep", () => {
  it("renders human-readable agent name using AGENT_LABEL", () => {
    const node = createMockNode({ agent_name: "weather_intelligence" });
    render(<AgentTraceStep node={node} />);
    expect(screen.getByText("Weather Intelligence")).toBeInTheDocument();
  });

  it("renders latency formatted properly", () => {
    const node = createMockNode({ latency_ms: 1200 });
    render(<AgentTraceStep node={node} />);
    expect(screen.getByText("1.2s")).toBeInTheDocument();

    const fastNode = createMockNode({ latency_ms: 450 });
    render(<AgentTraceStep node={fastNode} />);
    expect(screen.getByText("450ms")).toBeInTheDocument();
  });

  it("renders all status types correctly (ok, degraded, failed, skipped, cancelled)", () => {
    const statuses: Array<TraceNode["status"]> = ["ok", "degraded", "failed", "skipped", "cancelled"];
    for (const status of statuses) {
      const node = createMockNode({ status });
      const { container } = render(<AgentTraceStep node={node} />);
      const item = container.querySelector("li");
      expect(item).toBeInTheDocument();
    }
  });

  it("displays confidence badge for completed ok/degraded nodes", () => {
    const node = createMockNode({ status: "ok", confidence_tier: "HIGH" });
    render(<AgentTraceStep node={node} />);
    expect(screen.getByText("H")).toBeInTheDocument();
  });

  it("does not display confidence badge for skipped/cancelled nodes", () => {
    const node = createMockNode({ status: "skipped", confidence_tier: "HIGH", skip_reason: "Not planned" });
    render(<AgentTraceStep node={node} />);
    expect(screen.queryByText("H")).not.toBeInTheDocument();
  });

  it("displays run count badge when run_count > 1", () => {
    const node = createMockNode({ run_count: 2 });
    render(<AgentTraceStep node={node} />);
    expect(screen.getByText("×2")).toBeInTheDocument();
  });

  it("applies correct indentation classes", () => {
    const node = createMockNode();
    const { container: c0 } = render(<AgentTraceStep node={node} indent={0} />);
    expect(c0.querySelector("li")?.className).not.toContain("pl-4");

    const { container: c1 } = render(<AgentTraceStep node={node} indent={1} />);
    expect(c1.querySelector("li")?.className).toContain("pl-4");

    const { container: c2 } = render(<AgentTraceStep node={node} indent={2} />);
    expect(c2.querySelector("li")?.className).toContain("pl-8");
  });

  it("displays info tooltip with engine and reasoning summary", () => {
    const node = createMockNode({
      engine: "Deterministic",
      reasoning_summary: "Detailed reasoning overview",
    });
    render(<AgentTraceStep node={node} />);
    const infoButton = screen.getByLabelText("Show step details");
    fireEvent.mouseEnter(infoButton);

    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    expect(screen.getByText(/Engine: Deterministic/)).toBeInTheDocument();
    expect(screen.getByText(/Summary: Detailed reasoning overview/)).toBeInTheDocument();
  });
});
