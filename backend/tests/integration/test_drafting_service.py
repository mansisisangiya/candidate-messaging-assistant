import json

import pytest

from app.errors import RecordNotFoundError
from app.llm.base import LLMResponse, ToolCall
from app.llm.fake import FakeLLM
from app.models import RunStatus, StepType
from app.services.drafting import DraftingService


def test_create_draft_runs_the_agent(store, repo):
    run = DraftingService(store, repo, FakeLLM()).create_draft("conv_priya", "Be friendly")
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert run.instructions == "Be friendly"
    assert repo.get_run(run.id).draft_text == run.draft_text


def test_unknown_conversation_is_not_found_and_creates_no_run(store, repo):
    with pytest.raises(RecordNotFoundError):
        DraftingService(store, repo, FakeLLM()).create_draft("conv_nope")
    assert repo.list_runs() == []


def test_llm_asking_for_another_candidate_gets_an_error_and_no_data(store, repo):
    ask_other = LLMResponse(tool_calls=[
        ToolCall(id="c1", name="get_candidate", arguments={"candidate_id": "cand_tom"})])
    run = DraftingService(store, repo, FakeLLM([ask_other, LLMResponse(content="Hi")])
                          ).create_draft("conv_priya")
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert [s.type for s in run.steps[:2]] == [StepType.TOOL_CALL, StepType.ERROR]
    assert run.steps[1].error.startswith("invalid_tool_input")
    saved = json.dumps(run.model_dump(mode="json"))
    assert "Tom Becker" not in saved
    assert "tom.becker" not in saved
