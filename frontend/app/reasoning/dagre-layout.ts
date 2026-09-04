import dagre from "dagre";
import { MarkerType, Position, type Edge, type Node } from "@xyflow/react";
import type { TraceEdge, TraceGraph, TraceNode } from "./fixture";

export const NODE_WIDTH = 270;
export const NODE_HEIGHT = 124;

export type AgentNodeData = {
  node: TraceNode;
};

export function layoutTrace(
  trace: TraceGraph,
  options?: {
    activeNodeIds?: Set<string>;
    completedNodeIds?: Set<string>;
  }
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph({ compound: true });
  g.setGraph({ rankdir: "LR", nodesep: 48, ranksep: 140, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of trace.nodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }

  for (const grp of trace.groups) {
    g.setNode(grp.id, {});
    for (const id of grp.node_ids) {
      g.setParent(id, grp.id);
    }
  }

  for (const e of trace.edges) {
    g.setEdge(e.from, e.to);
  }

  dagre.layout(g);

  // Group backdrop boxes (placed first so React Flow paints them behind nodes)
  const groupNodes: Node[] = trace.groups.map((grp) => {
    const box = g.node(grp.id);
    const label =
      grp.id === "fanout_0" || grp.id === "fanout-forecast"
        ? "Parallel Specialists · 3 Concurrent Streams"
        : grp.id === "fanout_1" || grp.id === "fanout-synthesis"
        ? "Synthesis Hub · Multi-Criteria Arbitration"
        : "Parallel Execution Group";

    return {
      id: grp.id,
      type: "fanoutGroup",
      position: { x: box.x - box.width / 2 - 16, y: box.y - box.height / 2 - 16 },
      style: { width: box.width + 32, height: box.height + 32, pointerEvents: "none" },
      data: { label },
      selectable: false,
      draggable: false,
      zIndex: -1,
    };
  });

  // Agent nodes positioned via clean absolute coordinates matching exact Dagre layout
  const agentNodes: Node[] = trace.nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      type: "agent",
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
      style: {
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      },
      data: { node: n } satisfies AgentNodeData,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });

  const nodes: Node[] = [...groupNodes, ...agentNodes];

  const activeNodes = options?.activeNodeIds ?? new Set<string>();
  const completedNodes = options?.completedNodeIds ?? new Set<string>();

  const edges: Edge[] = trace.edges.map((e: TraceEdge, i) => {
    const isSourceDone = completedNodes.has(e.from);
    const isTargetActive = activeNodes.has(e.to);
    const isTargetDone = completedNodes.has(e.to);

    // Edge is active if source finished and target is running or completed
    const isActive = isSourceDone && (isTargetActive || isTargetDone);
    const isCompleted = isSourceDone && isTargetDone;

    return {
      id: `${i}-${e.from}-${e.to}`,
      source: e.from,
      target: e.to,
      type: "animatedFlow",
      data: {
        kind: e.kind,
        label: e.label,
        isActive,
        isCompleted,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 14,
        height: 14,
        color: e.kind === "critic_loop" ? "#f0468c" : isActive ? "#38bdf8" : "#24576f",
      },
    };
  });

  return { nodes, edges };
}
