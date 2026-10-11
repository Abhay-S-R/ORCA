# AgentTraceExpanded Component

## Overview

The `AgentTraceExpanded` component displays a detailed, chronological view of agent execution steps in the Agent Trace UI. It renders a flat list of agent steps showing parallel execution patterns, critic loops, and real-time streaming updates.

## Features

- **Flat Chronological List**: Displays agent steps in execution order as a flat list (not a tree structure)
- **Parallel Execution Grouping**: Groups parallel agents with "Parallel execution (N agents):" label
- **Critic Loop Display**: Shows re-invocations with indentation and "↻ Critic calls X again" text
- **Header with Collapse Button**: Clean header with close icon to return to summary view
- **Real-time Streaming**: Shows "Processing..." indicator when agents are still running
- **Responsive Styling**: Professional design with borders, backgrounds, and shadows
- **Accessibility**: Full ARIA support, semantic HTML, keyboard navigation

## Requirements Fulfilled

- 2.1: Expanded view shows flat chronological list
- 2.2: Display steps in execution order as flat list
- 2.3: Document flat list structure explicitly in code comments
- 2.4: Display steps in chronological order based on execution sequence
- 2.5: Provide way to collapse back to summary view
- 5.1, 5.2, 5.4: Critic loop visualization with indentation
- 6.1, 6.2, 6.3, 6.4, 6.5: Parallel execution display with grouping
- 11.1, 11.2: Edge type visualization (handoff, critic_loop)

## Design Philosophy - Flat List Structure

The component implements a **FLAT LIST** structure for displaying agent steps (Requirements 2.2, 2.3). This design allows for:

- Simple, intuitive rendering that matches actual execution flow
- Clear chronological order
- Easy comprehension of "what happened when"
- Parallel execution indicated through indentation and labels (not DOM nesting)

**Future Migration**: The code includes explicit comments documenting this decision. If product requirements change, the flat list can be migrated to a tree structure using the relationships already identified by `calculateExecutionOrder()`.

## Usage

```tsx
import { AgentTraceExpanded } from "./AgentTraceExpanded";
import type { TraceGraph } from "../reasoning/fixture";

// Basic usage
function MyComponent() {
  const [traceGraph, setTraceGraph] = useState<TraceGraph>(/* ... */);
  const [streaming, setStreaming] = useState(false);

  const handleCollapse = () => {
    // Return to collapsed summary view
    console.log("Collapsing trace");
  };

  return (
    <AgentTraceExpanded
      traceGraph={traceGraph}
      streaming={streaming}
      onCollapse={handleCollapse}
    />
  );
}
```

## Props

### `AgentTraceExpandedProps`

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `traceGraph` | `TraceGraph` | Yes | Adapted TraceGraph from trace-adapter.ts containing nodes, edges, and groups |
| `streaming` | `boolean` | Yes | Whether agents are still running (shows progress indicators) |
| `onCollapse` | `() => void` | Yes | Callback when user clicks collapse button or presses Escape |

### `TraceGraph` Type

```typescript
type TraceGraph = {
  query_id: string;
  nodes: TraceNode[];
  edges: TraceEdge[];
  groups: TraceGroup[];
};
```

See `../reasoning/fixture.ts` for complete type definitions.

## Visual Design

### Layout Structure

```
┌─────────────────────────────────────────────────────────┐
│ ▾ Agent Reasoning Trace                        [×]      │  ← Header with collapse button
├─────────────────────────────────────────────────────────┤
│  ✓ Distress Check · 0.2s                    HIGH     ⓘ │  ← Regular step
│  ✓ Language Ingress · 0.5s                             │
│  ✓ Planning · 1.2s                          MED      ⓘ │
│                                                          │
│  Parallel execution (3 agents):                         │  ← Group label
│    ✓ Weather Intelligence · 1.1s           HIGH     ⓘ │  ← Indented parallel step
│    ✓ Geospatial · 0.9s                     HIGH     ⓘ │
│    ⚠ Ocean Analytics · 2.1s                DEGRADED  ⓘ │
│                                                          │
│  ✓ Reporting · 1.5s                         HIGH     ⓘ │
│    ↻ Critic calls Reporting again (×2)                 │  ← Critic re-invocation marker
│       ✓ Reporting · 1.3s                    HIGH     ⓘ │  ← Double-indented re-invoked step
│  ✓ Language Egress · 0.3s                              │
│                                                          │
│  ⟳ Processing...                                        │  ← Streaming indicator (when streaming=true)
└─────────────────────────────────────────────────────────┘
```

### Styling

Uses ORCA design system tokens:
- Container: `rounded-lg border border-hairline/60 bg-shelf-1/40 p-2.5 shadow-sm`
- Header: `text-[11px] font-mono font-semibold uppercase tracking-wider text-ink-dim`
- Collapse button: `size-6` with hover states
- List: `flex flex-col gap-1` for vertical spacing
- Group labels: `text-[10px] font-mono font-semibold uppercase` in `ink-dim/70`
- Critic markers: `text-[10px] font-mono text-ink-dim/80` with indentation

## Component Behavior

### Execution Order Calculation

The component uses `calculateExecutionOrder()` to convert the `TraceGraph` into a flat chronological list:

1. Parse edges to build directed graph
2. Identify parallel groups from `TraceGraph.groups`
3. Perform topological sort with depth-first traversal
4. Group parallel agents together
5. Nest critic loops under critique steps

Result: Array of `OrderedStep` objects that can be rendered sequentially.

### Step Rendering

Four types of ordered steps:

1. **Regular Step** (`type: "step"`): Renders `AgentTraceStep` component
2. **Group Start** (`type: "group_start"`): Renders parallel execution label
3. **Group End** (`type: "group_end"`): Adds visual spacing
4. **Critic Reinvoke** (`type: "critic_reinvoke"`): Renders "↻ Critic calls X again" text

### Streaming Behavior

When `streaming={true}`:
- Shows pulsing "Processing..." indicator at bottom
- Last step in list may have `isRunning={true}` prop
- ARIA live region announces "Agents are still working"

### Collapse Interaction

User can collapse via:
- Click close button (×)
- Press Enter or Space on close button (keyboard)
- Press Escape key anywhere in component

## Accessibility

### Semantic HTML

```html
<div role="region" aria-label="Agent execution steps">
  <div> <!-- Header --> </div>
  <ol role="list">
    <li role="listitem"> <!-- Each step --> </li>
    <li role="heading" aria-level={3}> <!-- Group labels --> </li>
  </ol>
</div>
```

### ARIA Support

- `role="region"`: Identifies the trace as a landmark region
- `aria-label="Agent execution steps"`: Describes the region
- `role="list"` and `role="listitem"`: Semantic list structure
- `role="heading"` for group labels with `aria-level={3}`
- `aria-live="polite"` for streaming updates
- `aria-label` on collapse button: "Collapse trace to summary view"

### Keyboard Navigation

- **Tab**: Focus collapse button
- **Enter/Space**: Activate collapse button
- **Escape**: Collapse trace
- Focus management: Returns focus to collapsed view trigger after collapse

### WCAG Compliance

- Color contrast: All colors meet 4.5:1 minimum (WCAG AA)
- Touch targets: 44×44px minimum for interactive elements
- Screen reader: Full support with descriptive labels

## Integration with AgentTraceUI

The `AgentTraceExpanded` component is used within `AgentTraceUI` container:

```tsx
// In AgentTraceUI.tsx
{state.isExpanded && state.traceGraph && (
  <motion.div
    initial={{ height: 0, opacity: 0 }}
    animate={{ height: "auto", opacity: 1 }}
    exit={{ height: 0, opacity: 0 }}
    transition={{ duration: 0.2, ease: "easeOut" }}
  >
    <AgentTraceExpanded
      traceGraph={state.traceGraph}
      streaming={streaming}
      onCollapse={handleCollapse}
    />
  </motion.div>
)}
```

## Performance Considerations

### Memoization

The component uses `React.useMemo` to memoize the execution order calculation:

```typescript
const orderedSteps = React.useMemo(() => {
  return calculateExecutionOrder(traceGraph);
}, [traceGraph]);
```

This prevents recalculation on every render unless `traceGraph` changes.

### Incremental Updates

For streaming traces:
- Only new steps trigger re-renders
- Completed steps use `React.memo()` (in `AgentTraceStep`)
- No full list re-render on each SSE event

### Virtualization

For traces with 10+ steps, consider adding `@tanstack/react-virtual`:
- Renders only visible steps
- Improves performance for long traces
- Maintains smooth scrolling

See design.md "Performance Optimization" section for implementation details.

## Testing

Unit tests should verify (task 6.2):
- Steps render in correct chronological order
- Parallel agents grouped with correct indentation
- Critic loop re-invocations indented correctly
- Confidence badges display only for completed agents
- Missing fields handled gracefully (no crashes)

Example test:

```typescript
describe('AgentTraceExpanded', () => {
  it('renders parallel agents with indentation', () => {
    const mockTrace: TraceGraph = {
      query_id: "test",
      nodes: [
        { id: "geo", agent_name: "Geospatial", status: "ok", ... },
        { id: "ocean", agent_name: "Ocean", status: "ok", ... }
      ],
      edges: [],
      groups: [{
        id: "g1",
        node_ids: ["geo", "ocean"],
        reason: "parallel_fanout"
      }]
    };
    
    render(<AgentTraceExpanded traceGraph={mockTrace} streaming={false} onCollapse={() => {}} />);
    
    expect(screen.getByText("Parallel execution (2 agents):")).toBeInTheDocument();
    expect(screen.getByText("Geospatial")).toHaveClass("pl-4");
  });
});
```

## Error Handling

The component gracefully handles:

- **Empty trace**: Shows "No agent execution data available"
- **Missing nodes**: Skips rendering (no crash)
- **Invalid edges**: `calculateExecutionOrder()` handles gracefully
- **Missing groups**: Renders as regular steps without grouping

## Related Components

- **AgentTraceStep**: Individual step rendering (see `AgentTraceStep.README.md`)
- **AgentTraceCollapsed**: Summary view (collapsed state)
- **AgentTraceUI**: Container that manages expanded/collapsed state
- **calculateExecutionOrder**: Utility for ordering steps (see `calculateExecutionOrder.README.md`)

## Examples

See `AgentTraceExpanded.example.tsx` for complete examples:
- Simple linear trace
- Parallel execution trace
- Critic loop trace
- Streaming trace
- Complex trace with all features
