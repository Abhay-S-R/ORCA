// Execution order calculation utility for Agent Trace UI
// This function converts a TraceGraph (nodes, edges, groups) into a flat,
// chronological list of ordered steps for UI rendering.
//
// NOTE ON FLAT LIST STRUCTURE:
// The current implementation produces a FLAT LIST with indentation markers
// to indicate relationships (parallel groups, critic loops). This design
// choice allows for simple, chronological rendering that matches the actual
// execution flow. If product requirements change in the future, this can be
// migrated to a tree structure - the algorithm already identifies the
// relationships needed for that transformation.

import type { TraceGraph, TraceNode, TraceEdge } from "../reasoning/fixture";
import { AGENT_LABEL } from "../reasoning/trace-adapter";

/**
 * OrderedStep represents one item in the flat execution order list.
 * Each step can be:
 * - A regular agent execution step
 * - A group label marker (e.g., "Parallel execution (3 agents):")
 * - A critic re-invocation marker
 */
export type OrderedStep =
  | { type: "step"; node: TraceNode; indent: number }
  | { type: "group_start"; label: string; groupId: string }
  | { type: "group_end"; groupId: string }
  | { type: "critic_reinvoke"; label: string; indent: number };

/**
 * Calculates the chronological execution order of agents from a TraceGraph.
 * 
 * Algorithm:
 * 1. Build adjacency list from edges for graph traversal
 * 2. Identify parallel groups from TraceGraph.groups
 * 3. Perform depth-first traversal starting from root node
 * 4. Group parallel agents together with visual grouping
 * 5. Nest critic loop re-invocations under the critique step
 * 
 * @param graph - The TraceGraph containing nodes, edges, and groups
 * @returns Flat list of ordered steps for chronological rendering
 */
export function calculateExecutionOrder(graph: TraceGraph): OrderedStep[] {
  // Build adjacency list from edges for efficient traversal
  const adjacency = buildAdjacencyList(graph.edges);
  
  // Create map of parallel groups for quick lookup
  const parallelGroups = new Map<string, string[]>();
  const nodeToGroup = new Map<string, string>();
  
  for (const group of graph.groups) {
    if (group.reason === "parallel_fanout") {
      parallelGroups.set(group.id, group.node_ids);
      for (const nodeId of group.node_ids) {
        nodeToGroup.set(nodeId, group.id);
      }
    }
  }
  
  // Track visited nodes to avoid cycles
  const visited = new Set<string>();
  const ordered: OrderedStep[] = [];
  
  // Find root node (depth 0) to start traversal
  const root = graph.nodes.find((n) => n.depth === 0);
  if (!root) {
    // If no root found, return empty list
    return ordered;
  }
  
  // Track which groups have been processed
  const processedGroups = new Set<string>();
  
  /**
   * Recursive depth-first traversal function.
   * Visits nodes in execution order and handles parallel groups and critic loops.
   * 
   * @param nodeId - Current node being visited
   * @param indent - Indentation level (0=base, 1=parallel, 2=critic loop)
   */
  function visit(nodeId: string, indent: number): void {
    // Skip if already visited to avoid infinite loops
    if (visited.has(nodeId)) {
      return;
    }
    
    const node = graph.nodes.find((n) => n.id === nodeId);
    if (!node) {
      return;
    }
    
    // Check if this node is part of a parallel group
    const groupId = nodeToGroup.get(nodeId);
    
    if (groupId && !processedGroups.has(groupId)) {
      // This is the first node we're encountering from this parallel group
      // Add group start marker
      const groupNodeIds = parallelGroups.get(groupId) || [];
      ordered.push({
        type: "group_start",
        label: `Parallel execution (${groupNodeIds.length} agents):`,
        groupId,
      });
      
      // Mark group as processed so we don't add the label again
      processedGroups.add(groupId);
      
      // Add all nodes in the parallel group with indentation
      for (const parallelNodeId of groupNodeIds) {
        if (!visited.has(parallelNodeId)) {
          const parallelNode = graph.nodes.find((n) => n.id === parallelNodeId);
          if (parallelNode) {
            visited.add(parallelNodeId);
            ordered.push({ type: "step", node: parallelNode, indent: 1 });
          }
        }
      }
      
      // Add group end marker
      ordered.push({ type: "group_end", groupId });
      
      // Continue traversal from the first node in the group
      // (all parallel nodes should have the same outgoing edges)
      const outgoingEdges = adjacency.get(nodeId) || [];
      for (const edge of outgoingEdges) {
        if (edge.kind === "handoff") {
          visit(edge.to, indent);
        }
      }
    } else if (groupId && processedGroups.has(groupId)) {
      // This node was already processed as part of its parallel group
      // Don't add it again, just skip
      return;
    } else {
      // Regular node (not part of a parallel group)
      visited.add(nodeId);
      ordered.push({ type: "step", node, indent });
      
      // Find critic loop edges (re-invocations)
      const criticLoopEdges = (adjacency.get(nodeId) || []).filter(
        (e) => e.kind === "critic_loop"
      );
      
      if (criticLoopEdges.length > 0) {
        // Add critic re-invocation marker
        const targetNode = graph.nodes.find((n) => n.id === criticLoopEdges[0].to);
        if (targetNode) {
          const targetName = AGENT_LABEL[targetNode.agent_name] ?? AGENT_LABEL[targetNode.id] ?? targetNode.agent_name;
          ordered.push({
            type: "critic_reinvoke",
            label: `↻ Critic calls ${targetName} again (×${targetNode.run_count || 1})`,
            indent: indent + 1,
          });
          
          // Visit re-invoked nodes with increased indentation
          for (const edge of criticLoopEdges) {
            visit(edge.to, indent + 1);
          }
        }
      }
      
      // Continue with normal handoff edges
      const handoffEdges = (adjacency.get(nodeId) || []).filter(
        (e) => e.kind === "handoff"
      );
      
      for (const edge of handoffEdges) {
        visit(edge.to, indent);
      }
    }
  }
  
  // Start traversal from root node
  visit(root.id, 0);
  
  return ordered;
}

/**
 * Builds an adjacency list representation of the graph from edges.
 * Maps each node ID to the list of edges originating from it.
 * 
 * @param edges - Array of TraceEdge objects
 * @returns Map from node ID to array of outgoing edges
 */
function buildAdjacencyList(edges: TraceEdge[]): Map<string, TraceEdge[]> {
  const adjacency = new Map<string, TraceEdge[]>();
  
  for (const edge of edges) {
    if (!adjacency.has(edge.from)) {
      adjacency.set(edge.from, []);
    }
    adjacency.get(edge.from)!.push(edge);
  }
  
  return adjacency;
}
