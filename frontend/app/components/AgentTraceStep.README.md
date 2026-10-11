# AgentTraceStep Component

## Overview

The `AgentTraceStep` component renders an individual agent execution step within the expanded Agent Trace UI. It displays comprehensive information about a single agent's execution including status, timing, confidence, and detailed metadata.

## Features

- **Status Visualization**: Icons and color-coded display for all agent statuses (ok, degraded, failed, skipped, cancelled, running, pending)
- **Latency Formatting**: Automatically formats execution time (e.g., 1200ms → "1.2s", 450ms → "450ms")
- **Confidence Badges**: Shows H/M/L badges for completed agents with confidence data
- **Run Count Display**: Shows ×N badge for multi-run agents (critic loops)
- **Info Tooltip**: Hover tooltip with engine, model, tier, and reasoning summary
- **Indentation Support**: Handles 3 levels of indentation (0=base, 1=parallel, 2=critic loop)
- **Accessibility**: Full ARIA labels, semantic HTML, keyboard navigation, screen reader support

## Requirements Fulfilled

- 3.1, 3.2, 3.3, 3.4, 3.5: Agent step content display
- 9.1, 9.2, 9.3, 9.4, 9.5: Agent status visualization
- 10.1, 10.2, 10.3, 10.4, 10.5: Engine and confidence display
- 17.1, 17.2, 17.3, 17.4, 17.5: Run count display

## Usage

```tsx
import { AgentTraceStep } from "./AgentTraceStep";
import type { TraceNode } from "../reasoning/fixture";

// Basic usage
<AgentTraceStep node={traceNode} />

// With indentation (parallel execution)
<AgentTraceStep node={traceNode} indent={1} />

// With group label
<AgentTraceStep 
  node={traceNode} 
  showGroupLabel="Parallel execution (3 agents):" 
/>

// Currently running agent
<AgentTraceStep node={traceNode} isRunning={true} />

// Critic loop re-invocation (double indented)
<AgentTraceStep node={traceNode} indent={2} />
```

## Props

### `AgentTraceStepProps`

| Prop | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `node` | `TraceNode` | Yes | - | TraceNode from TraceGraph containing all agent execution data |
| `isRunning` | `boolean` | No | `false` | Override status to show agent as currently running |
| `indent` | `number` | No | `0` | Indentation level: 0 (base), 1 (parallel), 2 (critic loop) |
| `showGroupLabel` | `string` | No | - | Optional label to show above the step (e.g., "Parallel execution (4 agents):") |

## Visual Design

### Status Icons and Colors

- **✓ ok**: Green check mark, neutral background
- **⚠ degraded**: Yellow warning triangle, caution background
- **✗ failed**: Red X, error background
- **○ skipped**: Gray circle, faded appearance
- **⊘ cancelled**: Dashed border, caution tint
- **⟳ running**: Spinning loader, cyan color with pulse animation

### Layout Structure

```
┌─────────────────────────────────────────────────────────┐
│ [icon] Agent Name           1.2s    [H]    [×2]    [i] │
└─────────────────────────────────────────────────────────┘
```

Components from left to right:
1. Status icon
2. Agent name (truncates if too long)
3. Latency (formatted)
4. Confidence badge (H/M/L) - only for completed agents
5. Run count badge (×N) - only if run_count > 1
6. Info icon (appears on hover) - shows tooltip with details

### Indentation

- **Level 0** (base): No indentation
- **Level 1** (parallel): 16px left padding (`pl-4`)
- **Level 2** (critic loop): 32px left padding (`pl-8`)

### Tooltip Content

Hover or focus on the info icon to see:
- Agent status and skip reason (if applicable)
- Engine name (what computed this step)
- Model name and tier (if LLM was used)
- Confidence level (HIGH/MEDIUM/LOW_DATA)
- Run count explanation (if multi-run)
- Full reasoning summary

## Accessibility

### ARIA Support

- `aria-label`: Describes the complete step (name, status, time, confidence)
- `role="listitem"`: Semantic list item within trace list
- Screen reader text with full reasoning summary and skip reasons

### Keyboard Navigation

- Info icon is keyboard focusable
- Focus shows tooltip
- All interactive elements meet 44px touch target minimum

### Color Contrast

All status colors meet WCAG 2.1 AA standards (4.5:1 minimum):
- ok: ink on shelf-3 background
- degraded: caution on caution/10 background
- failed: no-go on no-go/10 background
- running: ocean-cyan on ocean-cyan/10 background

## Integration Example

The component is designed to be used within an ordered list (`<ol>`) in the `AgentTraceExpanded` component:

```tsx
<ol className="flex flex-col gap-1" role="list" aria-label="Agent execution steps">
  {orderedSteps.map((step, index) => (
    <React.Fragment key={index}>
      {step.type === "group_start" && (
        <AgentTraceStep 
          node={step.node} 
          showGroupLabel={step.label}
          indent={1}
        />
      )}
      {step.type === "step" && (
        <AgentTraceStep 
          node={step.node} 
          indent={step.indent}
          isRunning={step.node.status === "running"}
        />
      )}
      {step.type === "critic_reinvoke" && (
        <div className="pl-4 text-[10px] text-ink-dim">
          {step.label}
        </div>
      )}
    </React.Fragment>
  ))}
</ol>
```

## Styling

Uses ORCA design system tokens:
- Typography: 11px-12px, font-medium
- Colors: shelf-*, ink-*, status colors (go, caution, no-go, ocean-cyan)
- Borders: hairline/60
- Shadows: Subtle on hover
- Transitions: 150ms duration for smooth interactions

## Testing

Unit tests should verify:
- All status types render correctly (ok, degraded, failed, skipped, cancelled, running)
- Run count badge appears when run_count > 1
- Skip reason displays for skipped/cancelled agents
- Info tooltip shows correct content
- Confidence badges display for completed agents only
- Indentation styling applies correctly
- ARIA labels are present and descriptive

See `tasks.md` task 5.2 for complete testing requirements.
