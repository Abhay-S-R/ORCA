# Requirements Document

## Introduction

This feature replaces ORCA's current agent pill strip UI with a professional trace interface similar to ChatGPT and Claude's reasoning traces. The new interface displays agent execution in a clean, chronological format showing collapsed summary ("Worked for 33s") that expands into a detailed, flat list of execution steps with real-time streaming updates.

The backend audit work is complete (agents 4 and 6 audited and fixed). This feature implements the frontend UI that accurately reflects what the backend reports—no inference, no guessing. The trace must only show what the backend actually did.

## Glossary

- **Agent_Trace_UI**: The new frontend component that displays agent execution traces
- **Agent_Strip**: The current pill-based UI component (AgentPill.tsx and AgentStrip components)
- **Trace_Backend**: The `/trace/{query_id}` API endpoint that provides TraceGraph data
- **SSE_Stream**: Server-sent events stream that sends `agent_span` events as agents complete
- **Collapsed_View**: The summary line showing total execution time (e.g., "Worked for 33s")
- **Expanded_View**: The detailed chronological list of agent execution steps
- **Trace_Line**: The plain sentence from the backend describing what an agent did
- **Critic_Loop**: When the Critic agent re-invokes a specialist agent for refinement
- **Parallel_Execution**: Multiple specialist agents running concurrently (fanout groups)
- **TraceGraph**: Backend data structure containing nodes, edges, and groups
- **ChatTurn**: React component that currently uses AgentStrip to display agent activity

## Requirements

### Requirement 1: Collapsed View Display

**User Story:** As a user, I want to see a quiet summary line above my answer, so that I can quickly understand the total execution time without visual clutter.

#### Acceptance Criteria

1. THE Agent_Trace_UI SHALL display a collapsed view showing total execution time in the format "Worked for {N}s"
2. WHEN all agents have completed, THE Agent_Trace_UI SHALL calculate total execution time by summing all agent latency_ms values
3. THE Agent_Trace_UI SHALL display the collapsed view as a single line above the answer content
4. THE Agent_Trace_UI SHALL use a minimal, professional visual style consistent with ChatGPT and Claude reasoning traces
5. WHEN a user hovers over the collapsed view, THE Agent_Trace_UI SHALL indicate that the trace is expandable

### Requirement 2: Expanded View Structure

**User Story:** As a user, I want to expand the trace into a chronological list of steps, so that I can understand what the system did in order.

#### Acceptance Criteria

1. WHEN a user clicks the collapsed view, THE Agent_Trace_UI SHALL expand to show a flat chronological list of agent steps
2. THE Agent_Trace_UI SHALL display agent steps in execution order as a flat list, NOT as a tree structure
3. THE Agent_Trace_UI SHALL document explicitly in code comments that the current implementation uses a flat list to allow teammates to switch to tree structure later
4. FOR ALL agent steps, THE Agent_Trace_UI SHALL display the step in chronological order based on execution sequence
5. WHEN the expanded view is displayed, THE Agent_Trace_UI SHALL provide a way to collapse back to summary view

### Requirement 3: Agent Step Content Display

**User Story:** As a user, I want each step to show what the agent did in plain language, so that I can understand the system's reasoning process.

#### Acceptance Criteria

1. FOR ALL agent steps, THE Agent_Trace_UI SHALL display the `trace_line` field from the backend when available
2. WHEN `trace_line` is not available, THE Agent_Trace_UI SHALL display the `reasoning_summary` field from the backend
3. THE Agent_Trace_UI SHALL display the agent's name or human-readable label for each step
4. THE Agent_Trace_UI SHALL display each agent's execution time in milliseconds or seconds
5. THE Agent_Trace_UI SHALL display the agent's status (ok, degraded, failed, skipped, cancelled) visually

### Requirement 4: Real-time Streaming Updates

**User Story:** As a user, I want to see the trace update live as agents work, so that I can follow progress in real-time.

#### Acceptance Criteria

1. WHEN the SSE_Stream sends `agent_span` events, THE Agent_Trace_UI SHALL update the expanded view to show newly completed agent steps
2. WHILE agents are executing, THE Agent_Trace_UI SHALL show a progress indicator for agents that are currently running
3. THE Agent_Trace_UI SHALL update the collapsed view's total execution time as new agent spans complete
4. WHEN all agents complete, THE Agent_Trace_UI SHALL remove all progress indicators and show final execution time
5. THE Agent_Trace_UI SHALL handle SSE_Stream events incrementally without re-rendering the entire trace list

### Requirement 5: Critic Loop Visualization

**User Story:** As a user, I want to see when the Critic agent calls another agent again, so that I understand the refinement process.

#### Acceptance Criteria

1. WHEN the TraceGraph contains edges with `kind: "critic_loop"`, THE Agent_Trace_UI SHALL display re-invocations as separate steps
2. THE Agent_Trace_UI SHALL display re-invoked agent steps with indentation or visual indication showing they are critic-driven
3. THE Agent_Trace_UI SHALL display text in the format "Critic agent calls <agent X> again" for re-invocations
4. FOR ALL re-invoked agents, THE Agent_Trace_UI SHALL show the step indented under the critic's critique step
5. WHEN an agent has `run_count` greater than 1, THE Agent_Trace_UI SHALL indicate the agent ran multiple times

### Requirement 6: Parallel Agent Execution Display

**User Story:** As a user, I want to see which agents ran concurrently, so that I understand parallel execution patterns.

#### Acceptance Criteria

1. WHEN the TraceGraph contains groups with `reason: "parallel_fanout"`, THE Agent_Trace_UI SHALL identify parallel execution
2. THE Agent_Trace_UI SHALL display individual lines for each specialist agent in a parallel group
3. FOR ALL agents in a parallel group, THE Agent_Trace_UI SHALL display timestamps showing concurrent execution
4. THE Agent_Trace_UI SHALL visually indicate parallel execution through layout, spacing, or grouping
5. FOR ALL parallel agents, THE Agent_Trace_UI SHALL show individual execution times (e.g., "Weather Intel ran in 1.2s", "Geospatial ran in 0.8s")

### Requirement 7: Backward Compatibility Preservation

**User Story:** As a developer, I want existing AgentPill and AgentStrip components to remain functional, so that backward compatibility is maintained during transition.

#### Acceptance Criteria

1. THE Agent_Trace_UI SHALL NOT modify or delete existing AgentPill.tsx component
2. THE Agent_Trace_UI SHALL NOT modify or delete existing AgentStrip component
3. THE Agent_Trace_UI SHALL be implemented as new components separate from AgentPill and AgentStrip
4. WHEN existing code references AgentPill or AgentStrip, THE Agent_Trace_UI SHALL allow those references to function unchanged
5. THE Agent_Trace_UI SHALL provide a clear migration path from AgentStrip to the new trace components

### Requirement 8: Backend Data Accuracy

**User Story:** As a user, I want the trace to show only what actually happened, so that the display is truthful and trustworthy.

#### Acceptance Criteria

1. THE Agent_Trace_UI SHALL display only agents reported by the Trace_Backend
2. THE Agent_Trace_UI SHALL NOT infer or guess agent execution beyond what the backend reports
3. WHEN the backend reports an agent ran, THE Agent_Trace_UI SHALL display that agent
4. WHEN the backend does not report an agent, THE Agent_Trace_UI SHALL NOT display that agent
5. THE Agent_Trace_UI SHALL use the exact `trace_line` or `reasoning_summary` text provided by the backend without modification

### Requirement 9: Agent Status Visualization

**User Story:** As a user, I want to see each agent's completion status clearly, so that I can identify issues or degraded responses.

#### Acceptance Criteria

1. FOR ALL agent steps, THE Agent_Trace_UI SHALL display visual indicators for status values: ok, degraded, failed, skipped, cancelled
2. THE Agent_Trace_UI SHALL use color coding that is distinguishable and accessible (WCAG AA compliant)
3. THE Agent_Trace_UI SHALL display status through both color and icons/text for accessibility
4. WHEN an agent has status "skipped" or "cancelled", THE Agent_Trace_UI SHALL display the `skip_reason` field
5. WHEN an agent has status "failed", THE Agent_Trace_UI SHALL visually emphasize the failure

### Requirement 10: Engine and Confidence Display

**User Story:** As a user, I want to see which engine computed each step and its confidence level, so that I understand the quality of each result.

#### Acceptance Criteria

1. FOR ALL completed agent steps, THE Agent_Trace_UI SHALL display the `engine` field when available
2. WHEN an agent has `confidence_tier` data, THE Agent_Trace_UI SHALL display the confidence level (HIGH, MEDIUM, LOW_DATA)
3. THE Agent_Trace_UI SHALL display engine information in a non-intrusive way (e.g., tooltip, expandable detail)
4. WHEN an agent used an LLM, THE Agent_Trace_UI SHALL indicate the model tier (cheap, mid, reasoning) when available
5. WHEN an agent did not run (skipped or cancelled), THE Agent_Trace_UI SHALL NOT display engine information

### Requirement 11: Edge Type Visualization

**User Story:** As a developer debugging execution flow, I want to see different edge types between agents, so that I understand handoffs, loops, and cancellations.

#### Acceptance Criteria

1. WHEN the TraceGraph contains edges with `kind: "handoff"`, THE Agent_Trace_UI SHALL display normal sequential flow
2. WHEN the TraceGraph contains edges with `kind: "critic_loop"`, THE Agent_Trace_UI SHALL display re-invocation flow with visual distinction
3. WHEN the TraceGraph contains edges with `kind: "cancelled"`, THE Agent_Trace_UI SHALL display the cancelled edge with visual indication (e.g., dashed, faded)
4. THE Agent_Trace_UI SHALL use the TraceGraph edges to determine execution flow order
5. THE Agent_Trace_UI SHALL NOT infer edges beyond what the TraceGraph provides

### Requirement 12: Responsive Layout

**User Story:** As a mobile user, I want the trace to display clearly on my device, so that I can review execution details anywhere.

#### Acceptance Criteria

1. THE Agent_Trace_UI SHALL display collapsed view on screens of all sizes
2. THE Agent_Trace_UI SHALL display expanded view with readable text on mobile devices (minimum 320px width)
3. WHEN screen width is limited, THE Agent_Trace_UI SHALL wrap or truncate long agent step text appropriately
4. THE Agent_Trace_UI SHALL maintain touch-friendly interaction targets on mobile devices (minimum 44px tap areas)
5. THE Agent_Trace_UI SHALL use responsive typography that scales appropriately across screen sizes

### Requirement 13: Integration with ChatTurn

**User Story:** As a developer, I want the new trace UI to integrate cleanly with ChatTurn, so that it replaces the existing AgentStrip without breaking the chat interface.

#### Acceptance Criteria

1. THE Agent_Trace_UI SHALL provide a component interface compatible with ChatTurn's current AgentStrip usage
2. THE Agent_Trace_UI SHALL accept the same query_id and trace data props that ChatTurn provides
3. THE Agent_Trace_UI SHALL position itself above the answer content as AgentStrip currently does
4. THE Agent_Trace_UI SHALL integrate with ChatTurn's existing SSE stream handling
5. THE Agent_Trace_UI SHALL not break ChatTurn's existing layout or styling

### Requirement 14: Trace Data Adapter Integration

**User Story:** As a developer, I want the trace UI to use the existing trace-adapter.ts, so that data transformation logic is centralized.

#### Acceptance Criteria

1. THE Agent_Trace_UI SHALL use the `adaptTraceGraph` function from trace-adapter.ts to process backend data
2. THE Agent_Trace_UI SHALL consume the adapted TraceGraph format (nodes, edges, groups)
3. THE Agent_Trace_UI SHALL handle all TraceNode fields provided by the adapter (id, agent_name, depth, status, confidence_tier, latency_ms, reasoning_summary, engine, skip_reason, run_count)
4. THE Agent_Trace_UI SHALL NOT duplicate data transformation logic already present in trace-adapter.ts
5. THE Agent_Trace_UI SHALL handle missing or null fields gracefully with appropriate fallbacks

### Requirement 15: Performance Optimization

**User Story:** As a user, I want the trace to render smoothly even with many agent steps, so that the interface remains responsive.

#### Acceptance Criteria

1. WHEN rendering more than 10 agent steps, THE Agent_Trace_UI SHALL use efficient rendering techniques (virtualization, memoization)
2. THE Agent_Trace_UI SHALL update incrementally when new agent spans arrive via SSE
3. THE Agent_Trace_UI SHALL NOT re-render completed steps when new steps are added
4. THE Agent_Trace_UI SHALL debounce or throttle rapid SSE updates if needed to maintain smooth rendering
5. WHEN expanding or collapsing the trace, THE Agent_Trace_UI SHALL animate smoothly with framer-motion or CSS transitions

### Requirement 16: Accessibility

**User Story:** As a screen reader user, I want to navigate the agent trace, so that I can understand execution flow without visual presentation.

#### Acceptance Criteria

1. THE Agent_Trace_UI SHALL provide semantic HTML structure (lists, headings, regions)
2. THE Agent_Trace_UI SHALL use ARIA labels to describe agent steps and their relationships
3. THE Agent_Trace_UI SHALL announce state changes (expanding, new steps) via aria-live regions
4. THE Agent_Trace_UI SHALL ensure keyboard navigation works for expanding/collapsing the trace
5. THE Agent_Trace_UI SHALL meet WCAG 2.1 AA standards for color contrast and interactive elements

### Requirement 17: Agent Run Count Display

**User Story:** As a user, I want to see when an agent ran multiple times, so that I understand re-invocation patterns.

#### Acceptance Criteria

1. WHEN an agent has `run_count` greater than 1, THE Agent_Trace_UI SHALL display a visual indicator (e.g., "×2", "ran 2 times")
2. THE Agent_Trace_UI SHALL display the cumulative latency for multi-run agents (sum of all runs)
3. THE Agent_Trace_UI SHALL explain in hover text or tooltip that multiple runs indicate critic-driven refinement
4. THE Agent_Trace_UI SHALL NOT create duplicate step entries for the same agent with multiple runs
5. FOR ALL multi-run agents, THE Agent_Trace_UI SHALL show the run count prominently near the agent name

### Requirement 18: Visual Polish and Professionalism

**User Story:** As a product manager, I want the trace UI to match the quality of ChatGPT and Claude, so that ORCA appears professional and trustworthy.

#### Acceptance Criteria

1. THE Agent_Trace_UI SHALL use clean, minimal styling consistent with modern AI chat interfaces
2. THE Agent_Trace_UI SHALL use subtle animations for state transitions (expand/collapse, streaming updates)
3. THE Agent_Trace_UI SHALL use typography and spacing that enhance readability
4. THE Agent_Trace_UI SHALL use ORCA's existing design system colors, borders, and shadows
5. THE Agent_Trace_UI SHALL feel cohesive with the rest of ORCA's interface (fonts, colors, spacing)
