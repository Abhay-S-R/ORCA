// Example usage of calculateExecutionOrder function
// This file demonstrates how the function works with the example trace from fixture.ts

import { calculateExecutionOrder } from "./calculateExecutionOrder";
import { EXAMPLE_TRACE } from "../reasoning/fixture";

// Calculate execution order from the example trace
const orderedSteps = calculateExecutionOrder(EXAMPLE_TRACE);

// Log the results for verification
console.log("=== Execution Order Calculation ===");
console.log(`Query ID: ${EXAMPLE_TRACE.query_id}`);
console.log(`Total steps: ${orderedSteps.length}\n`);

orderedSteps.forEach((step, index) => {
  const indent = "  ".repeat(step.type === "step" ? step.indent : 0);
  
  switch (step.type) {
    case "step":
      console.log(
        `${index + 1}. ${indent}${step.node.agent_name} (${step.node.id}) - ${step.node.latency_ms}ms - ${step.node.status}`
      );
      break;
    case "group_start":
      console.log(`${index + 1}. ${step.label}`);
      break;
    case "group_end":
      console.log(`${index + 1}. [End of parallel group]`);
      break;
    case "critic_reinvoke":
      console.log(`${index + 1}. ${"  ".repeat(step.indent)}${step.label}`);
      break;
  }
});

console.log("\n=== Summary ===");
const stepCount = orderedSteps.filter((s) => s.type === "step").length;
const groupCount = orderedSteps.filter((s) => s.type === "group_start").length;
const criticLoopCount = orderedSteps.filter((s) => s.type === "critic_reinvoke").length;

console.log(`Agent steps: ${stepCount}`);
console.log(`Parallel groups: ${groupCount}`);
console.log(`Critic re-invocations: ${criticLoopCount}`);
