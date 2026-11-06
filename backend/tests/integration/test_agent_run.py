"""Whole pipeline with the default FakeLLM policy: fixtures + real tools + SQLite."""
import pytest

from app.agent.loop import run_agent
from app.models import RunStatus, StepType


def _run(store, repo, registry, conv):
    from app.llm.fake import FakeLLM
    return run_agent(llm=FakeLLM(), tools=registry, repo=repo,
                     conversation=store.get_conversation(conv))


def test_priya_gets_interview_date_in_draft(store, repo, registry):
    run = _run(store, repo, registry, "conv_priya")
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert "Priya" in run.draft_text
    assert "2026-11-12 at 14:00 UTC with Daniel Okafor" in run.draft_text
    assert "Senior Backend Engineer" in run.draft_text


def test_steps_are_ordered_and_persisted(store, repo, registry):
    run = _run(store, repo, registry, "conv_priya")
    expected = [(StepType.TOOL_CALL, "get_candidate"), (StepType.TOOL_RESULT, "get_candidate"),
                (StepType.TOOL_CALL, "get_interview_status"),
                (StepType.TOOL_RESULT, "get_interview_status"),
                (StepType.TOOL_CALL, "get_job"), (StepType.TOOL_RESULT, "get_job"),
                (StepType.LLM_MESSAGE, None)]
    assert [(s.type, s.name) for s in run.steps] == expected
    assert [s.index for s in run.steps] == list(range(7))
    assert repo.get_run(run.id) == run  # what was returned is what was saved


@pytest.mark.parametrize(("conv", "phrase"), [
    ("conv_marcus", "team is reviewing feedback"),
    ("conv_elena", "has not been scheduled yet"),
    ("conv_tom", "team is reviewing feedback"),
])
def test_each_fixture_conversation_produces_a_draft(store, repo, registry, conv, phrase):
    run = _run(store, repo, registry, conv)
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert phrase in run.draft_text


def test_draft_does_not_invent_compensation(store, repo, registry):
    run = _run(store, repo, registry, "conv_tom")  # candidate asked about salary
    assert "salary" not in run.draft_text.lower()
    assert "£" not in run.draft_text


def test_runs_are_listed_per_conversation(store, repo, registry):
    _run(store, repo, registry, "conv_priya")
    _run(store, repo, registry, "conv_tom")
    assert len(repo.list_runs("conv_priya")) == 1
