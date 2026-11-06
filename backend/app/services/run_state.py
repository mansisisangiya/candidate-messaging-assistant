r"""The run state machine: the only place that decides which status changes are legal.

    running -> awaiting_approval -> approved
       |                        \-> rejected
       \-> failed

Approved, rejected and failed are terminal: no transitions out, not even to themselves.
"""
from app.db.repo import RunRepository
from app.errors import InvalidTransition
from app.models import AgentRun, RunStatus

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
    current = repo.get_run(run_id).status
    if to not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"Cannot move a run from '{current}' to '{to}'")
    if not repo.update_status_if(run_id, current, to, **fields):
        raise InvalidTransition(f"Run {run_id} changed concurrently; it is no longer '{current}'")
    return repo.get_run(run_id)
