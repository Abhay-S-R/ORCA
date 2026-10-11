import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom/jest-globals";
import { describe, it, expect, jest } from "@jest/globals";
import { AgentTraceUI, type AgentSpan } from "./AgentTraceUI";

describe("AgentTraceUI Expand/Collapse Interactions (Task 8)", () => {
  const sampleSpans: AgentSpan[] = [
    { agent_name: "distress", status: "ok", latency_ms: 120 },
    { agent_name: "planning", status: "ok", latency_ms: 350 },
  ];

  it("expands to show detail view when collapsed summary is clicked", async () => {
    render(<AgentTraceUI spans={sampleSpans} streaming={false} />);

    // Initially in collapsed view
    expect(screen.getByText(/Worked for 470ms/)).toBeInTheDocument();
    expect(screen.queryByText("▾ Agent Reasoning Trace")).not.toBeInTheDocument();

    // Click to expand
    fireEvent.click(screen.getByRole("button", { name: /Agent trace: worked for/i }));

    // Now in expanded view
    expect(screen.getByText("▾ Agent Reasoning Trace")).toBeInTheDocument();
    expect(screen.getByText("Distress Check")).toBeInTheDocument();
    expect(screen.getByText("Planning")).toBeInTheDocument();
  });

  it("collapses back to summary view when close button is clicked", async () => {
    render(<AgentTraceUI spans={sampleSpans} streaming={false} />);

    // Expand
    fireEvent.click(screen.getByRole("button", { name: /Agent trace: worked for/i }));
    expect(screen.getByText("▾ Agent Reasoning Trace")).toBeInTheDocument();

    // Click collapse button
    fireEvent.click(screen.getByLabelText("Collapse trace to summary view"));

    // Back to collapsed view
    expect(screen.queryByText("▾ Agent Reasoning Trace")).not.toBeInTheDocument();
    expect(screen.getByText(/Worked for 470ms/)).toBeInTheDocument();
  });

  it("supports keyboard expansion with Enter and collapse with Escape", async () => {
    render(<AgentTraceUI spans={sampleSpans} streaming={false} />);

    const collapsedButton = screen.getByRole("button", { name: /Agent trace: worked for/i });
    fireEvent.keyDown(collapsedButton, { key: "Enter" });

    expect(screen.getByText("▾ Agent Reasoning Trace")).toBeInTheDocument();

    const collapseButton = screen.getByLabelText("Collapse trace to summary view");
    fireEvent.keyDown(collapseButton, { key: "Escape" });

    expect(screen.queryByText("▾ Agent Reasoning Trace")).not.toBeInTheDocument();
  });
});
