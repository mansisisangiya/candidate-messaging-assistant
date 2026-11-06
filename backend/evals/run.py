"""Eval harness: run every case through the real DraftingService and enforce a pass rate.

    python -m evals.run [--threshold 1.0] [--repeat N] [--cases path/to/cases.yaml]

Exits 0 if (passed case runs / all case runs) >= threshold, else 1. Prints each case, a
table per criterion and the overall pass rate. Uses FakeLLM only (default policy or a
script written in the case), so it needs no network and is deterministic.
This validates the pipeline (tools, state, guardrails, degradation), not model quality.
`--repeat N` runs every case N times and lists cases whose result differs between runs:
with FakeLLM there are none; it is the hook for measuring variance with a live model.
"""
import argparse
import json
import logging
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_drafting_service
from app.config import Settings
from app.data.store import FIXTURE_DIR, FixtureStore
from app.db.repo import RunRepository
from app.errors import LLMError
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
    llm_error: str | None = None  # the "model" fails with this message

    def to_step(self, n: int) -> LLMResponse | Exception:
        if self.llm_error is not None:
            return LLMError(self.llm_error)
        if self.tool_call is not None:
            call = ToolCall(id=f"call_{n}", name=self.tool_call.name,
                            arguments=self.tool_call.arguments)
            return LLMResponse(tool_calls=[call])
        return LLMResponse(content=self.content)


class Check(_Strict):
    type: Literal["status", "contains", "not_contains", "max_length", "step_types", "error_steps",
                  "has_draft", "grounded_in_tools", "addresses_topic", "tool_calls"]
    equals: str | list[str] | None = None  # status, step_types
    values: list[str] = Field(default_factory=list)  # contains/not_contains: all; addresses_topic: any
    where: Literal["draft", "error", "run"] = Field(default="draft", alias="in")
    value: int | None = None  # max_length
    count: int | None = None  # error_steps
    present: bool | None = None  # has_draft
    candidate_id: str | None = None  # tool_calls: required candidate_id argument
    job_id: str | None = None  # tool_calls: required job_id argument for get_job


Criterion = Literal["task_completion", "groundedness", "relevance", "tool_accuracy", "safety",
                    "failure_handling"]
CRITERIA: tuple[str, ...] = ("task_completion", "groundedness", "relevance", "tool_accuracy",
                             "safety", "failure_handling")


class Case(_Strict):
    id: str
    criterion: Criterion
    conversation_id: str
    candidate_message: str | None = None  # extra candidate message appended to the transcript
    instructions: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    script: list[ScriptItem] | None = None
    checks: list[Check]


class Result(BaseModel):
    case_id: str
    criterion: str = ""
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


DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
TIME_PATTERN = re.compile(r"\b\d{1,2}:\d{2}\b")


@lru_cache
def _known_names() -> frozenset[str]:
    """Every interviewer name and job title in the fixtures: the facts we can verify."""
    names: set[str] = set()
    for filename, field in (("interviews.json", "interviewer"), ("jobs.json", "title")):
        for record in json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8")):
            if record.get(field):
                names.add(record[field])
    return frozenset(names)


def check_grounded_in_tools(run: AgentRun, c: Check) -> str | None:
    """Every date, time, interviewer and job title in the draft must appear in a tool_result."""
    draft = run.draft_text or ""
    tool_text = " ".join(json.dumps(s.output) for s in run.steps
                         if s.type == StepType.TOOL_RESULT and s.output).lower()
    claims = DATE_PATTERN.findall(draft) + TIME_PATTERN.findall(draft)
    claims += [name for name in _known_names() if name.lower() in draft.lower()]
    ungrounded = [claim for claim in claims if claim.lower() not in tool_text]
    return f"not in any tool result: {ungrounded}" if ungrounded else None


def check_addresses_topic(run: AgentRun, c: Check) -> str | None:
    """Keyword proxy for relevance: the draft mentions at least one of the topic keywords.

    This is deliberately crude (it cannot tell a good answer from a keyword mention).
    """
    text = (run.draft_text or "").lower()
    return None if any(v.lower() in text for v in c.values) else f"draft mentions none of {c.values}"


def check_tool_calls(run: AgentRun, c: Check) -> str | None:
    calls = [s for s in run.steps if s.type == StepType.TOOL_CALL]
    names = [s.name for s in calls]
    if c.equals is not None and names != c.equals:
        return f"tool calls were {names}, expected {c.equals}"
    for call in calls:
        args = call.input or {}
        if c.candidate_id and call.name in ("get_candidate", "get_interview_status") \
                and args.get("candidate_id") != c.candidate_id:
            return f"{call.name} called with candidate_id={args.get('candidate_id')!r}"
        if c.job_id and call.name == "get_job" and args.get("job_id") != c.job_id:
            return f"get_job called with job_id={args.get('job_id')!r}"
    return None


CHECKS: dict[str, Callable[[AgentRun, Check], str | None]] = {
    "status": check_status, "contains": check_contains, "not_contains": check_not_contains,
    "max_length": check_max_length, "step_types": check_step_types,
    "error_steps": check_error_steps, "has_draft": check_has_draft,
    "grounded_in_tools": check_grounded_in_tools, "addresses_topic": check_addresses_topic,
    "tool_calls": check_tool_calls,
}


# ---- running ----

def load_cases(path: Path) -> list[Case]:
    return [Case.model_validate(item) for item in yaml.safe_load(path.read_text())]


def _store_for(case: Case, workdir: Path) -> FixtureStore:
    """The real fixtures, plus the case's extra candidate message (e.g. a prompt injection)."""
    if case.candidate_message is None:
        return FixtureStore()
    copy = Path(tempfile.mkdtemp(dir=workdir, prefix="fixtures_"))  # unique even when repeated
    shutil.copytree(FIXTURE_DIR, copy, dirs_exist_ok=True)
    path = copy / "conversations.json"
    conversations = json.loads(path.read_text(encoding="utf-8"))
    for conv in conversations:
        if conv["id"] == case.conversation_id:
            conv["messages"].append({"sender": "candidate", "text": case.candidate_message,
                                     "sent_at": "2026-11-06T09:00:00Z"})
    path.write_text(json.dumps(conversations), encoding="utf-8")
    return FixtureStore(copy)


def run_case(case: Case, repo: RunRepository, workdir: Path) -> Result:
    llm = FakeLLM([item.to_step(n) for n, item in enumerate(case.script)]
                  if case.script is not None else None)
    # Same wiring as the API, but hermetic: ignore the real environment and any .env file
    # (explicit init values win over env vars), so only the case's own env overrides apply.
    overrides = {"inject_interview_failure_for": ""} | {k.lower(): v for k, v in case.env.items()}
    settings = Settings(_env_file=None, **overrides)
    service = get_drafting_service(_store_for(case, workdir), repo, llm, settings)
    try:
        run = service.create_draft(case.conversation_id, case.instructions)
    except Exception as exc:  # noqa: BLE001 - a crashing case is a failed case, not a crashed harness
        return Result(case_id=case.id, criterion=case.criterion,
                      reasons=[f"raised {type(exc).__name__}: {exc}"])
    failures = ((c, CHECKS[c.type](run, c)) for c in case.checks)
    return Result(case_id=case.id, criterion=case.criterion,
                  reasons=[f"{c.type}: {r}" for c, r in failures if r])


def evaluate(cases: list[Case], repeat: int = 1) -> list[list[Result]]:
    """Run every case `repeat` times; returns one list of results per repetition."""
    logging.disable(logging.CRITICAL)  # keep the report readable; restored below
    try:
        with tempfile.TemporaryDirectory() as tmp:
            repo = RunRepository(Path(tmp) / "eval.db")
            return [[run_case(case, repo, Path(tmp)) for case in cases] for _ in range(repeat)]
    finally:
        logging.disable(logging.NOTSET)


def flaky_cases(runs: list[list[Result]]) -> list[str]:
    """Ids of cases whose outcome (pass/fail and reasons) differs between repetitions."""
    outcomes: dict[str, set[tuple[str, ...]]] = {}
    for results in runs:
        for r in results:
            outcomes.setdefault(r.case_id, set()).add(tuple(r.reasons))
    return [case_id for case_id, seen in outcomes.items() if len(seen) > 1]


def criterion_table(runs: list[list[Result]]) -> list[str]:
    """Lines of `criterion  passed/total` over all case runs, in the fixed criterion order."""
    lines = [f"{'criterion':<17} passed/total"]
    for criterion in CRITERIA:
        results = [r for results in runs for r in results if r.criterion == criterion]
        if results:
            lines.append(f"{criterion:<17} {sum(r.passed for r in results)}/{len(results)}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AI eval cases against FakeLLM.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="minimum pass rate, 0-1 (default %(default)s)")
    parser.add_argument("--repeat", type=int, default=1, help="run every case N times")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    cases = load_cases(args.cases)
    runs = evaluate(cases, args.repeat)

    for result in runs[0]:
        print(f"{'PASS' if result.passed else 'FAIL'}  [{result.criterion}] {result.case_id}")
        for reason in result.reasons:
            print(f"        - {reason}")
    flaky = flaky_cases(runs)
    for result in (r for results in runs[1:] for r in results if not r.passed):
        if result.case_id not in flaky:  # consistently failing in later runs: already shown above
            continue
        print(f"FAIL  (repeat) {result.case_id}: {'; '.join(result.reasons)}")
    print("\n" + "\n".join(criterion_table(runs)))
    if args.repeat > 1:
        print(f"\nRepeated {args.repeat}x; flaky cases: {', '.join(flaky) if flaky else 'none'}")

    all_results = [r for results in runs for r in results]
    passed = sum(r.passed for r in all_results)
    rate = passed / len(all_results)
    ok = rate >= args.threshold
    print(f"\nPass rate: {passed}/{len(all_results)} = {rate:.0%} "
          f"(threshold {args.threshold:.0%}) -> {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
