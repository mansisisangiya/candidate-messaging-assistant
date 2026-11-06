"""The agent loop: ask the LLM, run the tools it requests, repeat until it returns a draft.

Every step is written to SQLite as it happens, so a failed run still has a trace.
The run ends as `awaiting_approval` (draft ready) or `failed`.
"""
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, Protocol

from app.agent.prompt import build_messages
from app.db.repo import RunRepository
from app.errors import AppError, LLMError, MaxStepsExceededError, ToolUnavailableError
from app.llm.base import ChatMessage, LLMClient, ToolCall
from app.models import AgentRun, AgentStep, Conversation, RunStatus, StepType

logger = logging.getLogger(__name__)

MAX_STEPS = 6  # maximum LLM calls per run


class ToolExecutor(Protocol):
    def schemas(self) -> list[dict[str, Any]]: ...
    def execute(self, name: str, raw_args: dict[str, Any]) -> dict[str, Any]: ...


class _Recorder:
    """Persists steps with a running index."""

    def __init__(self, repo: RunRepository, run_id: str) -> None:
        self._repo, self._run_id, self._next = repo, run_id, 0

    def record(self, type_: StepType, duration_ms: int = 0, **fields: Any) -> None:
        step = AgentStep(index=self._next, type=type_, duration_ms=duration_ms,
                         ts=datetime.now(UTC), **fields)
        self._repo.add_step(self._run_id, step)
        self._next += 1


def run_agent(
    *,
    llm: LLMClient,
    tools: ToolExecutor,
    repo: RunRepository,
    conversation: Conversation,
    instructions: str | None = None,
) -> AgentRun:
    run = repo.create_run(conversation.id, instructions)
    log = {"run_id": run.id}
    logger.info("run started", extra=log)
    try:
        draft = _loop(llm, tools, _Recorder(repo, run.id), build_messages(conversation, instructions))
    except Exception as exc:
        message = exc.message if isinstance(exc, AppError) else "Unexpected internal error"
        if not isinstance(exc, AppError):
            logger.exception("run crashed", extra=log)
        logger.warning("run failed: %s", message, extra=log)
        return repo.update_run(run.id, status=RunStatus.FAILED, error=message)
    logger.info("run awaiting approval", extra=log)
    return repo.update_run(run.id, status=RunStatus.AWAITING_APPROVAL, draft_text=draft)


def _loop(llm: LLMClient, tools: ToolExecutor, recorder: _Recorder,
          messages: list[ChatMessage]) -> str:
    for _ in range(MAX_STEPS):
        response = llm.complete(messages, tools.schemas())
        if response.tool_calls:
            messages.append(ChatMessage(role="assistant", content=response.content,
                                        tool_calls=response.tool_calls))
            for call in response.tool_calls:
                messages.append(_run_tool(tools, recorder, call))
            continue
        draft = (response.content or "").strip()
        if not draft:
            raise LLMError("LLM returned neither tool calls nor a draft")
        recorder.record(StepType.LLM_MESSAGE, output={"text": draft})
        return draft
    raise MaxStepsExceededError(f"No draft produced after {MAX_STEPS} LLM calls")


def _run_tool(tools: ToolExecutor, recorder: _Recorder, call: ToolCall) -> ChatMessage:
    """Run one tool call. Tool errors are recorded and fed back to the LLM, not raised."""
    recorder.record(StepType.TOOL_CALL, name=call.name, input=call.arguments)
    started = time.perf_counter()
    try:
        try:
            result = tools.execute(call.name, call.arguments)
        except ToolUnavailableError:  # transient: retry once
            result = tools.execute(call.name, call.arguments)
    except AppError as exc:
        recorder.record(StepType.ERROR, _elapsed_ms(started), name=call.name,
                        error=f"{exc.code}: {exc.message}")
        payload: dict[str, Any] = {"error": {"code": exc.code, "message": exc.message}}
    else:
        recorder.record(StepType.TOOL_RESULT, _elapsed_ms(started), name=call.name, output=result)
        payload = result
    return ChatMessage(role="tool", name=call.name, tool_call_id=call.id,
                       content=json.dumps(payload))


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
