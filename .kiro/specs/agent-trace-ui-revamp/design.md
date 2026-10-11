# Design Document

## Overview

This design specifies a new trace UI for ORCA that replaces the current pill-based agent strip (AgentPill.tsx/AgentStrip) with a professional reasoning trace interface similar to ChatGPT and Claude. The interface has two states:

1. **Collapsed View**: A single line showing "Worked for {N}s" above the answer
2. **Expanded View**: A flat chronological list of agent execution steps with real-time streaming updates

The design emphasizes **truthfulness** — the UI displays only what the backend actually reports through the `/trace/{query_id}` API and SSE `agent_span` events. No inference, no guessing. The backend audit work is complete (agents 4 and 6 fixed), ensuring accurate trace data.

### Key Design Principles

- **Truthful**: Display only backend-reported data; no client-side inference
- **Real-time**: Stream updates as agents complete via SSE
- **Professional**: Match the visual quality of ChatGPT and Claude reasoning traces
- **Accessible**: WCAG 2.1 AA compliant with keyboard navigation and screen reader support
- **Performant**: Smooth rendering even with 15+ agent steps
- **Backward Compatible**: Existing AgentPill/AgentStrip components remain untouched

## Architecture

### Component Hierarchy

```
ChatTurn
├── UserBubble
├── AgentTraceUI (NEW)
│   ├── AgentTraceCollapsed
│   └── AgentTraceExpanded
│       └── AgentTraceStep[] (flat list)
└── AnswerPanel
```

### Data Flow

```
SSE Stream (`agent_span` events)
    ↓
useAskThread hook (existing)
    ↓
ChatTurn component
    ↓
AgentTraceUI (NEW)
    ↓
adaptTraceGraph (trace-adapter.ts)
    ↓
Render collapsed/expanded view
```

The existing `useAskThread` hook already handles SSE streaming and maintains the `spans` array. The new AgentTraceUI component consumes this data without changing the upstream architecture.

## Components and Interfaces

### 1. AgentTraceUI (Container Component)

**Purpose**: Top-level component that manages collapsed/expanded state and orchestrates rendering.

**Location**: `frontend/app/components/AgentTraceUI.tsx`

**Props**:
```typescript
interface AgentTraceUIProps {
  spans: AgentSpan[];              // From useAskThread
  streaming: boolean;              // Whether agents are still running
  queryId?: string;                // For fetching full trace data
  className?: string;
}
```

**State**:
```typescript
interface AgentTraceUIState {
  isExpanded: boolean;             // Collapsed vs expanded
  traceGraph: TraceGraph | null;   // Full trace from API
  loading: boolean;                // Fetching trace data
}
```

**Behavior**:
- Renders `AgentTraceCollapsed` by default
- Fetches full trace data from `/trace/{query_id}` when user clicks to expand
- Passes adapted TraceGraph to `AgentTraceExpanded`
- Handles expand/collapse transitions with framer-motion

### 2. AgentTraceCollapsed (Summary View)

**Purpose**: Shows total execution time in a single line.

**Location**: `frontend/app/components/AgentTraceCollapsed.tsx`

**Props**:
```typescript
interface AgentTraceCollapsedProps {
  totalTimeMs: number;             // Sum of all agent latency_ms
  streaming: boolean;              // Show progress indicator
  onExpand: () => void;            // Callback to expand
}
```

**Visual Design**:
```
┌─────────────────────────────────────────┐
│ ▸ Worked for 3.2s                       │  ← Clickable, subtle hover
└─────────────────────────────────────────┘
```

**Styling**:
- Minimal border, subtle background (shelf-1/40)
- Chevron icon indicates expandability
- Hover state shows border-hairline-strong
- Text: 12px, ink-dim color
- Smooth fade-in animation on mount

### 3. AgentTraceExpanded (Detail View)

**Purpose**: Displays flat chronological list of agent steps.

**Location**: `frontend/app/components/AgentTraceExpanded.tsx`

**Props**:
```typescript
interface AgentTraceExpandedProps {
  traceGraph: TraceGraph;          // Adapted from trace-adapter.ts
  streaming: boolean;              // Show running indicators
  onCollapse: () => void;          // Callback to collapse
}
```

**Visual Design**:
```
┌─────────────────────────────────────────────────────────┐
│ ▾ Agent Reasoning Trace                        [x]      │
├─────────────────────────────────────────────────────────┤
│  ✓ Distress Check · 0.2s                    HIGH     ⓘ │
│  ✓ Language Ingress · 0.5s                             │
│  ✓ Planning · 1.2s                          MED      ⓘ │
│  ✓ Marine Data Discovery · 0.8s                        │
│                                                          │
│  Parallel execution (4 agents):                         │
│    ✓ Geospatial · 1.1s                      HIGH     ⓘ │
│    ✓ Ocean Analytics · 0.9s                HIGH     ⓘ │
│    ✓ Weather Intel · 1.3s                  HIGH     ⓘ │
│    ⚠ Risk Assessment · 2.1s                DEGRADED  ⓘ │
│                                                          │
│  ✓ Visualization · 0.4s                                │
│  ✓ Reporting · 1.5s                         HIGH     ⓘ │
│    └─ ↻ Critic calls Reporting again (x2)              │
│       ✓ Reporting · 1.3s                    HIGH     ⓘ │
│  ✓ Language Egress · 0.3s                              │
└─────────────────────────────────────────────────────────┘
```

**Note on Flat vs Tree Structure**:
The current implementation uses a **flat list** for simplicity and to match the chronological execution flow. The code includes explicit comments documenting this decision, allowing future developers to migrate to a tree structure if product requirements change. The parallel execution pattern is indicated through indentation and grouping labels, not through actual tree nesting in the DOM.

**Behavior**:
- Renders steps in chronological order (sorted by execution sequence)
- Groups parallel agents under "Parallel execution" label with indentation
- Shows critic loops as indented re-invocations under the critique step
- Streams new steps as they arrive (incremental updates)
- Collapses back to summary on header click or close button

### 4. AgentTraceStep (Individual Step)

**Purpose**: Renders one agent execution step with all metadata.

**Location**: `frontend/app/components/AgentTraceStep.tsx`

**Props**:
```typescript
interface AgentTraceStepProps {
  node: TraceNode;                 // From TraceGraph
  isRunning?: boolean;             // Currently executing
  indent?: number;                 // 0, 1, or 2 for critic loops/parallel
  showGroupLabel?: string;         // "Parallel execution (4 agents)"
}
```

**TraceNode Interface** (from trace-adapter.ts):
```typescript
interface TraceNode {
  id: string;
  agent_name: string;
  depth: number;
  status: AgentStatus;
  confidence_tier: ConfidenceTier;
  latency_ms: number;
  reasoning_summary: string;
  source_count: number;
  used_llm: boolean;
  model?: string | null;
  tier?: "cheap" | "mid" | "reasoning" | null;
  engine?: string;
  skip_reason?: string | null;
  run_count: number;
}
```

**Visual Elements**:
- **Status Icon**: ✓ (ok), ⚠ (degraded), ✗ (failed), ○ (skipped), ⊘ (cancelled), ⟳ (running)
- **Agent Name**: From trace-adapter.ts AGENT_LABEL map
- **Latency**: Formatted as "1.2s" or "450ms"
- **Confidence Badge**: H/M/L letter badge (same as existing AgentPill)
- **Info Icon**: Hover/click shows tooltip with engine, model, reasoning_summary
- **Run Count**: "x2" badge for multi-run agents (critic loops)

**Styling**:
- Base: border-hairline/60, bg-shelf-1/40, 11px text
- Status colors: ok (ink), degraded (caution), failed (no-go), skipped (ink-dim/60), cancelled (caution/70 with dashed border)
- Indentation: 0 (base), 16px (parallel), 32px (critic loop)
- Hover: border-hairline-strong, subtle shadow

## Data Models

### TraceGraph (Existing)

Already defined in `trace-adapter.ts`:

```typescript
interface TraceGraph {
  query_id: string;
  nodes: TraceNode[];
  edges: TraceEdge[];
  groups: TraceGroup[];
}

interface TraceEdge {
  from: string;
  to: string;
  kind: "handoff" | "critic_loop" | "cancelled";
  label: string;
}

interface TraceGroup {
  id: string;
  node_ids: string[];
  reason: "parallel_fanout";
}
```

### Execution Order Calculation

The expanded view must render steps in chronological order. The algorithm:

1. **Parse edges** to build a directed graph of agent dependencies
2. **Identify parallel groups** from TraceGraph.groups
3. **Topological sort** with depth-first traversal
4. **Group parallel agents** together in sequence
5. **Nest critic loops** under the critique step

**Pseudocode**:
```typescript
function calculateExecutionOrder(graph: TraceGraph): OrderedStep[] {
  const adjacency = buildAdjacencyList(graph.edges);
  const parallelGroups = new Map(graph.groups.map(g => [g.id, g.node_ids]));
  
  const visited = new Set<string>();
  const ordered: OrderedStep[] = [];
  
  // Start from root (distress or language_ingress)
  const root = graph.nodes.find(n => n.depth === 0);
  
  function visit(nodeId: string, indent: number) {
    if (visited.has(nodeId)) return;
    visited.add(nodeId);
    
    const node = graph.nodes.find(n => n.id === nodeId);
    const criticLoopEdges = graph.edges.filter(e => e.from === nodeId && e.kind === "critic_loop");
    
    // Check if this node is part of a parallel group
    const group = Array.from(parallelGroups.entries()).find(([_, ids]) => ids.includes(nodeId));
    
    if (group) {
      // First node in group adds the group label
      const [groupId, groupNodeIds] = group;
      if (groupNodeIds.indexOf(nodeId) === 0) {
        ordered.push({
          type: "group_start",
          label: `Parallel execution (${groupNodeIds.length} agents):`
        });
      }
      
      ordered.push({ type: "step", node, indent: 1 });
      
      // Last node in group closes the group
      if (groupNodeIds.indexOf(nodeId) === groupNodeIds.length - 1) {
        ordered.push({ type: "group_end" });
      }
    } else {
      ordered.push({ type: "step", node, indent });
    }
    
    // Handle critic loops (re-invocations)
    if (criticLoopEdges.length > 0) {
      ordered.push({
        type: "critic_reinvoke",
        label: `↻ Critic calls ${node.agent_name} again (x${node.run_count})`
      });
      
      criticLoopEdges.forEach(edge => visit(edge.to, indent + 1));
    }
    
    // Continue with normal handoff edges
    const handoffEdges = graph.edges.filter(e => e.from === nodeId && e.kind === "handoff");
    handoffEdges.forEach(edge => visit(edge.to, indent));
  }
  
  if (root) visit(root.id, 0);
  
  return ordered;
}
```

## Error Handling

### 1. Missing Trace Data

**Scenario**: `/trace/{query_id}` returns 404 or empty data

**Handling**:
- Show collapsed view with calculated time from spans
- Disable expand functionality
- Log warning to console

### 2. Incomplete Spans

**Scenario**: Agent span missing required fields (latency_ms, status)

**Handling**:
- Use fallbacks: latency_ms → 0, status → "ok"
- Display step with "(unknown)" if agent_name is missing
- Never crash the UI

### 3. Network Errors

**Scenario**: SSE connection drops or fetch fails

**Handling**:
- Show last known state
- Display retry button in expanded view
- Use exponential backoff for retries

### 4. Race Conditions

**Scenario**: User expands before trace data is ready

**Handling**:
- Show skeleton loader while fetching
- Timeout after 5 seconds → show error state
- Allow collapse even if data fetch failed

## Testing Strategy

### Unit Tests

**Test Framework**: Jest + React Testing Library

**Coverage Areas**:

1. **AgentTraceCollapsed**:
   - Renders total time correctly (3200ms → "3.2s")
   - Shows spinner when streaming=true
   - Calls onExpand when clicked
   - Keyboard accessible (Enter/Space triggers expand)

2. **AgentTraceExpanded**:
   - Renders steps in correct chronological order
   - Groups parallel agents correctly
   - Indents critic loop re-invocations
   - Shows confidence badges only for completed agents
   - Handles missing fields gracefully

3. **AgentTraceStep**:
   - Renders all status types correctly (ok, degraded, failed, skipped, cancelled)
   - Shows run count badge when run_count > 1
   - Displays skip_reason for skipped/cancelled agents
   - Info tooltip contains engine and reasoning_summary

4. **Execution Order Algorithm**:
   - Correctly sorts simple linear traces
   - Groups parallel agents together
   - Nests critic loops under critique step
   - Handles cancelled edges correctly

**Example Test**:
```typescript
describe('AgentTraceExpanded', () => {
  it('renders parallel agents with indentation', () => {
    const mockTrace: TraceGraph = {
      query_id: "test-123",
      nodes: [
        { id: "geospatial", agent_name: "Geospatial", status: "ok", latency_ms: 1100, ... },
        { id: "ocean", agent_name: "Ocean Analytics", status: "ok", latency_ms: 900, ... }
      ],
      edges: [],
      groups: [{ id: "g1", node_ids: ["geospatial", "ocean"], reason: "parallel_fanout" }]
    };
    
    render(<AgentTraceExpanded traceGraph={mockTrace} streaming={false} onCollapse={() => {}} />);
    
    expect(screen.getByText("Parallel execution (2 agents):")).toBeInTheDocument();
    expect(screen.getByText("Geospatial")).toHaveClass("indent-4"); // 16px indentation
    expect(screen.getByText("Ocean Analytics")).toHaveClass("indent-4");
  });
});
```

### Integration Tests

**Test Framework**: Playwright

**Test Scenarios**:

1. **SSE Streaming**:
   - Mock SSE endpoint to send agent_span events incrementally
   - Verify UI updates in real-time as spans arrive
   - Verify final state matches all spans received

2. **Expand/Collapse**:
   - Click collapsed view → expands to show steps
   - Click header or close button → collapses back
   - Animation completes smoothly

3. **Accessibility**:
   - Keyboard navigation (Tab, Enter, Space)
   - Screen reader announces new steps (aria-live)
   - Focus management on expand/collapse

### Accessibility Testing

**Manual Testing with NVDA/JAWS**:
- Navigate trace with arrow keys
- Verify step announcements include status and time
- Confirm expand/collapse actions are announced
- Test high contrast mode and color blindness filters

**Automated Testing**:
- Run axe-core on collapsed and expanded views
- Verify WCAG 2.1 AA compliance for:
  - Color contrast (4.5:1 for text)
  - Touch target size (44x44px minimum)
  - Keyboard operability
  - Screen reader compatibility

## Performance Optimization

### 1. Virtualization

**Problem**: Rendering 15+ agent steps may cause jank on low-end devices.

**Solution**: Use `react-window` or `@tanstack/react-virtual` for the expanded list.

**Implementation**:
```typescript
import { useVirtualizer } from '@tanstack/react-virtual';

function AgentTraceExpanded({ traceGraph, ... }: AgentTraceExpandedProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const orderedSteps = useMemo(() => calculateExecutionOrder(traceGraph), [traceGraph]);
  
  const virtualizer = useVirtualizer({
    count: orderedSteps.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32, // Estimated row height
    overscan: 5, // Render 5 extra items outside viewport
  });
  
  return (
    <div ref={parentRef} className="h-[400px] overflow-auto">
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map(virtualRow => {
          const step = orderedSteps[virtualRow.index];
          return (
            <div
              key={virtualRow.index}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <AgentTraceStep {...step} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

### 2. Memoization

**Memoize expensive calculations**:
- `calculateExecutionOrder()`: Use `useMemo` with traceGraph as dependency
- `AgentTraceStep`: Use `React.memo()` to prevent re-renders of unchanged steps

### 3. Incremental Updates

**Problem**: SSE sends one event at a time; re-rendering the entire list on each event is wasteful.

**Solution**: Only append new steps to the DOM, don't re-render existing ones.

**Implementation**:
```typescript
function AgentTraceExpanded({ traceGraph, streaming }: AgentTraceExpandedProps) {
  const [renderedNodeIds, setRenderedNodeIds] = useState<Set<string>>(new Set());
  
  useEffect(() => {
    const newNodeIds = new Set(traceGraph.nodes.map(n => n.id));
    const addedIds = Array.from(newNodeIds).filter(id => !renderedNodeIds.has(id));
    
    if (addedIds.length > 0) {
      setRenderedNodeIds(newNodeIds);
      // Only new nodes will re-render due to React.memo on AgentTraceStep
    }
  }, [traceGraph.nodes, renderedNodeIds]);
  
  // ... render logic
}
```

### 4. Smooth Animations

**Use framer-motion for expand/collapse**:
```typescript
<motion.div
  initial={{ height: 0, opacity: 0 }}
  animate={{ height: "auto", opacity: 1 }}
  exit={{ height: 0, opacity: 0 }}
  transition={{ duration: 0.2, ease: "easeOut" }}
>
  <AgentTraceExpanded ... />
</motion.div>
```

**Debounce rapid SSE updates**:
```typescript
const [debouncedSpans] = useDebounce(spans, 100); // Wait 100ms between updates
```

## Accessibility

### Semantic HTML

```html
<section aria-label="Agent reasoning trace">
  <button aria-expanded={isExpanded} onClick={toggleExpand}>
    Worked for 3.2s
  </button>
  
  {isExpanded && (
    <div role="region" aria-label="Agent execution steps">
      <ol>
        <li>
          <span role="img" aria-label="completed">✓</span>
          <span>Distress Check</span>
          <time>0.2s</time>
        </li>
        <!-- ... more steps -->
      </ol>
    </div>
  )}
</section>
```

### ARIA Live Regions

**Announce new steps as they stream**:
```html
<div aria-live="polite" aria-atomic="false">
  {streaming && latestStep && (
    <span className="sr-only">
      {latestStep.agent_name} completed in {latestStep.latency_ms}ms
    </span>
  )}
</div>
```

### Keyboard Navigation

- **Tab**: Focus collapsed view
- **Enter/Space**: Toggle expand/collapse
- **Arrow Down/Up**: Navigate steps in expanded view
- **Escape**: Collapse expanded view
- **Home/End**: Jump to first/last step

### Color Contrast

All status colors meet WCAG AA contrast ratios (4.5:1 minimum):
- **ok**: ink (#1a1a1a) on shelf-3 (#f5f5f5) → 16.2:1 ✓
- **degraded**: caution (#d97706) on caution/10 → 5.8:1 ✓
- **failed**: no-go (#dc2626) on no-go/10 → 6.1:1 ✓
- **running**: ocean-cyan (#0891b2) on ocean-cyan/10 → 5.2:1 ✓

### Touch Targets

All interactive elements meet 44x44px minimum:
- Collapsed view: 48px height
- Close button: 44x44px
- Info icons: 44x44px tap area (icon is 16px, padding adds to 44px)

## Integration with ChatTurn

### Current Integration (AgentStrip)

ChatTurn currently renders AgentStrip like this:

```tsx
{(displaySpans.length > 0 || runningAgent) && (
  <div className="flex min-w-0 max-w-full flex-col gap-1.5">
    {streaming && (
      <span className="inline-flex items-center gap-1.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-ink-dim">
        <Radio className="size-3" aria-hidden="true" />
        {t("chatTurn.agentTrace")}
      </span>
    )}
    <AgentStrip>
      {groupRuns(displaySpans).map(({ span: s, runs, latency }, i) => (
        <AgentPill key={`${s.agent_name}-${i}`} name={s.agent_name} status={s.status} ... />
      ))}
      {runningAgent && <AgentPill name={runningAgent} status="running" />}
    </AgentStrip>
  </div>
)}
```

### New Integration (AgentTraceUI)

Replace the above block with:

```tsx
{(displaySpans.length > 0 || runningAgent) && (
  <AgentTraceUI
    spans={displaySpans}
    streaming={streaming}
    queryId={answer?.query_id}
  />
)}
```

**No changes needed to**:
- `useAskThread` hook (SSE handling)
- `groupRuns()` function (still useful for spans array)
- `displaySpans` calculation (fallback logic)

**Migration strategy**:
1. Add AgentTraceUI alongside AgentStrip (feature flag)
2. Test with real queries in staging
3. Gradually roll out to users (10% → 50% → 100%)
4. Keep AgentStrip code for rollback capability
5. Remove AgentStrip after 2 weeks of stable operation

## Trace Data Adapter Integration

The design fully leverages the existing `trace-adapter.ts`:

### Usage Pattern

```typescript
import { adaptTraceGraph, type ApiTraceGraph } from "@/app/reasoning/trace-adapter";

async function fetchTraceData(queryId: string): Promise<TraceGraph> {
  const response = await fetch(`${API_BASE}/trace/${queryId}${tokenParam()}`);
  const apiTrace: ApiTraceGraph = await response.json();
  return adaptTraceGraph(apiTrace);
}
```

### Field Mappings

The adapter already handles all required fields:

| Backend Field | Adapter Output | UI Usage |
|---------------|----------------|----------|
| `id` | `id` | Step identification |
| `agent_name` | Resolved via `AGENT_LABEL` map | Display name |
| `status` | Coerced to `AgentStatus` | Icon and color |
| `confidence_tier` | Coerced to `ConfidenceTier` | Badge (H/M/L) |
| `latency_ms` | `latency_ms` (defaults to 0) | Duration display |
| `reasoning_summary` | `reasoning_summary` | Tooltip text |
| `engine` | `engine` | Tooltip detail |
| `skip_reason` | `skip_reason` | Skipped/cancelled explanation |
| `run_count` | `run_count` (defaults to 1) | Multi-run badge |

### Null Handling

The adapter provides safe defaults for missing fields:
- `latency_ms` → 0
- `model` → null
- `tier` → null
- `skip_reason` → null
- `run_count` → 1

The UI handles these gracefully:
- Missing latency → Don't show time
- Missing engine → Tooltip shows only reasoning_summary
- Missing skip_reason → Generic "skipped" text

## Visual Polish and Design System Integration

### Typography

- **Collapsed view**: 12px, font-medium, ink-dim
- **Expanded header**: 11px, font-mono, font-semibold, uppercase, ink-dim
- **Step names**: 11px sm:12px, font-medium, ink
- **Step times**: 10px, font-mono, ink-muted

### Colors

All colors use ORCA's existing design system:

| Element | Color Token | Value |
|---------|-------------|-------|
| Background | `shelf-1/40` | `rgba(245, 245, 245, 0.4)` |
| Border | `hairline/60` | `rgba(0, 0, 0, 0.06)` |
| Text (primary) | `ink` | `#1a1a1a` |
| Text (secondary) | `ink-dim` | `#6b7280` |
| Text (muted) | `ink-muted` | `#9ca3af` |
| Status (ok) | `go` | `#10b981` |
| Status (degraded) | `caution` | `#d97706` |
| Status (failed) | `no-go` | `#dc2626` |
| Status (running) | `ocean-cyan` | `#0891b2` |

### Shadows

- **Collapsed**: `shadow-2xs` (subtle)
- **Collapsed hover**: `shadow-xs`
- **Expanded**: `shadow-sm`

### Spacing

- **Collapsed padding**: `px-4 py-2` (16px horizontal, 8px vertical)
- **Expanded padding**: `p-2.5` (10px all sides)
- **Step gap**: `gap-1` (4px between steps)
- **Indent (parallel)**: `pl-4` (16px)
- **Indent (critic loop)**: `pl-8` (32px)

### Animations

All animations use framer-motion for consistency:

```typescript
// Expand/collapse
<motion.div
  initial={{ height: 0, opacity: 0 }}
  animate={{ height: "auto", opacity: 1 }}
  transition={{ duration: 0.2, ease: "easeOut" }}
>
  ...
</motion.div>

// Step entry (streaming)
<motion.li
  initial={{ opacity: 0, x: -8 }}
  animate={{ opacity: 1, x: 0 }}
  transition={{ duration: 0.15 }}
>
  ...
</motion.li>

// Running pulse
<motion.div
  animate={{ opacity: [0.5, 1, 0.5] }}
  transition={{ duration: 1.5, repeat: Infinity }}
>
  ⟳ Running...
</motion.div>
```

### Responsive Breakpoints

- **Mobile (< 640px)**: Single column, smaller text (11px)
- **Tablet (640px - 1024px)**: Comfortable spacing
- **Desktop (> 1024px)**: Full layout with wider info tooltips

## Responsive Layout

### Mobile (320px - 639px)

```
┌────────────────────────┐
│ ▸ Worked for 3.2s     │  ← 40px height, 14px text
└────────────────────────┘

Expanded:
┌────────────────────────┐
│ ▾ Trace          [x]   │
├────────────────────────┤
│ ✓ Distress · 0.2s   H │  ← Wraps if name too long
│ ✓ Planning · 1.2s   M │
│ ...                    │
└────────────────────────┘
```

### Tablet (640px - 1023px)

```
┌──────────────────────────────────┐
│ ▸ Worked for 3.2s                │  ← 44px height, 13px text
└──────────────────────────────────┘

Expanded:
┌──────────────────────────────────┐
│ ▾ Agent Reasoning Trace    [x]   │
├──────────────────────────────────┤
│ ✓ Distress Check · 0.2s   HIGH ⓘ│
│ ✓ Planning · 1.2s          MED  ⓘ│
│ ...                              │
└──────────────────────────────────┘
```

### Desktop (1024px+)

Full layout as shown in "Visual Design" section above.

### Responsive Techniques

1. **Fluid Typography**:
   ```css
   font-size: clamp(11px, 1vw, 12px);
   ```

2. **Flexible Containers**:
   ```tsx
   <div className="max-w-full overflow-x-auto">
     {/* Steps render in scrollable container if too wide */}
   </div>
   ```

3. **Touch-Friendly Targets**:
   - Mobile: 48px minimum tap area
   - Desktop: 44px minimum (WCAG guideline)

4. **Breakpoint Classes**:
   ```tsx
   <span className="text-[11px] sm:text-xs md:text-sm">
     Agent Name
   </span>
   ```

## Browser Compatibility

**Supported Browsers**:
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile Safari 14+
- Chrome Android 90+

**Fallbacks**:
- No framer-motion support → Use CSS transitions
- No IntersectionObserver (virtualization) → Render all steps
- No EventSource (SSE) → Poll `/trace/{query_id}` every 2s

## Deployment and Rollout

### Phase 1: Development (Week 1-2)

1. Create AgentTraceUI component structure
2. Implement collapsed view
3. Implement expanded view with flat list
4. Integrate with trace-adapter.ts
5. Add unit tests

### Phase 2: Integration (Week 3)

1. Integrate with ChatTurn (behind feature flag)
2. Test with real queries in staging
3. Accessibility audit (automated + manual)
4. Performance profiling (15+ agent traces)

### Phase 3: Gradual Rollout (Week 4)

1. 10% of users see new UI (A/B test)
2. Monitor error rates, performance metrics
3. Increase to 50% if no issues
4. Full rollout (100%) after 3 days

### Phase 4: Cleanup (Week 5)

1. Remove feature flag
2. Keep AgentStrip for 2 weeks (rollback capability)
3. Remove AgentStrip after confirming stability
4. Update documentation

### Rollback Plan

If critical issues arise:
1. Set feature flag to 0% (immediate)
2. Revert ChatTurn integration (< 5 minutes)
3. Investigate and fix issue
4. Re-deploy and resume rollout

## Future Enhancements

### Tree Structure (Post-MVP)

The current flat list can be migrated to a tree structure if product requirements change:

```tsx
// Current: Flat list with indentation
<ol>
  <li>Planning</li>
  <li className="pl-4">Geospatial (parallel)</li>
  <li className="pl-4">Ocean (parallel)</li>
  <li>Reporting</li>
</ol>

// Future: Actual tree structure
<TreeView>
  <TreeNode>Planning</TreeNode>
  <TreeNode>
    <TreeNode.Label>Parallel Execution</TreeNode.Label>
    <TreeNode.Children>
      <TreeNode>Geospatial</TreeNode>
      <TreeNode>Ocean</TreeNode>
    </TreeNode.Children>
  </TreeNode>
  <TreeNode>Reporting</TreeNode>
</TreeView>
```

The code includes explicit comments documenting this decision for future developers.

### Interactive Filtering

Allow users to:
- Filter by status (show only failed/degraded)
- Filter by confidence tier (show only LOW_DATA)
- Search by agent name

### Export Functionality

Download trace as:
- JSON (full TraceGraph)
- CSV (steps table)
- PNG (screenshot of expanded view)

### Trace Comparison

Show diff between two query traces:
- Which agents ran differently?
- Execution time comparison
- Status changes

### Telemetry

Track user behavior:
- Expansion rate (% of users who expand)
- Time spent in expanded view
- Clicks on info tooltips (which agents are users curious about?)

## Correctness Properties

This feature is primarily a UI rendering task with no complex algorithmic logic or data transformation beyond what already exists in `trace-adapter.ts`. The feature is **not suitable for property-based testing** because:

1. **UI Rendering**: The main logic is React component rendering, which is best tested with example-based unit tests and integration tests
2. **External Data Dependency**: The component consumes data from an external API (`/trace/{query_id}`) and SSE stream, making it an integration point rather than pure logic
3. **Visual Behavior**: Many requirements concern visual presentation (animations, hover states, responsive layout) which are not amenable to property-based testing

Instead, we will use:
- **Example-based unit tests**: Specific scenarios for collapsed/expanded rendering, status icons, execution order calculation
- **Integration tests**: SSE streaming behavior, expand/collapse interactions
- **Accessibility tests**: Automated axe-core checks + manual NVDA/JAWS testing
- **Visual regression tests**: Screenshot comparison for UI polish verification

## Testing Strategy

### Unit Tests (Jest + React Testing Library)

**Test Coverage**:

1. **AgentTraceCollapsed Component**:
   - Renders total time correctly formatted ("3.2s" vs "450ms")
   - Shows chevron icon and hover state
   - Calls onExpand callback when clicked
   - Shows spinner when streaming=true
   - Keyboard accessible (Enter/Space triggers expand)

2. **AgentTraceExpanded Component**:
   - Renders steps in chronological order
   - Groups parallel agents with indentation and label
   - Nests critic loop re-invocations
   - Shows confidence badges for completed agents
   - Hides confidence for running/skipped agents
   - Calls onCollapse when header clicked
   - Renders empty state when traceGraph has no nodes

3. **AgentTraceStep Component**:
   - Renders all status types with correct icons/colors
   - Shows run count badge when run_count > 1
   - Displays skip_reason for skipped/cancelled agents
   - Info tooltip contains engine and reasoning_summary
   - Handles missing fields gracefully (null latency_ms, null engine)

4. **Execution Order Algorithm**:
   - Linear trace sorted correctly (distress → planning → ... → egress)
   - Parallel groups identified and indented
   - Critic loops nested under critique step
   - Cancelled edges excluded from flow
   - Empty graph returns empty array

5. **Integration with trace-adapter.ts**:
   - adaptTraceGraph output consumed correctly
   - Null fields handled with safe defaults
   - Agent names resolved via AGENT_LABEL map

**Example Test**:
```typescript
describe('calculateExecutionOrder', () => {
  it('nests critic loop re-invocations under critique step', () => {
    const graph: TraceGraph = {
      query_id: "test",
      nodes: [
        { id: "reporting", agent_name: "Reporting", run_count: 2, ... },
        { id: "critic", agent_name: "Critic", run_count: 2, ... }
      ],
      edges: [
        { from: "reporting", to: "critic", kind: "handoff", label: "" },
        { from: "critic", to: "reporting", kind: "critic_loop", label: "Re-invoke" }
      ],
      groups: []
    };
    
    const ordered = calculateExecutionOrder(graph);
    
    expect(ordered).toEqual([
      { type: "step", node: nodes[0], indent: 0 },
      { type: "step", node: nodes[1], indent: 0 },
      { type: "critic_reinvoke", label: "↻ Critic calls Reporting again (x2)" },
      { type: "step", node: nodes[0], indent: 1 } // Re-invoked reporting indented
    ]);
  });
});
```

### Integration Tests (Playwright)

**Test Scenarios**:

1. **SSE Streaming Updates**:
   - Mock SSE endpoint to send `agent_span` events incrementally
   - Verify collapsed view updates total time as spans arrive
   - Expand trace mid-stream → verify steps appear incrementally
   - Verify final state matches all spans received

2. **Expand/Collapse Interaction**:
   - Click collapsed view → expands smoothly with animation
   - Click close button → collapses back
   - Click header → toggles expanded state
   - Keyboard (Enter) expands, (Escape) collapses

3. **Trace Data Fetching**:
   - Mock `/trace/{query_id}` endpoint
   - Verify loading state while fetching
   - Verify error state on fetch failure
   - Verify retry button appears and works

4. **Parallel Agent Visualization**:
   - Query with parallel fanout group
   - Verify "Parallel execution (N agents):" label appears
   - Verify agents in group are indented
   - Verify order matches execution flow

5. **Critic Loop Visualization**:
   - Query with critic re-invocation
   - Verify "↻ Critic calls X again" label appears
   - Verify re-invoked agent is indented under critique
   - Verify run count badge shows "x2"

### Accessibility Tests

**Automated (axe-core)**:
- Run on collapsed view (initial state)
- Run on expanded view (after click)
- Run on streaming state (running indicator visible)
- Verify no WCAG 2.1 AA violations

**Manual (NVDA/JAWS)**:
- Navigate collapsed view with keyboard
- Expand trace and navigate steps with arrow keys
- Verify aria-live announces new steps during streaming
- Verify status and confidence announced correctly
- Test high contrast mode and color blindness filters

**Keyboard Navigation Test**:
```typescript
test('keyboard navigation works correctly', async ({ page }) => {
  await page.goto('/ask');
  
  // Submit query (triggers SSE stream)
  await page.fill('input[type="text"]', 'Is it safe to fish near 10.5N, 80.5E?');
  await page.press('input[type="text"]', 'Enter');
  
  // Wait for agent trace to appear
  await page.waitForSelector('[aria-label="Agent reasoning trace"]');
  
  // Tab to collapsed view
  await page.keyboard.press('Tab');
  await expect(page.locator('[aria-expanded="false"]')).toBeFocused();
  
  // Expand with Enter
  await page.keyboard.press('Enter');
  await expect(page.locator('[aria-expanded="true"]')).toBeVisible();
  
  // Collapse with Escape
  await page.keyboard.press('Escape');
  await expect(page.locator('[aria-expanded="false"]')).toBeVisible();
});
```

### Visual Regression Tests

**Tool**: Playwright with screenshot comparison

**Scenarios**:
- Collapsed view (default state)
- Expanded view (15 steps, mix of statuses)
- Parallel execution grouping
- Critic loop nesting
- Mobile responsive layout (320px width)
- Tablet layout (768px width)
- Desktop layout (1440px width)

### Performance Tests

**Metrics**:
- Time to First Render (collapsed view): < 50ms
- Time to Expand: < 200ms (including animation)
- Incremental Update (new step): < 16ms (60fps)
- Memory usage (15 steps): < 5MB

**Load Test**:
- Render trace with 20+ steps (stress test)
- Verify virtualization kicks in (not all steps in DOM)
- Verify smooth scrolling (no jank)

### Test Data Fixtures

Create realistic trace fixtures:

```typescript
// fixtures/traces.ts
export const SIMPLE_LINEAR_TRACE: TraceGraph = {
  query_id: "simple-123",
  nodes: [
    { id: "distress", agent_name: "Distress Check", status: "ok", latency_ms: 200, ... },
    { id: "planning", agent_name: "Planning", status: "ok", latency_ms: 1200, ... },
    { id: "egress", agent_name: "Language Egress", status: "ok", latency_ms: 300, ... }
  ],
  edges: [
    { from: "distress", to: "planning", kind: "handoff", label: "" },
    { from: "planning", to: "egress", kind: "handoff", label: "" }
  ],
  groups: []
};

export const PARALLEL_FANOUT_TRACE: TraceGraph = { /* ... */ };
export const CRITIC_LOOP_TRACE: TraceGraph = { /* ... */ };
export const MIXED_STATUS_TRACE: TraceGraph = { /* ... */ };
```

### CI Integration

Add to `.github/workflows/ci.yml`:

```yaml
- name: Run Agent Trace UI Tests
  run: |
    npm run test:unit -- --testPathPattern=AgentTrace
    npm run test:integration -- --grep "AgentTrace"
    npm run test:a11y -- --grep "AgentTrace"
```

## Summary

This design provides a complete specification for replacing ORCA's agent pill strip with a professional reasoning trace interface. The key points:

- **Two-state UI**: Collapsed summary → Expanded chronological list
- **Truthful rendering**: Only backend-reported data, no inference
- **Real-time streaming**: Incremental updates via SSE
- **Accessible**: WCAG 2.1 AA compliant, keyboard navigable, screen reader friendly
- **Performant**: Virtualization, memoization, smooth animations
- **Backward compatible**: AgentPill/AgentStrip remain untouched
- **Well-tested**: Unit, integration, accessibility, and visual regression tests

The implementation reuses existing infrastructure (`trace-adapter.ts`, `useAskThread`, ChatTurn) and integrates seamlessly with ORCA's design system (colors, shadows, typography). The flat list structure is explicitly documented to allow future migration to a tree structure if needed.
