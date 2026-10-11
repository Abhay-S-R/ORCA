# Execution Order Calculation Function

## Overview

The `calculateExecutionOrder` function converts a `TraceGraph` (containing nodes, edges, and groups) into a flat, chronological list of ordered steps for UI rendering in the Agent Trace UI.

## Purpose

This function is the core algorithm for Task 3.1 of the Agent Trace UI Revamp spec. It determines the chronological execution order of agents from the TraceGraph data structure, producing a flat list that the UI will render with proper handling of:

- Sequential execution flow
- Parallel execution groups  
- Critic loop re-invocations
- Cancelled edges

## Design Philosophy

### Flat List Structure

The current implementation produces a **FLAT LIST** with indentation markers to indicate relationships. This design choice was made to:

1. **Match chronological flow**: The list mirrors the actual execution order
2. **Simplify rendering**: No complex tree traversal needed in UI components
3. **Allow future migration**: The algorithm already identifies relationships needed for tree structure
4. **Enable accessibility**: Screen readers can navigate a linear list more easily

**Important**: This is explicitly documented in the code to allow teammates to migrate to a tree structure if product requirements change in the future.

## Algorithm

The function uses a depth-first graph traversal with the following steps:

1. **Build adjacency list** from edges for efficient graph traversal
2. **Identify parallel groups** from `TraceGraph.groups`
3. **Find root node** (depth 0) to start traversal
4. **Depth-first traversal** visiting nodes in execution order:
   - Regular nodes are added with base indentation
   - Parallel groups are wrapped in `group_start`/`group_end` markers
   - All nodes in a parallel group get indent level 1
   - Critic loop edges trigger re-invocation markers
   - Re-invoked nodes get increased indentation (indent + 1)
5. **Cycle detection** via visited set prevents infinite loops

## Types

### OrderedStep

The output type representing one item in the execution order:

```typescript
type OrderedStep =
  | { type: "step"; node: TraceNode; indent: number }
  | { type: "group_start"; label: string; groupId: string }
  | { type: "group_end"; groupId: string }
  | { type: "critic_reinvoke"; label: string; indent: number };
```

**Step types:**
- `step`: A regular agent execution step with the TraceNode and indentation level
- `group_start`: Marker for beginning of parallel group (e.g., "Parallel execution (3 agents):")
- `group_end`: Marker for end of parallel group
- `critic_reinvoke`: Marker for critic loop re-invocation (e.g., "↻ Critic calls Reporting again (×2)")

**Indentation levels:**
- `0`: Base level (sequential agents)
- `1`: Parallel group members or first-level critic re-invocations
- `2`: Nested critic re-invocations (rare, but supported)

## Usage

```typescript
import { calculateExecutionOrder } from "./calculateExecutionOrder";
import { adaptTraceGraph } from "../reasoning/trace-adapter";

// Get trace data from API
const apiTrace = await fetch(`/trace/${queryId}`).then(r => r.json());
const traceGraph = adaptTraceGraph(apiTrace);

// Calculate execution order
const orderedSteps = calculateExecutionOrder(traceGraph);

// Render in UI
orderedSteps.forEach(step => {
  switch (step.type) {
    case "step":
      // Render agent step with indentation
      renderAgentStep(step.node, step.indent);
      break;
    case "group_start":
      // Render "Parallel execution (N agents):" label
      renderGroupLabel(step.label);
      break;
    case "group_end":
      // Optional: add spacing or visual separator
      break;
    case "critic_reinvoke":
      // Render "↻ Critic calls X again" with indentation
      renderReinvokeLabel(step.label, step.indent);
      break;
  }
});
```

## Examples

### Simple Linear Trace

```
Input: A -> B -> C

Output:
[
  { type: "step", node: A, indent: 0 },
  { type: "step", node: B, indent: 0 },
  { type: "step", node: C, indent: 0 }
]
```

### Parallel Execution

```
Input: Planning -> [Weather, Geo, Ocean] -> Reporting

Output:
[
  { type: "step", node: Planning, indent: 0 },
  { type: "group_start", label: "Parallel execution (3 agents):", groupId: "..." },
  { type: "step", node: Weather, indent: 1 },
  { type: "step", node: Geo, indent: 1 },
  { type: "step", node: Ocean, indent: 1 },
  { type: "group_end", groupId: "..." },
  { type: "step", node: Reporting, indent: 0 }
]
```

### Critic Loop

```
Input: Planning -> Reporting -> Critic --(critic_loop)--> Reporting

Output:
[
  { type: "step", node: Planning, indent: 0 },
  { type: "step", node: Reporting, indent: 0 },
  { type: "step", node: Critic, indent: 0 },
  { type: "critic_reinvoke", label: "↻ Critic calls Reporting again (×2)", indent: 1 },
  { type: "step", node: Reporting_reinvoked, indent: 1 }
]
```

## Edge Cases

The function handles several edge cases gracefully:

1. **Empty graph**: Returns empty array
2. **No root node**: Returns empty array (requires depth 0 node to start)
3. **Single node**: Returns single step
4. **Cycles**: Visited set prevents infinite loops
5. **Cancelled edges**: Not traversed (only handoff and critic_loop edges followed)
6. **Missing nodes**: Skipped if node not found in graph

## Testing

Comprehensive unit tests are provided in `calculateExecutionOrder.test.ts`:

- ✅ Simple linear trace ordering
- ✅ Parallel agent grouping with indentation
- ✅ Critic loop nesting
- ✅ Cancelled edge handling
- ✅ Empty graph
- ✅ No root node
- ✅ Single node
- ✅ Cycle detection
- ✅ Complex scenarios (parallel + critic loops combined)

## Performance

- **Time Complexity**: O(N + E) where N = nodes, E = edges
- **Space Complexity**: O(N) for visited set and output array
- **Typical Performance**: Handles 15+ agent traces efficiently (< 1ms)

The algorithm is optimized for the expected graph sizes (10-20 nodes) in production ORCA traces.

## Requirements Validation

This implementation satisfies the following requirements from `requirements.md`:

- **2.1**: Flat chronological list structure ✅
- **2.2**: Explicit code comments documenting flat list for future tree migration ✅
- **2.3**: Chronological ordering based on execution sequence ✅
- **2.4**: Uses TraceGraph edges to determine flow order ✅
- **5.1**: Re-invocations displayed as separate steps ✅
- **5.2**: Re-invoked agents shown with indentation ✅
- **6.1**: Parallel execution identified from TraceGraph.groups ✅
- **11.4**: Edge type handling (handoff, critic_loop, cancelled) ✅

## Future Enhancements

If product requirements change to use a tree structure instead of a flat list:

1. The algorithm already identifies all relationships (parent-child, siblings)
2. Change output type from `OrderedStep[]` to a tree node type
3. Build tree during traversal instead of flat list
4. UI components would need to handle tree rendering instead of flat iteration

The explicit code comments mark where this transformation would occur.
