import type { AgentRun, AgentStep } from "./types";

export function makeStep(overrides: Partial<AgentStep> = {}): AgentStep {
  return {
    index: 0,
    type: "tool_call",
    name: "get_candidate",
    input: { candidate_id: "cand_priya" },
    output: null,
    error: null,
    duration_ms: 3,
    ts: "2026-11-06T10:00:00Z",
    ...overrides,
  };
}

export function makeRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run1",
    conversation_id: "conv_priya",
    status: "awaiting_approval",
    instructions: null,
    steps: [
      makeStep(),
      makeStep({ index: 1, type: "tool_result", input: null, output: { name: "Priya Sharma" } }),
      makeStep({ index: 2, type: "llm_message", name: null, input: null, output: { text: "Hi Priya" } }),
    ],
    draft_text: "Hi Priya, your interview is on 2026-11-12.",
    final_text: null,
    rejection_reason: null,
    error: null,
    created_at: "2026-11-06T10:00:00Z",
    updated_at: "2026-11-06T10:00:00Z",
    ...overrides,
  };
}
