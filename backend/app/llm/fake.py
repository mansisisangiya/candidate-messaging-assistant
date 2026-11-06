"""Deterministic LLM used by default, in tests and in CI. No network, no API key.

Two modes:
- default policy: reads the message history, calls the three tools in a fixed order,
  then writes a template draft from the tool results. It proves the orchestration,
  not model quality.
- script: returns the given responses in order (an `Exception` item is raised).
  Tests use this to force bad behaviour (invalid args, endless tool calls, errors).
"""
import json
import re
from typing import Any

from app.errors import LLMError
from app.llm.base import ChatMessage, LLMResponse, ToolCall

CANDIDATE_ID_PATTERN = re.compile(r"^Candidate ID: (\S+)", re.MULTILINE)


class FakeLLM:
    def __init__(self, script: list[LLMResponse | Exception] | None = None) -> None:
        self._script = list(script) if script is not None else None
        self.calls = 0  # how many times complete() was invoked

    def complete(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls += 1
        if self._script is None:
            return self._default_policy(messages)
        if not self._script:
            raise LLMError("FakeLLM script exhausted")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _default_policy(self, messages: list[ChatMessage]) -> LLMResponse:
        results = {m.name: json.loads(m.content or "{}") for m in messages if m.role == "tool"}
        candidate = _ok(results.get("get_candidate"))

        if "get_candidate" not in results:
            return _call(len(results), "get_candidate", {"candidate_id": _candidate_id(messages)})
        if "get_interview_status" not in results:
            return _call(len(results), "get_interview_status",
                         {"candidate_id": _candidate_id(messages)})
        if "get_job" not in results and candidate is not None:
            return _call(len(results), "get_job", {"job_id": candidate["job_id"]})
        return LLMResponse(content=_write_draft(candidate, _ok(results.get("get_job")),
                                                _ok(results.get("get_interview_status"))))


def _call(n: int, name: str, arguments: dict[str, Any]) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=f"call_{n}", name=name, arguments=arguments)])


def _candidate_id(messages: list[ChatMessage]) -> str:
    for m in messages:
        if m.role == "user" and m.content and (match := CANDIDATE_ID_PATTERN.search(m.content)):
            return match.group(1)
    raise LLMError("FakeLLM could not find a candidate id in the conversation")


def _ok(result: dict[str, Any] | None) -> dict[str, Any] | None:
    """A tool result, or None if the tool was not called or returned an error."""
    return None if result is None or "error" in result else result


def _write_draft(candidate: dict | None, job: dict | None, interview: dict | None) -> str:
    first_name = candidate["name"].split()[0] if candidate else "there"
    role = f" for the {job['title']} role" if job else ""
    lines = [f"Hi {first_name}, thank you for your message{role}."]
    lines.append(_interview_sentence(interview))
    lines.append("Please let me know if you have any other questions.")
    return " ".join(lines)


def _interview_sentence(interview: dict | None) -> str:
    # With no interview data we make no promises about dates.
    if interview is None:
        return "I'm checking on the interview details and will confirm them shortly."
    status, when, who = interview["status"], interview["scheduled_at"], interview["interviewer"]
    if status == "scheduled":
        return f"Your interview is scheduled for {when[:10]} at {when[11:16]} UTC with {who}."
    if status in ("completed", "pending_feedback"):
        return "Your interview is complete and the team is reviewing feedback. I will update you soon."
    return "Your interview has not been scheduled yet; I will be in touch with next steps."
