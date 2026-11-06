import type { AgentStep } from "../types";

const MAX_SUMMARY = 120;

function shorten(text: string): string {
  return text.length > MAX_SUMMARY ? `${text.slice(0, MAX_SUMMARY)}…` : text;
}

/** One short line describing what the step did. */
function summarize(step: AgentStep): string {
  if (step.error) return step.error;
  if (step.type === "tool_call" && step.input) return shorten(JSON.stringify(step.input));
  if (step.type === "tool_result" && step.output) return shorten(JSON.stringify(step.output));
  if (step.type === "llm_message" && typeof step.output?.text === "string") {
    return shorten(step.output.text);
  }
  return "";
}

export function TracePanel({ steps }: { steps: AgentStep[] }) {
  return (
    <section aria-label="Trace">
      <h3>Trace ({steps.length} steps)</h3>
      <ol className="trace">
        {steps.map((step) => (
          <li
            key={step.index}
            data-testid="trace-step"
            className={step.type === "error" ? "step step-error" : "step"}
          >
            <span className="step-type">{step.type}</span>
            {step.name && <code>{step.name}</code>}
            <span className="step-summary">{summarize(step)}</span>
            <span className="muted">{step.duration_ms} ms</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
