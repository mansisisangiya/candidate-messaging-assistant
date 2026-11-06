from datetime import UTC, datetime

import pytest

from app.db.repo import RunRepository
from app.errors import RecordNotFoundError
from app.models import AgentStep, RunStatus, StepType


def _step(index: int, type_: StepType = StepType.TOOL_CALL, **kw) -> AgentStep:
    return AgentStep(index=index, type=type_, ts=datetime.now(UTC), **kw)


def test_create_and_get_run(repo):
    run = repo.create_run("conv_priya", "be brief")
    loaded = repo.get_run(run.id)
    assert loaded.status == RunStatus.RUNNING
    assert loaded.conversation_id == "conv_priya"
    assert loaded.instructions == "be brief"
    assert loaded.steps == []


def test_steps_round_trip_in_order(repo):
    run = repo.create_run("conv_priya")
    repo.add_step(run.id, _step(1, StepType.TOOL_RESULT, name="get_job", output={"title": "X"}))
    repo.add_step(run.id, _step(0, name="get_job", input={"job_id": "job_data"}, duration_ms=3))
    steps = repo.get_run(run.id).steps
    assert [s.index for s in steps] == [0, 1]
    assert steps[0].input == {"job_id": "job_data"}
    assert steps[1].output == {"title": "X"}


def test_error_step_is_persisted(repo):
    run = repo.create_run("conv_tom")
    repo.add_step(run.id, _step(0, StepType.ERROR, name="get_interview_status", error="down"))
    assert repo.get_run(run.id).steps[0].error == "down"


def test_update_run(repo):
    run = repo.create_run("conv_priya")
    updated = repo.update_run(run.id, status=RunStatus.AWAITING_APPROVAL, draft_text="Hello")
    assert updated.status == RunStatus.AWAITING_APPROVAL
    assert updated.draft_text == "Hello"
    assert updated.updated_at >= run.updated_at


def test_update_run_rejects_unknown_or_empty_fields(repo):
    run = repo.create_run("conv_priya")
    with pytest.raises(ValueError):
        repo.update_run(run.id, id="other")
    with pytest.raises(ValueError):
        repo.update_run(run.id)


def test_missing_run_raises_not_found(repo):
    with pytest.raises(RecordNotFoundError):
        repo.get_run("nope")
    with pytest.raises(RecordNotFoundError):
        repo.add_step("nope", _step(0))
    with pytest.raises(RecordNotFoundError):
        repo.update_run("nope", status="failed")


def test_duplicate_step_index_is_rejected_and_rolled_back(repo):
    run = repo.create_run("conv_priya")
    repo.add_step(run.id, _step(0))
    with pytest.raises(Exception, match="UNIQUE"):
        repo.add_step(run.id, _step(0))
    assert len(repo.get_run(run.id).steps) == 1


def test_list_runs_filters_by_conversation_newest_first(repo):
    first = repo.create_run("conv_priya")
    repo.create_run("conv_tom")
    second = repo.create_run("conv_priya")
    assert [r.id for r in repo.list_runs("conv_priya")] == [second.id, first.id]
    assert len(repo.list_runs()) == 3


def test_data_persists_across_repository_instances(tmp_path):
    path = tmp_path / "persist.db"
    run = RunRepository(path).create_run("conv_priya")
    assert RunRepository(path).get_run(run.id).id == run.id
