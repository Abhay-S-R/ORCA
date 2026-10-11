import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/jest-globals";
import { describe, it, expect, jest, beforeEach, afterEach } from "@jest/globals";
import { AgentTraceUI } from "./AgentTraceUI";

const mockApiTrace = {
  query_id: "test-query-123",
  nodes: [
    {
      id: "distress",
      agent_name: "distress",
      depth: 0,
      status: "ok",
      confidence_tier: "HIGH",
      latency_ms: 210,
      reasoning_summary: "No distress indicators detected",
      source_count: 0,
      used_llm: false,
      engine: "Deterministic",
    },
    {
      id: "planning",
      agent_name: "planning",
      depth: 1,
      status: "ok",
      confidence_tier: "HIGH",
      latency_ms: 450,
      reasoning_summary: "Generated 3-stage execution plan",
      source_count: 0,
      used_llm: true,
      engine: "Gemini",
      model: "gemini-2.5-flash",
      tier: "mid",
    },
  ],
  edges: [
    { from: "distress", to: "planning", kind: "handoff", label: "planning" },
  ],
  groups: [],
};

describe("AgentTraceUI Container & Data Fetching (Task 10)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders initially in collapsed summary state", () => {
    render(
      <AgentTraceUI
        spans={[{ agent_name: "distress", status: "ok", latency_ms: 210 }]}
        streaming={false}
        queryId="test-query-123"
      />
    );

    expect(screen.getByText("Thought for 210ms")).toBeInTheDocument();
  });

  it("fetches trace data on expand and integrates with adaptTraceGraph", async () => {
    global.fetch = jest.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockApiTrace),
      } as unknown as Response)
    ) as typeof fetch;

    render(
      <AgentTraceUI
        spans={[]}
        streaming={false}
        queryId="test-query-123"
      />
    );

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByText("Thought for 0ms")).toBeInTheDocument();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/trace/test-query-123"),
      expect.any(Object)
    );

    expect(screen.getByText("No distress indicators detected")).toBeInTheDocument();
    expect(screen.getByText("Generated 3-stage execution plan")).toBeInTheDocument();
  });

  it("displays loading skeleton state while fetching trace data", async () => {
    let resolveFetch: (value: Response) => void;
    const fetchPromise = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });

    global.fetch = jest.fn().mockImplementation(() => fetchPromise) as typeof fetch;

    render(
      <AgentTraceUI
        spans={[]}
        streaming={false}
        queryId="test-query-123"
      />
    );

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByRole("status", { name: /loading trace data/i })).toBeInTheDocument();

    resolveFetch!({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockApiTrace),
    } as unknown as Response);

    await waitFor(() => {
      expect(screen.queryByRole("status", { name: /loading trace data/i })).not.toBeInTheDocument();
      expect(screen.getByText("No distress indicators detected")).toBeInTheDocument();
    });
  });

  it("handles fetch errors and displays retry button", async () => {
    global.fetch = jest.fn().mockImplementation(() =>
      Promise.resolve({
        ok: false,
        status: 500,
      } as unknown as Response)
    ) as typeof fetch;

    render(
      <AgentTraceUI
        spans={[]}
        streaming={false}
        queryId="test-query-123"
      />
    );

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Retry")).toBeInTheDocument();
    });
  });

  it("falls back to streaming spans when API returns 404", async () => {
    global.fetch = jest.fn().mockImplementation(() =>
      Promise.resolve({
        ok: false,
        status: 404,
      } as unknown as Response)
    ) as typeof fetch;

    render(
      <AgentTraceUI
        spans={[{ agent_name: "distress", status: "ok", latency_ms: 180 }]}
        streaming={false}
        queryId="non-existent-query"
      />
    );

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByText("Thought for 180ms")).toBeInTheDocument();
      expect(screen.getByText("No distress signals detected")).toBeInTheDocument();
    });
  });
});
