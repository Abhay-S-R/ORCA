// dagre left-to-right layout by execution depth (plan §5.10 Day 15) —
// computed once per trace via `useMemo` in the page, never per SSE frame.
// dagre's own rank algorithm (longest path from the source nodes) reproduces
// the graph's real execution depth on its own; it is not fed a hint.
//
// Parallel fan-out groups use dagre's compound-graph support (`setParent`)
// so the group box is a real computed bounding rectangle around its
// children, not a hand-placed div guessing at their layout.
import dagre from "dagre";
import { MarkerType, Position, type Edge, type Node } from "@xyflow/react";
import type { TraceEdge, TraceGraph, TraceNode } from "./fixture";

export const NODE_WIDTH = 248;
export const NODE_HEIGHT = 112;

export type AgentNodeData = { node: TraceNode };

export function layoutTrace(trace: TraceGraph): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph({ compound: true });
  g.setGraph({ rankdir: "LR", nodesep: 32, ranksep: 100, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of trace.nodes) g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  const parentOf = new Map<string, string>();
  for (const grp of trace.groups) {
    g.setNode(grp.id, {});
    for (const id of grp.node_ids) {
      g.setParent(id, grp.id);
      parentOf.set(id, grp.id);
    }
  }
  for (const e of trace.edges) g.setEdge(e.from, e.to);
  dagre.layout(g);

  // Group boxes pushed first: React Flow paints array order back-to-front,
  // so a group must precede its children or it would draw over them.
  const nodes: Node[] = trace.groups.map((grp) => {
    const box = g.node(grp.id);
    return {
      id: grp.id, type: "fanoutGroup",
      position: { x: box.x - box.width / 2, y: box.y - box.height / 2 },
      style: { width: box.width, height: box.height },
      data: {}, selectable: false, draggable: false, zIndex: -1,
    };
  });

  for (const n of trace.nodes) {
    const pos = g.node(n.id);
    const parentId = parentOf.get(n.id);
    const parentBox = parentId ? g.node(parentId) : null;
    const origin = parentBox
      ? { x: parentBox.x - parentBox.width / 2, y: parentBox.y - parentBox.height / 2 }
      : { x: 0, y: 0 };
    nodes.push({
      id: n.id, type: "agent",
      position: { x: pos.x - pos.width / 2 - origin.x, y: pos.y - pos.height / 2 - origin.y },
      parentId, extent: parentId ? "parent" : undefined,
      data: { node: n } satisfies AgentNodeData,
      sourcePosition: Position.Right, targetPosition: Position.Left,
    });
  }

  // Edge style carries meaning, same "never colour alone" rule as everywhere
  // else in the product (plan §4.4): solid = handoff, dashed = Critic
  // re-invocation loop, dotted = early-exit cancellation.
  const edges: Edge[] = trace.edges.map((e: TraceEdge, i) => ({
    id: `${i}-${e.from}-${e.to}`, source: e.from, target: e.to, label: e.label,
    type: "smoothstep", animated: e.kind === "critic_loop",
    style:
      e.kind === "cancelled" ? { strokeDasharray: "1 4", opacity: 0.5 }
      : e.kind === "critic_loop" ? { strokeDasharray: "6 4" }
      : undefined,
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
  }));

  return { nodes, edges };
}
