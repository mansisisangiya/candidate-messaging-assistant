"""The status write is conditional, so a stale or concurrent writer is rejected."""
import pytest

from app.db.repo import RunRepository
from app.errors import InvalidTransition
from app.models import RunStatus
from app.services.run_state import transition


def test_update_status_if_rejects_a_stale_expected_status(repo):
    run = repo.create_run("conv_priya")
    assert repo.update_status_if(run.id, RunStatus.RUNNING, RunStatus.FAILED, error="boom")
    # A second writer still believes the run is "running".
    assert not repo.update_status_if(run.id, RunStatus.RUNNING, RunStatus.AWAITING_APPROVAL,
                                     draft_text="late")
    saved = repo.get_run(run.id)
    assert (saved.status, saved.error, saved.draft_text) == (RunStatus.FAILED, "boom", None)


class StaleReadRepo(RunRepository):
    """Simulates a race: reads return an out-of-date snapshot saying the run is still running."""

    def get_run(self, run_id):
        run = super().get_run(run_id)
        return run.model_copy(update={"status": RunStatus.RUNNING})


def test_transition_rejects_when_the_run_changed_after_it_was_read(tmp_path):
    repo = StaleReadRepo(tmp_path / "race.db")
    run = repo.create_run("conv_priya")
    assert repo.update_status_if(run.id, RunStatus.RUNNING, RunStatus.FAILED, error="boom")

    with pytest.raises(InvalidTransition, match="changed concurrently"):
        transition(repo, run.id, RunStatus.AWAITING_APPROVAL, draft_text="late")

    row = RunRepository(tmp_path / "race.db").get_run(run.id)
    assert (row.status, row.draft_text) == (RunStatus.FAILED, None)
