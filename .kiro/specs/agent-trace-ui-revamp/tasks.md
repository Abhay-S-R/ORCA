# Implementation Plan: Agent Trace UI Revamp

## Overview

This implementation replaces ORCA's current pill-based agent strip UI with a professional trace interface displaying agent execution in a collapsed summary ("Worked for 33s") that expands into a detailed, flat chronological list. The implementation uses TypeScript/React with framer-motion for animations, integrates with the existing trace-adapter.ts, and maintains backward compatibility with AgentPill/AgentStrip components.

## Tasks

- [x] 1. Set up core component structure and data models
  - Create `frontend/app/components/AgentTraceUI.tsx` container component
  - Define TypeScript interfaces for component props (AgentTraceUIProps, AgentTraceCollapsedProps, AgentTraceExpandedProps, AgentTraceStepProps)
  - Set up state management for expanded/collapsed view and trace data loading
  - Import and configure framer-motion for animations
  - _Requirements: 1.1, 1.3, 2.1, 13.1, 13.2, 13.3_

- [x] 2. Implement AgentTraceCollapsed component
  - [x] 2.1 Create AgentTraceCollapsed component with summary view
    - Create `frontend/app/components/AgentTraceCollapsed.tsx`
    - Implement total execution time calculation from spans (sum of latency_ms values)
    - Render "Worked for {N}s" text with proper time formatting (ms vs seconds)
    - Add chevron icon to indicate expandability
    - Implement onClick handler to trigger expansion
    - Apply styling: minimal border, subtle background (shelf-1/40), hover states
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 2.2 Write unit tests for AgentTraceCollapsed
    - Test total time calculation (3200ms → "3.2s")
    - Test streaming spinner display when streaming=true
    - Test onExpand callback invocation on click
    - Test keyboard accessibility (Enter/Space triggers expand)
    - _Requirements: 1.1, 1.2, 1.5_

- [x] 3. Implement execution order calculation algorithm
  - [x] 3.1 Create execution order calculation function
    - Create utility function `calculateExecutionOrder(graph: TraceGraph): OrderedStep[]`
    - Implement edge parsing to build directed graph of agent dependencies
    - Implement topological sort with depth-first traversal
    - Handle parallel group identification from TraceGraph.groups
    - Handle critic loop nesting under critique steps
    - Add explicit code comments documenting flat list structure (allows future tree migration)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.1, 5.2, 6.1, 11.4_

  - [ ]* 3.2 Write unit tests for execution order algorithm
    - Test simple linear trace ordering
    - Test parallel agent grouping
    - Test critic loop nesting
    - Test cancelled edge handling
    - Test edge cases (empty graph, single node, cycles)
    - _Requirements: 2.4, 5.1, 5.2, 6.1_

- [x] 4. Checkpoint - Verify core logic
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement AgentTraceStep component
  - [x] 5.1 Create AgentTraceStep component for individual steps
    - Create `frontend/app/components/AgentTraceStep.tsx`
    - Render status icon (✓ ok, ⚠ degraded, ✗ failed, ○ skipped, ⊘ cancelled, ⟳ running)
    - Display agent name using AGENT_LABEL map from trace-adapter.ts
    - Format and display latency (1200ms → "1.2s", 450ms → "450ms")
    - Display confidence badge (H/M/L) when available
    - Display run count badge (×2) when run_count > 1
    - Implement info icon with tooltip showing engine, model, reasoning_summary
    - Handle indentation levels (0=base, 1=parallel, 2=critic loop)
    - Apply status-based color coding (ok, degraded, failed, skipped, cancelled)
    - Implement accessibility: ARIA labels, semantic HTML
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 9.1, 9.2, 9.3, 9.4, 9.5, 10.1, 10.2, 10.3, 10.4, 10.5, 17.1, 17.2, 17.3, 17.4, 17.5_

  - [ ]* 5.2 Write unit tests for AgentTraceStep
    - Test all status type renderings (ok, degraded, failed, skipped, cancelled)
    - Test run count badge display when run_count > 1
    - Test skip_reason display for skipped/cancelled agents
    - Test info tooltip content (engine, reasoning_summary)
    - Test confidence badge display logic
    - Test indentation styling
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 9.1, 9.5, 17.1_

- [x] 6. Implement AgentTraceExpanded component
  - [x] 6.1 Create AgentTraceExpanded component with detail view
    - Create `frontend/app/components/AgentTraceExpanded.tsx`
    - Integrate calculateExecutionOrder to get chronological step list
    - Render flat list of AgentTraceStep components in execution order
    - Implement parallel execution grouping with "Parallel execution (N agents):" label
    - Implement critic loop display with indentation and "↻ Critic calls X again" text
    - Add header with collapse button (close icon)
    - Implement collapse callback (onCollapse)
    - Apply styling: container with border, background, shadows
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2, 6.1, 6.2, 6.3, 6.4, 6.5, 11.1, 11.2_

  - [ ]* 6.2 Write unit tests for AgentTraceExpanded
    - Test step rendering in correct chronological order
    - Test parallel agent grouping with indentation
    - Test critic loop re-invocation indentation
    - Test confidence badge display only for completed agents
    - Test missing field handling (graceful fallbacks)
    - _Requirements: 2.1, 2.4, 5.1, 5.2, 6.2, 6.4_

- [x] 7. Implement real-time streaming updates
  - [ ] 7.1 Add SSE streaming support to AgentTraceUI
    - Implement incremental step updates as agent_span events arrive
    - Update collapsed view total time as new spans complete
    - Show progress indicators for running agents
    - Remove progress indicators when all agents complete
    - Use memoization to prevent re-rendering completed steps
    - Implement debouncing for rapid SSE updates (100ms)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 15.2, 15.3, 15.4_

  - [ ]* 7.2 Write integration tests for streaming
    - Mock SSE endpoint to send agent_span events incrementally
    - Verify UI updates in real-time as spans arrive
    - Verify final state matches all spans received
    - Test debouncing behavior with rapid events
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 8. Implement expand/collapse animations and interactions
  - [ ] 8.1 Add framer-motion animations for expand/collapse
    - Implement expand animation (height 0→auto, opacity 0→1, 200ms easeOut)
    - Implement collapse animation (height auto→0, opacity 1→0, 200ms easeOut)
    - Add step entry animation for streaming updates (opacity 0→1, x -8→0, 150ms)
    - Add running pulse animation for in-progress agents (opacity pulse, 1.5s infinite)
    - Implement smooth scroll behavior when expanding
    - _Requirements: 1.5, 2.5, 15.5, 18.2_

  - [ ]* 8.2 Write integration tests for expand/collapse
    - Test expand interaction (click collapsed → shows expanded view)
    - Test collapse interaction (click close button → shows collapsed view)
    - Verify animation completion
    - _Requirements: 1.5, 2.5_

- [ ] 9. Checkpoint - Verify core UI components
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Implement AgentTraceUI container component
  - [ ] 10.1 Wire up AgentTraceUI with state and data fetching
    - Implement expanded/collapsed state management
    - Implement trace data fetching from `/trace/{query_id}` on expand
    - Integrate with adaptTraceGraph from trace-adapter.ts
    - Handle loading states (skeleton loader while fetching)
    - Implement error handling (404, network errors, missing data)
    - Pass streaming prop to child components
    - Calculate total time from spans for collapsed view
    - _Requirements: 1.2, 2.1, 8.1, 8.2, 8.3, 8.4, 8.5, 14.1, 14.2, 14.3, 14.4, 14.5_

  - [ ]* 10.2 Write unit tests for AgentTraceUI container
    - Test initial collapsed state rendering
    - Test expand trigger and data fetching
    - Test loading state display
    - Test error state handling
    - Test integration with adaptTraceGraph
    - _Requirements: 1.1, 2.1, 8.1, 14.1, 14.2_

- [ ] 11. Implement responsive layout and styling
  - [ ] 11.1 Add responsive breakpoints and mobile optimizations
    - Implement mobile layout (320px-639px): smaller text (11px), 40px collapsed height
    - Implement tablet layout (640px-1023px): medium text (13px), 44px collapsed height
    - Implement desktop layout (1024px+): full layout with wider tooltips
    - Use fluid typography with clamp() for smooth scaling
    - Implement touch-friendly targets (48px mobile, 44px desktop)
    - Add horizontal scroll for wide content on mobile
    - Test text wrapping and truncation on narrow screens
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 11.2 Write responsive layout tests
    - Test collapsed view display on all screen sizes
    - Test expanded view readability on mobile (320px width)
    - Test touch target sizes on mobile
    - Test text wrapping behavior
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [ ] 12. Implement accessibility features
  - [ ] 12.1 Add ARIA labels and keyboard navigation
    - Add semantic HTML structure (section, button, ol/li for steps)
    - Implement ARIA labels (aria-label, aria-expanded, role attributes)
    - Add aria-live regions for streaming updates announcements
    - Implement keyboard navigation (Tab, Enter, Space, Escape, Arrow keys, Home/End)
    - Add screen reader text for status icons and step relationships
    - Ensure focus management on expand/collapse
    - _Requirements: 16.1, 16.2, 16.3, 16.4_

  - [ ]* 12.2 Run automated accessibility tests
    - Run axe-core on collapsed view
    - Run axe-core on expanded view
    - Verify WCAG 2.1 AA color contrast (4.5:1 minimum)
    - Verify touch target sizes (44x44px minimum)
    - Test keyboard operability
    - _Requirements: 16.5, 9.2_

- [ ] 13. Integrate with ChatTurn component
  - [ ] 13.1 Replace AgentStrip with AgentTraceUI in ChatTurn
    - Modify ChatTurn to conditionally render AgentTraceUI (behind feature flag)
    - Pass displaySpans, streaming, and query_id props to AgentTraceUI
    - Maintain existing position above answer content
    - Preserve existing SSE stream handling from useAskThread
    - Ensure no breaking changes to ChatTurn layout or styling
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 13.2 Write integration tests for ChatTurn integration
    - Test AgentTraceUI rendering within ChatTurn
    - Test SSE stream integration
    - Test position above answer content
    - Test layout preservation
    - _Requirements: 13.3, 13.4, 13.5_

- [ ] 14. Implement performance optimizations
  - [ ] 14.1 Add virtualization and memoization
    - Implement virtualization with @tanstack/react-virtual for 10+ steps
    - Add useMemo for calculateExecutionOrder
    - Add React.memo to AgentTraceStep component
    - Implement incremental rendering (only new steps re-render)
    - Add performance monitoring for trace rendering
    - _Requirements: 15.1, 15.2, 15.3_

  - [ ]* 14.2 Write performance tests
    - Test rendering performance with 15+ agent steps
    - Verify virtualization activates for large lists
    - Test memoization prevents unnecessary re-renders
    - Measure expand/collapse animation frame rate
    - _Requirements: 15.1, 15.2, 15.3, 15.5_

- [ ] 15. Checkpoint - Verify integration and performance
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 16. Implement error handling and edge cases
  - [ ] 16.1 Add comprehensive error handling
    - Handle missing trace data (404 from /trace/{query_id}): show collapsed view only
    - Handle incomplete spans (missing latency_ms, status): use safe defaults
    - Handle network errors: show last known state with retry button
    - Implement race condition handling (expand before data ready): show skeleton
    - Add timeout for trace fetch (5 seconds)
    - Log errors to console without crashing UI
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 14.5_

  - [ ]* 16.2 Write error handling tests
    - Test 404 response handling
    - Test missing field fallbacks
    - Test network error recovery
    - Test race condition handling
    - Test timeout behavior
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 17. Apply visual polish and design system integration
  - [ ] 17.1 Finalize styling with ORCA design system
    - Apply typography tokens (12px collapsed, 11px-12px expanded, font-medium, font-mono)
    - Apply color tokens (shelf-1/40 bg, hairline/60 border, ink colors, status colors)
    - Apply shadow tokens (shadow-2xs collapsed, shadow-sm expanded)
    - Apply spacing tokens (px-4 py-2, gap-1, indent pl-4/pl-8)
    - Verify all status colors meet WCAG AA contrast (4.5:1)
    - Test visual cohesion with rest of ORCA interface
    - _Requirements: 1.4, 18.1, 18.3, 18.4, 18.5, 9.2_

  - [ ]* 17.2 Run visual regression tests
    - Capture screenshots of collapsed view
    - Capture screenshots of expanded view (various states)
    - Compare with design mockups
    - Verify animations and transitions
    - _Requirements: 18.1, 18.2, 18.3_

- [ ] 18. Final integration and testing
  - [ ] 18.1 End-to-end testing in staging environment
    - Test with real queries and trace data
    - Test streaming behavior with live SSE
    - Test all agent status types (ok, degraded, failed, skipped, cancelled)
    - Test parallel execution display
    - Test critic loop display
    - Test on multiple browsers (Chrome, Firefox, Safari)
    - Test on mobile devices (iOS Safari, Chrome Android)
    - _Requirements: All requirements_

  - [ ]* 18.2 Accessibility manual testing
    - Test with NVDA screen reader
    - Test with JAWS screen reader
    - Test keyboard navigation flow
    - Test high contrast mode
    - Test color blindness filters
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

- [ ] 19. Final checkpoint - Feature complete
  - Ensure all tests pass, verify feature is ready for rollout.

## Notes

- Tasks marked with `*` are optional testing tasks and can be skipped for faster MVP delivery
- All implementation tasks reference specific requirements from requirements.md for traceability
- The design uses a flat list structure with explicit code comments to allow future migration to tree structure
- Existing AgentPill.tsx and AgentStrip components remain untouched for backward compatibility
- Integration uses feature flag to allow gradual rollout and easy rollback
- TypeScript interfaces are reused from trace-adapter.ts where possible
- All accessibility requirements target WCAG 2.1 AA compliance
- Performance optimizations activate automatically for traces with 10+ steps
- The feature is designed for truthfulness: display only backend-reported data, no inference

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1"] },
    { "id": 5, "tasks": ["6.2", "7.1", "8.1"] },
    { "id": 6, "tasks": ["7.2", "8.2", "10.1"] },
    { "id": 7, "tasks": ["10.2", "11.1", "12.1"] },
    { "id": 8, "tasks": ["11.2", "12.2", "13.1"] },
    { "id": 9, "tasks": ["13.2", "14.1", "16.1"] },
    { "id": 10, "tasks": ["14.2", "16.2", "17.1"] },
    { "id": 11, "tasks": ["17.2", "18.1"] },
    { "id": 12, "tasks": ["18.2"] }
  ]
}
```
