import { useState } from "react";
import { approveRun, describeError, getRun, rejectRun } from "../api";
import { ApiError, type AgentRun } from "../types";
import { StatusBadge } from "./StatusBadge";
import { TracePanel } from "./TracePanel";

const MIN_REASON = 3;
const MAX_REASON = 500;
const MAX_EDITED = 2000;

interface Props {
  run: AgentRun;
  onChange: (run: AgentRun) => void;
}

/** Use `key={run.id}` where this is rendered so the form resets for a new run. */
export function DraftPanel({ run, onChange }: Props) {
  const [text, setText] = useState(run.draft_text ?? "");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const degraded = run.status !== "failed" && run.steps.some((s) => s.type === "error");

  async function act(action: () => Promise<AgentRun>) {
    setPending(true);
    setMessage(null);
    try {
      onChange(await action());
    } catch (e) {
      setMessage(describeError(e));
      if (e instanceof ApiError && e.code === "invalid_transition") {
        // Someone else already decided this run: show the real state.
        try {
          onChange(await getRun(run.id));
        } catch {
          /* keep the message above */
        }
      }
    } finally {
      setPending(false);
    }
  }

  function approve() {
    if (!text.trim()) {
      setMessage("The draft cannot be empty.");
      return;
    }
    // Send an edit only if the recruiter changed the text.
    const edited = text.trim() === (run.draft_text ?? "").trim() ? undefined : text.trim();
    void act(() => approveRun(run.id, edited));
  }

  function reject() {
    if (reason.trim().length < MIN_REASON) {
      setMessage(`Enter a reason of at least ${MIN_REASON} characters.`);
      return;
    }
    void act(() => rejectRun(run.id, reason.trim()));
  }

  return (
    <section aria-label="Draft" className="draft-panel">
      <h2>
        Draft <StatusBadge status={run.status} testId="run-status" />
      </h2>

      {degraded && (
        <div role="status" className="alert alert-warning" data-testid="degraded-banner">
          Some data was unavailable; the draft avoids relying on it.
        </div>
      )}

      {run.status === "failed" && (
        <div role="alert" className="alert alert-error">
          The run failed: {run.error ?? "unknown error"}
        </div>
      )}

      {run.status === "awaiting_approval" && (
        <>
          <label>
            Draft (you can edit it before approving)
            <textarea
              value={text}
              rows={6}
              maxLength={MAX_EDITED}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
          <button type="button" data-testid="approve-button" disabled={pending} onClick={approve}>
            Approve
          </button>
          <label>
            Rejection reason
            <input
              type="text"
              value={reason}
              maxLength={MAX_REASON}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <button type="button" disabled={pending} onClick={reject}>
            Reject
          </button>
        </>
      )}

      {run.status === "approved" && (
        <div data-testid="approved-text">
          <p>
            <strong>Approved - ready to send</strong>
          </p>
          <blockquote>{run.final_text}</blockquote>
        </div>
      )}

      {run.status === "rejected" && (
        <p>
          <strong>Rejected.</strong> Reason: {run.rejection_reason}
        </p>
      )}

      {message && (
        <div role="alert" className="alert alert-error">
          {message}
        </div>
      )}

      <TracePanel steps={run.steps} />
    </section>
  );
}
