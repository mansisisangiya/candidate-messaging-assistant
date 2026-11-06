"""Injected get_interview_status outage: the run degrades gracefully instead of failing."""
from app.llm.fake import FakeLLM
from app.models import RunStatus, StepType
from app.services.drafting import DraftingService


def _draft(store, repo, conv="conv_priya", inject="cand_priya"):
    return DraftingService(store, repo, FakeLLM(), inject_failure_for=inject).create_draft(conv)


def test_run_completes_with_both_error_steps_and_no_date_promise(store, repo):
    run = _draft(store, repo)
    assert run.status == RunStatus.AWAITING_APPROVAL
    errors = [s for s in run.steps if s.type == StepType.ERROR]
    assert [e.name for e in errors] == ["get_interview_status"] * 2
    assert errors[0].error == "tool_unavailable: get_interview_status is temporarily unavailable, retrying"
    assert errors[1].error == "tool_unavailable: get_interview_status is temporarily unavailable"
    assert not any(s.type == StepType.TOOL_RESULT and s.name == "get_interview_status"
                   for s in run.steps)
    assert "2026-11-12" not in run.draft_text  # Priya's real interview date
    assert "14:00" not in run.draft_text
    assert "will confirm them shortly" in run.draft_text


def test_other_tools_still_work_during_the_outage(store, repo):
    run = _draft(store, repo)
    results = {s.name for s in run.steps if s.type == StepType.TOOL_RESULT}
    assert results == {"get_candidate", "get_job"}


def test_other_candidates_are_unaffected(store, repo):
    run = _draft(store, repo, conv="conv_tom")
    assert not [s for s in run.steps if s.type == StepType.ERROR]


def test_injection_is_off_by_default(store, repo):
    run = DraftingService(store, repo, FakeLLM()).create_draft("conv_priya")
    assert "2026-11-12" in run.draft_text
    assert DraftingService(store, repo, FakeLLM(), inject_failure_for="").create_draft(
        "conv_priya").draft_text == run.draft_text
