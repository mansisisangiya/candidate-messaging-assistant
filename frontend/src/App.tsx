import { useCallback, useEffect, useRef, useState } from "react";
import { getConversation, describeError, listConversations } from "./api";
import { ConversationList } from "./components/ConversationList";
import { ConversationView } from "./components/ConversationView";
import { DraftPanel } from "./components/DraftPanel";
import type { AgentRun, ConversationDetail, ConversationSummary } from "./types";

export default function App() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latestRequest = useRef<string | null>(null);

  const refreshList = useCallback(async () => {
    try {
      setConversations(await listConversations());
    } catch (e) {
      setError(describeError(e));
    }
  }, []);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  async function select(id: string) {
    latestRequest.current = id;
    setLoading(true);
    setError(null);
    try {
      const loaded = await getConversation(id);
      if (latestRequest.current === id) setDetail(loaded); // ignore a slower, older response
    } catch (e) {
      if (latestRequest.current === id) setError(describeError(e));
    } finally {
      if (latestRequest.current === id) setLoading(false);
    }
  }

  function runChanged(run: AgentRun) {
    setDetail((d) => (d ? { ...d, latest_run: run } : d));
    void refreshList(); // keeps the status badges in the list current
  }

  return (
    <main>
      <h1>Candidate Messaging Assistant</h1>
      {error && (
        <div role="alert" className="alert alert-error">
          {error}
        </div>
      )}
      <div className="layout">
        <aside>
          <ConversationList
            conversations={conversations}
            selectedId={detail?.conversation.id ?? null}
            onSelect={(id) => void select(id)}
          />
        </aside>
        <div className="content">
          {loading && <p>Loading…</p>}
          {!detail && !loading && <p className="muted">Select a conversation.</p>}
          {detail && !loading && (
            <>
              <ConversationView key={detail.conversation.id} detail={detail} onDrafted={runChanged} />
              {detail.latest_run && (
                <DraftPanel key={detail.latest_run.id} run={detail.latest_run} onChange={runChanged} />
              )}
            </>
          )}
        </div>
      </div>
    </main>
  );
}
