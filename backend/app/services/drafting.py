from app.agent.failure_injection import FailingTools
from app.agent.loop import ToolExecutor, run_agent
from app.agent.tools import CandidateScopedTools, ToolRegistry
from app.data.store import FixtureStore
from app.db.repo import RunRepository
from app.llm.base import LLMClient
from app.models import AgentRun


class DraftingService:
    def __init__(self, store: FixtureStore, repo: RunRepository, llm: LLMClient,
                 inject_failure_for: str | None = None) -> None:
        self._store, self._repo, self._llm = store, repo, llm
        self._inject_failure_for = inject_failure_for or None

    def create_draft(self, conversation_id: str, instructions: str | None = None) -> AgentRun:
        """Run the agent for a conversation. A failed run is still returned, not raised."""
        conversation = self._store.get_conversation(conversation_id)  # RecordNotFoundError -> 404
        tools: ToolExecutor = CandidateScopedTools(ToolRegistry(self._store),
                                                   conversation.candidate_id)
        if conversation.candidate_id == self._inject_failure_for:
            tools = FailingTools(tools)  # demo/E2E: interview lookups always fail for this candidate
        return run_agent(llm=self._llm, tools=tools, repo=self._repo,
                         conversation=conversation, instructions=instructions)
