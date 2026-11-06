"""Recruiter decisions on a draft. Nothing is sent: approving only marks the text ready to send."""
from app.db.repo import RunRepository
from app.models import AgentRun, RunStatus
from app.services.run_state import transition


class ApprovalService:
    def __init__(self, repo: RunRepository) -> None:
        self._repo = repo

    def approve(self, run_id: str, edited_text: str | None = None) -> AgentRun:
        """final_text is the recruiter's edit if given, otherwise the draft unchanged.

        Illegal states (already decided, failed) raise InvalidTransition (409) from
        transition(); this method does no status checks of its own.
        """
        run = self._repo.get_run(run_id)  # RecordNotFoundError -> 404
        return transition(self._repo, run_id, RunStatus.APPROVED,
                          final_text=edited_text or run.draft_text)

    def reject(self, run_id: str, reason: str) -> AgentRun:
        return transition(self._repo, run_id, RunStatus.REJECTED, rejection_reason=reason)
