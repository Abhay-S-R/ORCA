import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/jest-globals";
import { describe, it, expect, jest, beforeEach, afterEach } from "@jest/globals";
import { AgentTraceUI, type AgentSpan } from "./AgentTraceUI";

describe("AgentTraceUI Streaming Updates (Task 7)", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("updates collapsed view dynamic action text as spans arrive", () => {
    const { rerender } = render(
      <AgentTraceUI spans={[]} streaming={true} />
    );

    expect(screen.getByText("Scanning for distress signals…")).toBeInTheDocument();

    const span1: AgentSpan = {
      agent_name: "distress",
      status: "ok",
      latency_ms: 150,
    };

    rerender(<AgentTraceUI spans={[span1]} streaming={true} />);

    expect(screen.getByText("Analyzing the query and planning my approach…")).toBeInTheDocument();

    const span2: AgentSpan = {
      agent_name: "planning",
      status: "ok",
      latency_ms: 950,
    };

    rerender(<AgentTraceUI spans={[span1, span2]} streaming={true} />);

    expect(screen.getByText(/Gathering weather and sea conditions/)).toBeInTheDocument();
  });

  it("shows streaming progress indicator while streaming and displays total time on completion", () => {
    const { rerender } = render(
      <AgentTraceUI
        spans={[{ agent_name: "distress", status: "ok", latency_ms: 200 }]}
        streaming={true}
      />
    );

    expect(screen.getByText("Analyzing the query and planning my approach…")).toBeInTheDocument();

    rerender(
      <AgentTraceUI
        spans={[{ agent_name: "distress", status: "ok", latency_ms: 200 }]}
        streaming={false}
      />
    );

    expect(screen.getByText("Thought for 200ms")).toBeInTheDocument();
  });

  it("updates active step text immediately when new spans arrive", () => {
    const { rerender } = render(<AgentTraceUI spans={[]} streaming={true} />);

    expect(screen.getByText("Scanning for distress signals…")).toBeInTheDocument();

    const span1: AgentSpan = { agent_name: "distress", status: "ok", latency_ms: 100 };
    rerender(<AgentTraceUI spans={[span1]} streaming={true} />);

    expect(screen.getByText("Analyzing the query and planning my approach…")).toBeInTheDocument();
  });
});
