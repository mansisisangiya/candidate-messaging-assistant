import json

import pytest

from app.agent.prompt import build_messages
from app.errors import LLMError
from app.llm.base import ChatMessage, LLMResponse
from app.llm.fake import FakeLLM


def _messages(store, conv_id="conv_priya"):
    return build_messages(store.get_conversation(conv_id), None)


def _tool_msg(name: str, payload: dict) -> ChatMessage:
    return ChatMessage(role="tool", name=name, tool_call_id="x", content=json.dumps(payload))


def test_default_policy_calls_tools_in_order(store):
    llm = FakeLLM()
    messages = _messages(store)
    first = llm.complete(messages, [])
    assert first.tool_calls[0].name == "get_candidate"
    assert first.tool_calls[0].arguments == {"candidate_id": "cand_priya"}

    messages.append(_tool_msg("get_candidate", {"name": "Priya Sharma", "job_id": "job_backend"}))
    assert llm.complete(messages, []).tool_calls[0].name == "get_interview_status"

    messages.append(_tool_msg("get_interview_status", {"status": "not_scheduled",
                                                       "scheduled_at": None, "interviewer": None}))
    job_call = llm.complete(messages, []).tool_calls[0]
    assert (job_call.name, job_call.arguments) == ("get_job", {"job_id": "job_backend"})


def test_draft_uses_tool_facts(store):
    messages = _messages(store)
    messages += [
        _tool_msg("get_candidate", {"name": "Priya Sharma", "job_id": "job_backend"}),
        _tool_msg("get_interview_status", {"status": "scheduled", "interviewer": "Dan",
                                           "scheduled_at": "2026-11-12T14:00:00Z"}),
        _tool_msg("get_job", {"title": "Senior Backend Engineer"}),
    ]
    draft = FakeLLM().complete(messages, []).content
    assert "Priya" in draft
    assert "2026-11-12 at 14:00 UTC with Dan" in draft
    assert "Senior Backend Engineer" in draft


def test_draft_makes_no_date_promise_when_interview_lookup_failed(store):
    messages = _messages(store)
    messages += [
        _tool_msg("get_candidate", {"name": "Priya Sharma", "job_id": "job_backend"}),
        _tool_msg("get_interview_status", {"error": {"code": "tool_unavailable", "message": "x"}}),
        _tool_msg("get_job", {"title": "Senior Backend Engineer"}),
    ]
    draft = FakeLLM().complete(messages, []).content
    assert "2026" not in draft
    assert "checking on the interview details" in draft


def test_missing_candidate_id_raises_llm_error():
    with pytest.raises(LLMError):
        FakeLLM().complete([ChatMessage(role="user", content="hello")], [])


def test_script_mode_returns_in_order_and_raises_exceptions():
    llm = FakeLLM([LLMResponse(content="a"), LLMError("boom")])
    assert llm.complete([], []).content == "a"
    with pytest.raises(LLMError, match="boom"):
        llm.complete([], [])
    with pytest.raises(LLMError, match="exhausted"):
        llm.complete([], [])
    assert llm.calls == 3
