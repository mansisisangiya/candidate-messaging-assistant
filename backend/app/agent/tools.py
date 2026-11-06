"""Read-only tools the agent can call. Each tool = name, description, input model, function.

The registry validates raw (LLM-supplied) arguments, runs the tool, and returns plain
JSON-able dicts. It knows nothing about the agent loop or the LLM.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.data.store import FixtureStore
from app.errors import ToolInputError, UnknownToolError
from app.models import GetCandidateInput, GetInterviewStatusInput, GetJobInput


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[[Any], BaseModel]

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_model.model_json_schema(),
        }


class ToolRegistry:
    def __init__(self, store: FixtureStore) -> None:
        tools = [
            Tool("get_candidate", "Get a candidate's name, email, job id and pipeline stage.",
                 GetCandidateInput, lambda a: store.get_candidate(a.candidate_id)),
            Tool("get_interview_status",
                 "Get a candidate's interview status, date and interviewer.",
                 GetInterviewStatusInput, lambda a: store.get_interview(a.candidate_id)),
            Tool("get_job", "Get a job's title, team and location.",
                 GetJobInput, lambda a: store.get_job(a.job_id)),
        ]
        self._tools = {t.name: t for t in tools}

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def execute(self, name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
        """Validate args, run the tool. Raises ToolInputError, UnknownToolError or RecordNotFoundError."""
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(f"Unknown tool '{name}'")
        try:
            args = tool.input_model.model_validate(raw_args)
        except ValidationError as exc:
            raise ToolInputError(f"Invalid arguments for {name}: {exc.errors()[0]['msg']} "
                                 f"({exc.errors()[0]['loc']})") from exc
        return tool.run(args).model_dump(mode="json")


class CandidateScopedTools:
    """Wraps a registry so tools can only read the candidate of the current conversation.

    The LLM chooses tool arguments, and a prompt-injected transcript could make it ask about
    someone else. Enforcing the scope here, in code, does not depend on the model behaving.
    """

    def __init__(self, registry: ToolRegistry, candidate_id: str) -> None:
        self._registry = registry
        self._candidate_id = candidate_id

    def schemas(self) -> list[dict[str, Any]]:
        return self._registry.schemas()

    def execute(self, name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
        requested = raw_args.get("candidate_id")
        if requested is not None and requested != self._candidate_id:
            raise ToolInputError("candidate_id must be the candidate of this conversation")
        return self._registry.execute(name, raw_args)
