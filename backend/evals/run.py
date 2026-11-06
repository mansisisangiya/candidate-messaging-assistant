"""Eval harness: run every case through the real DraftingService and enforce a pass rate.

    python -m evals.run [--threshold 1.0] [--cases path/to/cases.yaml]

Exits 0 if (passed cases / all cases) >= threshold, else 1. Uses FakeLLM only (default
policy or a script written in the case), so it needs no network and is deterministic.
This validates the pipeline (tools, state, guardrails, degradation), not model quality.
"""
import argparse
import json
import logging
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_drafting_service
from app.config import Settings
from app.data.store import FixtureStore
from app.db.repo import RunRepository
from app.llm.base import LLMResponse, ToolCall
from app.llm.fake import FakeLLM
from app.models import AgentRun, StepType

# FakeLLM has no randomness, so any failing case is a real regression: require all of them.
# A live-model run (not built) is non-deterministic and would use a lower value, e.g. 0.8.
DEFAULT_THRESHOLD = 1.0
DEFAULT_CASES = Path(__file__).with_name("cases.yaml")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScriptToolCall(_Strict):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ScriptItem(_Strict):
    content: str | None = None
    tool_call: ScriptToolCall | None = None

    def to_response(self, n: int) -> LLMResponse:
        if self.tool_call is not None:
            call = ToolCall(id=f"call_{n}", name=self.tool_call.name,
                            arguments=self.tool_call.arguments)
            return LLMResponse(tool_calls=[call])
        return LLMResponse(content=self.content)


class Check(_Strict):
    type: Literal["status", "contains", "not_contains", "max_length", "step_types", "error_steps",
                  "has_draft"]
    equals: str | list[str] | None = None  # status, step_types
    values: list[str] = Field(default_factory=list)  # contains, not_contains
    where: Literal["draft", "error", "run"] = Field(default="draft", alias="in")
    value: int | None = None  # max_length
    count: int | None = None  # error_steps
    present: bool | None = None  # has_draft


class Case(_Strict):
    id: str
    conversation_id: str
    instructions: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    script: list[ScriptItem] | None = None
    checks: list[Check]


class Result(BaseModel):
    case_id: str
    reasons: list[str]  # empty = passed

    @property
    def passed(self) -> bool:
        return not self.reasons


# ---- checks: one function each; each returns a failure reason or None ----

def _text(run: AgentRun, where: str) -> str:
    if where == "draft":
        return run.draft_text or ""
    if where == "error":
        return run.error or ""
    return json.dumps(run.model_dump(mode="json"))  # whole run: draft, steps, errors


def check_status(run: AgentRun, c: Check) -> str | None:
    return None if run.status == c.equals else f"status is '{run.status}', expected '{c.equals}'"


def check_contains(run: AgentRun, c: Check) -> str | None:
    text = _text(run, c.where).lower()
    missing = [v for v in c.values if v.lower() not in text]
    return f"{c.where} is missing {missing}" if missing else None


def check_not_contains(run: AgentRun, c: Check) -> str | None:
    text = _text(run, c.where).lower()
    found = [v for v in c.values if v.lower() in text]
    return f"{c.where} contains forbidden {found}" if found else None


def check_max_length(run: AgentRun, c: Check) -> str | None:
    length = len(run.draft_text or "")
    return None if length <= (c.value or 0) else f"draft is {length} characters (max {c.value})"


def check_step_types(run: AgentRun, c: Check) -> str | None:
    actual = [s.type.value for s in run.steps]
    if [s.index for s in run.steps] != list(range(len(run.steps))):
        return f"step indexes are {[s.index for s in run.steps]}, expected 0..{len(run.steps) - 1}"
    return None if actual == c.equals else f"step types are {actual}, expected {c.equals}"


def check_error_steps(run: AgentRun, c: Check) -> str | None:
    n = sum(1 for s in run.steps if s.type == StepType.ERROR)
    return None if n == c.count else f"{n} error steps, expected {c.count}"


def check_has_draft(run: AgentRun, c: Check) -> str | None:
    has = run.draft_text is not None
    return None if has == c.present else f"draft_text stored: {has}, expected {c.present}"


CHECKS: dict[str, Callable[[AgentRun, Check], str | None]] = {
    "status": check_status, "contains": check_contains, "not_contains": check_not_contains,
    "max_length": check_max_length, "step_types": check_step_types,
    "error_steps": check_error_steps, "has_draft": check_has_draft,
}


# ---- running ----

def load_cases(path: Path) -> list[Case]:
    return [Case.model_validate(item) for item in yaml.safe_load(path.read_text())]


def run_case(case: Case, store: FixtureStore, repo: RunRepository) -> Result:
    llm = FakeLLM([item.to_response(n) for n, item in enumerate(case.script)]
                  if case.script is not None else None)
    # Same wiring as the API, but hermetic: ignore the real environment and any .env file
    # (explicit init values win over env vars), so only the case's own env overrides apply.
    overrides = {"inject_interview_failure_for": ""} | {k.lower(): v for k, v in case.env.items()}
    settings = Settings(_env_file=None, **overrides)
    service = get_drafting_service(store, repo, llm, settings)
    try:
        run = service.create_draft(case.conversation_id, case.instructions)
    except Exception as exc:  # noqa: BLE001 - a crashing case is a failed case, not a crashed harness
        return Result(case_id=case.id, reasons=[f"raised {type(exc).__name__}: {exc}"])
    failures = ((c, CHECKS[c.type](run, c)) for c in case.checks)
    return Result(case_id=case.id, reasons=[f"{c.type}: {r}" for c, r in failures if r])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AI eval cases against FakeLLM.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="minimum pass rate, 0-1 (default %(default)s)")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    store = FixtureStore()
    logging.disable(logging.CRITICAL)  # keep the report readable; restored below
    try:
        with tempfile.TemporaryDirectory() as tmp:
            repo = RunRepository(Path(tmp) / "eval.db")
            results = [run_case(case, store, repo) for case in cases]
    finally:
        logging.disable(logging.NOTSET)

    for result in results:
        print(f"{'PASS' if result.passed else 'FAIL'}  {result.case_id}")
        for reason in result.reasons:
            print(f"        - {reason}")
    passed = sum(r.passed for r in results)
    rate = passed / len(results)
    ok = rate >= args.threshold
    print(f"\nPass rate: {passed}/{len(results)} = {rate:.0%} "
          f"(threshold {args.threshold:.0%}) -> {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
