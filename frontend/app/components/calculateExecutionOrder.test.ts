/* eslint-disable @typescript-eslint/no-explicit-any */
// Unit tests for calculateExecutionOrder function
// These tests verify the execution order algorithm handles:
// - Simple linear traces
// - Parallel agent grouping
// - Critic loop nesting
// - Cancelled edges
// - Edge cases (empty graph, single node, cycles)

import { describe, it, expect } from "@jest/globals";
import { calculateExecutionOrder } from "./calculateExecutionOrder";
import type { TraceGraph, TraceNode } from "../reasoning/fixture";

// Helper function to create a minimal TraceNode
function createNode(
  id: string,
  agent_name: string,
  depth: number = 0
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
    run_count: 1,
  };
}

describe("calculateExecutionOrder", () => {
  describe("simple linear trace", () => {
    it("should order nodes in a simple linear sequence", () => {
      const graph: TraceGraph = {
        query_id: "test-linear",
        nodes: [
          createNode("a", "Agent A", 0),
          createNode("b", "Agent B", 1),
          createNode("c", "Agent C", 2),
        ],
        edges: [
          { from: "a", to: "b", kind: "handoff" },
          { from: "b", to: "c", kind: "handoff" },
        ],
        groups: [],
      };

      const result = calculateExecutionOrder(graph);

      expect(result).toHaveLength(3);
      expect(result[0]).toEqual({ type: "step", node: graph.nodes[0], indent: 0 });
      expect(result[1]).toEqual({ type: "step", node: graph.nodes[1], indent: 0 });
      expect(result[2]).toEqual({ type: "step", node: graph.nodes[2], indent: 0 });
    });
  });

  describe("parallel agent grouping", () => {
    it("should group parallel agents together with correct indentation", () => {
      const graph: TraceGraph = {
        query_id: "test-parallel",
        nodes: [
          createNode("planning", "Planning", 0),
          createNode("weather", "Weather", 1),
          createNode("geo", "Geospatial", 1),
          createNode("ocean", "Ocean", 1),
          createNode("reporting", "Reporting", 2),
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
            id: "parallel-group",
            node_ids: ["weather", "geo", "ocean"],
            reason: "parallel_fanout",
          },
        ],
      };

      const result = calculateExecutionOrder(graph);

      // Should have: planning step + group_start + 3 parallel steps + group_end + reporting step
      expect(result).toHaveLength(7);
      
      expect(result[0].type).toBe("step");
      expect((result[0] as any).node.id).toBe("planning");
      
      expect(result[1].type).toBe("group_start");
      expect((result[1] as any).label).toBe("Parallel execution (3 agents):");
      
      expect(result[2].type).toBe("step");
      expect((result[2] as any).indent).toBe(1);
      expect((result[2] as any).node.id).toBe("weather");
      
      expect(result[3].type).toBe("step");
      expect((result[3] as any).indent).toBe(1);
      expect((result[3] as any).node.id).toBe("geo");
      
      expect(result[4].type).toBe("step");
      expect((result[4] as any).indent).toBe(1);
      expect((result[4] as any).node.id).toBe("ocean");
      
      expect(result[5].type).toBe("group_end");
      
      expect(result[6].type).toBe("step");
      expect((result[6] as any).node.id).toBe("reporting");
    });
  });

  describe("critic loop nesting", () => {
    it("should nest critic loop re-invocations with increased indentation", () => {
      const reportingNode = createNode("reporting", "Reporting", 2);
      reportingNode.run_count = 2;

      const graph: TraceGraph = {
        query_id: "test-critic",
        nodes: [
          createNode("planning", "Planning", 0),
          reportingNode,
          createNode("critic", "Critic", 3),
          createNode("reporting_reinvoke", "Reporting", 4),
        ],
        edges: [
          { from: "planning", to: "reporting", kind: "handoff" },
          { from: "reporting", to: "critic", kind: "handoff" },
          { from: "critic", to: "reporting_reinvoke", kind: "critic_loop" },
        ],
        groups: [],
      };

      const result = calculateExecutionOrder(graph);

      // Should have: planning + reporting + critic + critic_reinvoke label + reporting_reinvoke
      expect(result.length).toBeGreaterThanOrEqual(5);
      
      // Find the critic_reinvoke marker
      const criticReinvokeStep = result.find((step) => step.type === "critic_reinvoke");
      expect(criticReinvokeStep).toBeDefined();
      expect((criticReinvokeStep as any).label).toMatch(/Critic calls Reporting again|Requesting Reporting to refine its analysis/);
      expect((criticReinvokeStep as any).indent).toBe(1); // Indented under critic
      
      // The re-invoked node should also be indented
      const reinvokedStep = result.find(
        (step) => step.type === "step" && (step as any).node.id === "reporting_reinvoke"
      );
      expect(reinvokedStep).toBeDefined();
      expect((reinvokedStep as any).indent).toBe(1);
    });
  });

  describe("cancelled edge handling", () => {
    it("should handle cancelled edges without traversing them", () => {
      const graph: TraceGraph = {
        query_id: "test-cancelled",
        nodes: [
          createNode("a", "Agent A", 0),
          createNode("b", "Agent B", 1),
          createNode("c", "Agent C", 1), // This should not be visited
        ],
        edges: [
          { from: "a", to: "b", kind: "handoff" },
          { from: "a", to: "c", kind: "cancelled" },
        ],
        groups: [],
      };

      const result = calculateExecutionOrder(graph);

      // Should only have A and B, not C
      expect(result).toHaveLength(2);
      expect((result[0] as any).node.id).toBe("a");
      expect((result[1] as any).node.id).toBe("b");
    });
  });

  describe("edge cases", () => {
    it("should handle empty graph", () => {
      const graph: TraceGraph = {
        query_id: "test-empty",
        nodes: [],
        edges: [],
        groups: [],
      };

      const result = calculateExecutionOrder(graph);
      expect(result).toHaveLength(0);
    });

    it("should handle graph with no root node", () => {
      const graph: TraceGraph = {
        query_id: "test-no-root",
        nodes: [
          createNode("a", "Agent A", 1),
          createNode("b", "Agent B", 2),
        ],
        edges: [{ from: "a", to: "b", kind: "handoff" }],
        groups: [],
      };

      const result = calculateExecutionOrder(graph);
      expect(result).toHaveLength(0);
    });

    it("should handle single node graph", () => {
      const graph: TraceGraph = {
        query_id: "test-single",
        nodes: [createNode("a", "Agent A", 0)],
        edges: [],
        groups: [],
      };

      const result = calculateExecutionOrder(graph);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual({ type: "step", node: graph.nodes[0], indent: 0 });
    });

    it("should avoid infinite loops with cycles", () => {
      const graph: TraceGraph = {
        query_id: "test-cycle",
        nodes: [
          createNode("a", "Agent A", 0),
          createNode("b", "Agent B", 1),
          createNode("c", "Agent C", 2),
        ],
        edges: [
          { from: "a", to: "b", kind: "handoff" },
          { from: "b", to: "c", kind: "handoff" },
          { from: "c", to: "b", kind: "handoff" }, // Cycle back to B
        ],
        groups: [],
      };

      const result = calculateExecutionOrder(graph);

      // Should visit each node only once
      expect(result).toHaveLength(3);
      expect((result[0] as any).node.id).toBe("a");
      expect((result[1] as any).node.id).toBe("b");
      expect((result[2] as any).node.id).toBe("c");
    });
  });

  describe("complex scenario", () => {
    it("should handle a complex trace with parallel groups and critic loops", () => {
      const reportingNode = createNode("reporting", "Reporting", 5);
      reportingNode.run_count = 2;

      const graph: TraceGraph = {
        query_id: "test-complex",
        nodes: [
          createNode("planning", "Planning", 0),
          createNode("weather", "Weather", 1),
          createNode("geo", "Geospatial", 1),
          createNode("ocean", "Ocean", 1),
          reportingNode,
          createNode("critic", "Critic", 6),
          createNode("reporting_reinvoke", "Reporting", 7),
        ],
        edges: [
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
            id: "parallel-group",
            node_ids: ["weather", "geo", "ocean"],
            reason: "parallel_fanout",
          },
        ],
      };

      const result = calculateExecutionOrder(graph);

      // Verify structure: planning + group + 3 parallel + group_end + reporting + critic + reinvoke marker + reporting_reinvoke
      expect(result.length).toBeGreaterThanOrEqual(9);
      
      // Planning should be first
      expect(result[0].type).toBe("step");
      expect((result[0] as any).node.id).toBe("planning");
      
      // Should have parallel group
      const groupStart = result.find((step) => step.type === "group_start");
      expect(groupStart).toBeDefined();
      
      // Should have critic reinvoke marker
      const criticReinvoke = result.find((step) => step.type === "critic_reinvoke");
      expect(criticReinvoke).toBeDefined();
      
      // All parallel nodes should have indent 1
      const parallelSteps = result.filter(
        (step) =>
          step.type === "step" &&
          ["weather", "geo", "ocean"].includes((step as any).node.id)
      );
      expect(parallelSteps).toHaveLength(3);
      parallelSteps.forEach((step) => {
        expect((step as any).indent).toBe(1);
      });
    });
  });
});
