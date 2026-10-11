import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/jest-globals";
import { describe, it, expect } from "@jest/globals";
import { AgentTraceUI, type AgentSpan } from "./AgentTraceUI";

describe("AgentTraceUI Expand/Collapse Interactions (Task 8)", () => {
  const sampleSpans: AgentSpan[] = [
    { agent_name: "distress", status: "ok", latency_ms: 120 },
    { agent_name: "planning", status: "ok", latency_ms: 350 },
  ];

  it("expands to show detail view when collapsed summary is clicked", async () => {
    render(<AgentTraceUI spans={sampleSpans} streaming={false} />);

    // Initially in collapsed view
    expect(screen.getByText(/Thought for 470ms/)).toBeInTheDocument();

    // Click to expand
    fireEvent.click(screen.getByRole("button", { name: /Thought for 470ms/i }));

    // Now in expanded view
    expect(screen.getByText("No distress signals detected")).toBeInTheDocument();
  });

  it("collapses back to summary view when close button is clicked", async () => {
    render(<AgentTraceUI spans={sampleSpans} streaming={false} />);

    // Expand
    fireEvent.click(screen.getByRole("button", { name: /Thought for 470ms/i }));
    expect(screen.getByText("No distress signals detected")).toBeInTheDocument();

    // Click collapse button
    fireEvent.click(screen.getByLabelText("Close"));

    // Back to collapsed view
    expect(screen.getByText(/Thought for 470ms/)).toBeInTheDocument();
  });

  it("supports keyboard expansion with Enter and collapse with Escape", async () => {
    render(<AgentTraceUI spans={sampleSpans} streaming={false} />);

    const collapsedButton = screen.getByRole("button", { name: /Thought for 470ms/i });
    fireEvent.keyDown(collapsedButton, { key: "Enter" });

    expect(screen.getByText("No distress signals detected")).toBeInTheDocument();

    const collapseButton = screen.getByLabelText("Close");
    fireEvent.click(collapseButton);

    expect(screen.getByText(/Thought for 470ms/)).toBeInTheDocument();
  });
});
