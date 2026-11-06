r"""The run state machine: the only place that decides which status changes are legal.

    running -> awaiting_approval -> approved
       |                        \-> rejected
       \-> failed

Approved, rejected and failed are terminal: no transitions out, not even to themselves.
"""
import logging

from app.db.repo import RunRepository
from app.errors import InvalidTransition
from app.logging_config import bind_run_id
from app.models import AgentRun, RunStatus

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.RUNNING: frozenset({RunStatus.AWAITING_APPROVAL, RunStatus.FAILED}),
    RunStatus.AWAITING_APPROVAL: frozenset({RunStatus.APPROVED, RunStatus.REJECTED}),
    RunStatus.APPROVED: frozenset(),
    RunStatus.REJECTED: frozenset(),
    RunStatus.FAILED: frozenset(),
}


def transition(repo: RunRepository, run_id: str, to: RunStatus, **fields: str | None) -> AgentRun:
    """Move a run to `to`, writing `fields` in the same statement.

    Raises RecordNotFoundError for an unknown run and InvalidTransition if the move is not
    allowed or the run changed since we read it (the write is conditional on the old status).
    """
    with bind_run_id(run_id):  # approve/reject run outside run_agent, so bind here too
        current = repo.get_run(run_id).status
        if to not in ALLOWED_TRANSITIONS[current]:
            logger.warning("invalid transition rejected",
                           extra={"from_status": current, "to_status": to})
            raise InvalidTransition(f"Cannot move a run from '{current}' to '{to}'")
        if not repo.update_status_if(run_id, current, to, **fields):
            logger.warning("stale transition rejected",
                           extra={"from_status": current, "to_status": to})
            raise InvalidTransition(
                f"Run {run_id} changed concurrently; it is no longer '{current}'")
        logger.info("run transition", extra={"from_status": current, "to_status": to})
        return repo.get_run(run_id)
