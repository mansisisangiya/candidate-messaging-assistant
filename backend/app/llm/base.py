"""The only interface the agent loop knows about. Providers implement `LLMClient`."""
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)  # assistant messages only
    tool_call_id: str | None = None  # tool messages only
    name: str | None = None  # tool messages only: which tool produced this


class LLMResponse(BaseModel):
    """Either tool calls (to continue) or final text content (the draft)."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMClient(Protocol):
    def complete(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> LLMResponse:
        """Raise `LLMError` on failure."""
        ...
