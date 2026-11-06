import type { ConversationSummary } from "../types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  conversations: ConversationSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function ConversationList({ conversations, selectedId, onSelect }: Props) {
  return (
    <ul className="conversation-list" aria-label="Conversations">
      {conversations.map((c) => (
        <li key={c.id}>
          <button
            type="button"
            className={c.id === selectedId ? "conversation-item selected" : "conversation-item"}
            data-testid="conversation-item"
            onClick={() => onSelect(c.id)}
          >
            <strong>{c.candidate_name}</strong>
            <span className="muted">{c.job_title}</span>
            <span className="preview">{c.last_message_preview}</span>
            {c.latest_run_status && <StatusBadge status={c.latest_run_status} />}
          </button>
        </li>
      ))}
    </ul>
  );
}
