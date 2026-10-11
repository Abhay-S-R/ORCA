import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/jest-globals";
import { describe, it, expect, jest } from "@jest/globals";
import { AgentTraceCollapsed } from "./AgentTraceCollapsed";

describe("AgentTraceCollapsed", () => {
  it("formats and displays execution time correctly for seconds", () => {
    render(
      <AgentTraceCollapsed
        totalTimeMs={3200}
        streaming={false}
        onExpand={() => {}}
      />
    );
    expect(screen.getByText("Thought for 3.2s")).toBeInTheDocument();
  });

  it("formats and displays execution time correctly for milliseconds", () => {
    render(
      <AgentTraceCollapsed
        totalTimeMs={450}
        streaming={false}
        onExpand={() => {}}
      />
    );
    expect(screen.getByText("Thought for 450ms")).toBeInTheDocument();
  });

  it("shows currentText when streaming=true", () => {
    render(
      <AgentTraceCollapsed
        totalTimeMs={1500}
        streaming={true}
        currentText="Scanning for distress signals…"
        onExpand={() => {}}
      />
    );
    expect(screen.getByText("Scanning for distress signals…")).toBeInTheDocument();
  });

  it("calls onExpand when clicked", () => {
    const handleExpand = jest.fn();
    render(
      <AgentTraceCollapsed
        totalTimeMs={2000}
        streaming={false}
        onExpand={handleExpand}
      />
    );

    fireEvent.click(screen.getByRole("button"));
    expect(handleExpand).toHaveBeenCalledTimes(1);
  });

  it("supports keyboard expansion with Enter and Space keys", () => {
    const handleExpand = jest.fn();
    render(
      <AgentTraceCollapsed
        totalTimeMs={2000}
        streaming={false}
        onExpand={handleExpand}
      />
    );

    const button = screen.getByRole("button");
    fireEvent.keyDown(button, { key: "Enter" });
    expect(handleExpand).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(button, { key: " " });
    expect(handleExpand).toHaveBeenCalledTimes(2);
  });
});
