import { useState } from "react";
import { createDraft, describeError } from "../api";
import type { AgentRun, ConversationDetail } from "../types";

const MAX_INSTRUCTIONS = 500;

interface Props {
  detail: ConversationDetail;
  onDrafted: (run: AgentRun) => void;
}

export function ConversationView({ detail, onDrafted }: Props) {
  const { conversation, candidate, job } = detail;
  const [instructions, setInstructions] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function draft() {
    setPending(true);
    setError(null);
    try {
      onDrafted(await createDraft(conversation.id, instructions.trim() || undefined));
    } catch (e) {
      setError(describeError(e));
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-label="Conversation">
      <h2>{candidate.name}</h2>
      <p className="muted">
        {candidate.email} · stage: {candidate.stage} · {job.title}, {job.team} ({job.location})
      </p>
      <ul className="transcript">
        {conversation.messages.map((m) => (
          <li key={`${m.sent_at}-${m.sender}`} className={`message message-${m.sender}`}>
            <strong>{m.sender}</strong>: {m.text}
          </li>
        ))}
      </ul>
      <label>
        Instructions for the draft (optional)
        <textarea
          value={instructions}
          maxLength={MAX_INSTRUCTIONS}
          rows={2}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </label>
      <p className="muted">
        {instructions.length}/{MAX_INSTRUCTIONS}
      </p>
      <button type="button" data-testid="draft-button" disabled={pending} onClick={draft}>
        {pending ? "Drafting…" : "Draft reply"}
      </button>
      {error && (
        <div role="alert" className="alert alert-error">
          {error}
        </div>
      )}
    </section>
  );
}
