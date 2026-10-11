import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/jest-globals";
import { describe, it, expect, jest } from "@jest/globals";
import { ChatTurn } from "./ChatTurn";
import type { Turn } from "./useAskThread";

// Mock i18n
jest.mock("../i18n/useT", () => ({
  useT: () => (key: string) => key,
}));

// Mock Audio speaker to prevent DOM audio issues in jsdom
jest.mock("../components/AnswerSpeaker", () => ({
  AnswerSpeaker: () => <div data-testid="answer-speaker" />,
}));

// Mock MapView/navigation dependencies if any
jest.mock("../components/MapView", () => ({
  MapView: () => <div data-testid="map-view" />,
}));

function createMockTurn(overrides: Partial<Turn> = {}): Turn {
  return {
    id: "turn-1",
    askedQuery: "Can I sail to Mumbai today?",
    spans: [
      {
        agent_name: "weather_intelligence",
        status: "ok",
        latency_ms: 1200,
        confidence_tier: "HIGH",
        engine: "Deterministic",
      },
      {
        agent_name: "geospatial",
        status: "ok",
        latency_ms: 800,
        confidence_tier: "HIGH",
        engine: "Deterministic",
      },
    ],
    answer: {
      query_id: "query-abc-123",
      final_english_response: "Winds are 14 knots with wave heights around 1.2m.",
      confidence_tier: "HIGH",
    },
    streaming: false,
    failed: false,
    renderedAs: "fisherman",
    focus: null,
    ...overrides,
  };
}

describe("ChatTurn - AgentTraceUI Integration", () => {
  it("renders AgentTraceUI within ChatTurn by default", () => {
    const turn = createMockTurn();
    render(
      <ChatTurn
        turn={turn}
        persona="fisherman"
        hadEarlierAnswers={false}
        onRetry={() => {}}
        onRerun={() => {}}
        onShowVersion={() => {}}
        onFollowUp={() => {}}
      />
    );

    // AgentTraceUI renders collapsed view showing total time (1200ms + 800ms = 2.0s)
    expect(screen.getByText("Worked for 2.0s")).toBeInTheDocument();
    expect(screen.getByText("Can I sail to Mumbai today?")).toBeInTheDocument();
    expect(screen.getByText("Winds are 14 knots with wave heights around 1.2m.")).toBeInTheDocument();
  });

  it("integrates SSE stream updates when streaming is true", () => {
    const turn = createMockTurn({
      streaming: true,
      spans: [
        {
          agent_name: "weather_intelligence",
          status: "running",
          latency_ms: 450,
        },
      ],
      answer: null,
    });

    render(
      <ChatTurn
        turn={turn}
        persona="fisherman"
        hadEarlierAnswers={false}
        onRetry={() => {}}
        onRerun={() => {}}
        onShowVersion={() => {}}
        onFollowUp={() => {}}
      />
    );

    // Progress indicator displayed
    expect(screen.getByLabelText("Still working")).toBeInTheDocument();
    expect(screen.getByText("Worked for 450ms")).toBeInTheDocument();
  });

  it("positions AgentTraceUI above the answer content", () => {
    const turn = createMockTurn();
    const { container } = render(
      <ChatTurn
        turn={turn}
        persona="fisherman"
        hadEarlierAnswers={false}
        onRetry={() => {}}
        onRerun={() => {}}
        onShowVersion={() => {}}
        onFollowUp={() => {}}
      />
    );

    const traceElement = container.querySelector(".agent-trace-ui");
    const questionElement = screen.getByText("Can I sail to Mumbai today?");
    const answerElement = screen.getByText("Winds are 14 knots with wave heights around 1.2m.");

    expect(traceElement).toBeInTheDocument();
    expect(questionElement).toBeInTheDocument();
    expect(answerElement).toBeInTheDocument();

    // Verify ordering: question comes before trace, trace comes before answer
    const questionPos = questionElement.compareDocumentPosition(traceElement!);
    const answerPos = traceElement!.compareDocumentPosition(answerElement);

    expect(questionPos & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(answerPos & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("falls back to legacy AgentStrip when useAgentTraceUI is false", () => {
    const turn = createMockTurn();
    const { container } = render(
      <ChatTurn
        turn={turn}
        persona="fisherman"
        hadEarlierAnswers={false}
        onRetry={() => {}}
        onRerun={() => {}}
        onShowVersion={() => {}}
        onFollowUp={() => {}}
        useAgentTraceUI={false}
      />
    );

    // AgentTraceUI should not be rendered
    expect(container.querySelector(".agent-trace-ui")).not.toBeInTheDocument();

    // Legacy pills should be rendered
    expect(screen.getByText("Weather")).toBeInTheDocument();
    expect(screen.getByText("Geospatial")).toBeInTheDocument();
  });

  it("expands AgentTraceUI on click to show details", async () => {
    const turn = createMockTurn();
    render(
      <ChatTurn
        turn={turn}
        persona="fisherman"
        hadEarlierAnswers={false}
        onRetry={() => {}}
        onRerun={() => {}}
        onShowVersion={() => {}}
        onFollowUp={() => {}}
      />
    );

    const expandButton = screen.getByRole("button", { name: /worked for 2\.0s/i });
    fireEvent.click(expandButton);

    // Expanded heading should appear
    expect(await screen.findByText("▾ Agent Reasoning Trace")).toBeInTheDocument();
  });
});
