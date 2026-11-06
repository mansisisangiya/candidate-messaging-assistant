"""Deliberate tool failure, used to demonstrate and test graceful degradation."""
from typing import Any

from app.errors import ToolUnavailableError


class FailingTools:
    """Wraps a ToolExecutor so one tool always raises ToolUnavailableError.

    It fails on every call, so the loop's single retry fails too and the run has to
    carry on without that data.
    """

    def __init__(self, inner: Any, failing_tool: str = "get_interview_status") -> None:
        self._inner, self._failing_tool = inner, failing_tool

    def schemas(self) -> list[dict[str, Any]]:
        return self._inner.schemas()

    def execute(self, name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
        if name == self._failing_tool:
            raise ToolUnavailableError(f"{name} is temporarily unavailable")
        return self._inner.execute(name, raw_args)
