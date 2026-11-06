"""Tools + real fixtures + SQLite together: tool calls and results recorded as run steps."""
from datetime import UTC, datetime

from app.errors import RecordNotFoundError
from app.models import AgentStep, StepType


def test_tool_calls_can_be_recorded_as_steps(registry, repo, store):
    conv = store.get_conversation("conv_priya")
    run = repo.create_run(conv.id)
    args = {"candidate_id": conv.candidate_id}
    result = registry.execute("get_interview_status", args)
    now = datetime.now(UTC)
    repo.add_step(run.id, AgentStep(index=0, type=StepType.TOOL_CALL,
                                    name="get_interview_status", input=args, ts=now))
    repo.add_step(run.id, AgentStep(index=1, type=StepType.TOOL_RESULT,
                                    name="get_interview_status", output=result, ts=now))
    saved = repo.get_run(run.id).steps
    assert saved[1].output["status"] == "scheduled"


def test_failed_tool_can_be_recorded_as_error_step(registry, repo):
    run = repo.create_run("conv_x")
    try:
        registry.execute("get_candidate", {"candidate_id": "cand_nope"})
    except RecordNotFoundError as exc:
        repo.add_step(run.id, AgentStep(index=0, type=StepType.ERROR, name="get_candidate",
                                        error=exc.message, ts=datetime.now(UTC)))
    assert "cand_nope" in repo.get_run(run.id).steps[0].error
