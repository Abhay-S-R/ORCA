import React from "react";
import { render, screen, act } from "@testing-library/react";
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

  it("updates collapsed view total time incrementally as spans arrive", () => {
    const { rerender } = render(
      <AgentTraceUI spans={[]} streaming={true} />
    );

    expect(screen.getByText("Worked for 0ms")).toBeInTheDocument();

    const span1: AgentSpan = {
      agent_name: "distress",
      status: "ok",
      latency_ms: 150,
    };

    rerender(<AgentTraceUI spans={[span1]} streaming={true} />);
    act(() => {
      jest.advanceTimersByTime(100);
    });

    expect(screen.getByText("Worked for 150ms")).toBeInTheDocument();

    const span2: AgentSpan = {
      agent_name: "planning",
      status: "ok",
      latency_ms: 950,
    };

    rerender(<AgentTraceUI spans={[span1, span2]} streaming={true} />);
    act(() => {
      jest.advanceTimersByTime(100);
    });

    expect(screen.getByText("Worked for 1.1s")).toBeInTheDocument();
  });

  it("shows streaming progress indicator while streaming and removes it on completion", () => {
    const { rerender } = render(
      <AgentTraceUI
        spans={[{ agent_name: "distress", status: "ok", latency_ms: 200 }]}
        streaming={true}
      />
    );
    act(() => {
      jest.advanceTimersByTime(100);
    });

    expect(screen.getByLabelText("Still working")).toBeInTheDocument();

    rerender(
      <AgentTraceUI
        spans={[{ agent_name: "distress", status: "ok", latency_ms: 200 }]}
        streaming={false}
      />
    );

    expect(screen.queryByLabelText("Still working")).not.toBeInTheDocument();
  });

  it("debounces rapid span events within 100ms window", () => {
    const { rerender } = render(<AgentTraceUI spans={[]} streaming={true} />);

    const span1: AgentSpan = { agent_name: "distress", status: "ok", latency_ms: 100 };
    rerender(<AgentTraceUI spans={[span1]} streaming={true} />);

    // Advance 50ms (less than debounce delay of 100ms)
    act(() => {
      jest.advanceTimersByTime(50);
    });
    // Should still display initial 0ms before debounce triggers
    expect(screen.getByText("Worked for 0ms")).toBeInTheDocument();

    // Now advance remaining 50ms
    act(() => {
      jest.advanceTimersByTime(50);
    });
    expect(screen.getByText("Worked for 100ms")).toBeInTheDocument();
  });
});
