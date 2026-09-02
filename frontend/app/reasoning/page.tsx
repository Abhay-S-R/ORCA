import { Workflow } from "lucide-react";
import { Planned } from "../components/Planned";

// Reasoning (§4.4) — the agent DAG. The renderer is chosen (React Flow) and
// installed, but node and edge semantics come from real trace data, and the
// trace stream that carries it is Phase 2.
export default function ReasoningPage() {
  return (
    <Planned
      icon={<Workflow className="size-6" />}
      title="Reasoning"
      lede="The full agent graph behind an answer: which agents ran, what each one read, and where a result came from."
      needs="The graph is drawn from real execution traces. Until the trace stream lands in Phase 2, a diagram here would show a shape ORCA never actually ran."
    />
  );
}
