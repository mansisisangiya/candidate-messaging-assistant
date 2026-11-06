from app.agent.loop import run_agent
from app.agent.tools import CandidateScopedTools, ToolRegistry
from app.data.store import FixtureStore
from app.db.repo import RunRepository
from app.llm.base import LLMClient
from app.models import AgentRun


class DraftingService:
    def __init__(self, store: FixtureStore, repo: RunRepository, llm: LLMClient) -> None:
        self._store, self._repo, self._llm = store, repo, llm

    def create_draft(self, conversation_id: str, instructions: str | None = None) -> AgentRun:
        """Run the agent for a conversation. A failed run is still returned, not raised."""
        conversation = self._store.get_conversation(conversation_id)  # RecordNotFoundError -> 404
        tools = CandidateScopedTools(ToolRegistry(self._store), conversation.candidate_id)
        return run_agent(llm=self._llm, tools=tools, repo=self._repo,
                         conversation=conversation, instructions=instructions)
