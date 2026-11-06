"""Agent loop behaviour with scripted FakeLLM responses and a real temp SQLite database."""
from app.agent.loop import MAX_STEPS, MAX_TOOL_CALLS_PER_RESPONSE, run_agent
from app.errors import LLMError, ToolUnavailableError
from app.llm.base import LLMResponse, ToolCall
from app.llm.fake import FakeLLM
from app.models import RunStatus, StepType


def _call(name: str, **arguments) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id="c1", name=name, arguments=arguments)])


def _run(store, repo, registry, llm, conv="conv_priya", instructions=None):
    return run_agent(llm=llm, tools=registry, repo=repo, instructions=instructions,
                     conversation=store.get_conversation(conv))


def _types(run):
    return [s.type for s in run.steps]


def test_tool_call_then_draft(store, repo, registry):
    llm = FakeLLM([_call("get_job", job_id="job_data"), LLMResponse(content="  Hello!  ")])
    run = _run(store, repo, registry, llm)
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert run.draft_text == "Hello!"
    assert _types(run) == [StepType.TOOL_CALL, StepType.TOOL_RESULT, StepType.LLM_MESSAGE]
    assert run.steps[1].output["title"] == "Data Analyst"


def test_invalid_tool_arguments_become_error_step_and_agent_recovers(store, repo, registry):
    llm = FakeLLM([_call("get_job", wrong_arg="x"), _call("get_job", job_id="job_data"),
                   LLMResponse(content="Done")])
    run = _run(store, repo, registry, llm)
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert run.steps[1].type == StepType.ERROR
    assert run.steps[1].error.startswith("invalid_tool_input")


def test_unknown_record_and_unknown_tool_are_errors_not_crashes(store, repo, registry):
    llm = FakeLLM([_call("get_candidate", candidate_id="cand_nope"), _call("send_email"),
                   LLMResponse(content="Done")])
    run = _run(store, repo, registry, llm)
    assert run.status == RunStatus.AWAITING_APPROVAL
    errors = [s.error for s in run.steps if s.type == StepType.ERROR]
    assert errors[0].startswith("not_found")
    assert errors[1].startswith("unknown_tool")


def test_error_result_is_fed_back_to_the_llm(store, repo, registry):
    seen = []

    class SpyLLM(FakeLLM):
        def complete(self, messages, tools):
            seen.append([m.content for m in messages if m.role == "tool"])
            return super().complete(messages, tools)

    run = _run(store, repo, registry,
               SpyLLM([_call("get_job", job_id="nope"), LLMResponse(content="Done")]))
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert "not_found" in seen[1][0]


class FlakyTools:
    """Raises ToolUnavailableError `failures` times, then succeeds."""

    def __init__(self, failures: int) -> None:
        self.failures, self.attempts = failures, 0

    def schemas(self):
        return []

    def execute(self, name, raw_args):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ToolUnavailableError("interview system down")
        return {"status": "scheduled"}


def test_unavailable_tool_is_retried_once(store, repo):
    tools = FlakyTools(failures=1)
    llm = FakeLLM([_call("get_interview_status", candidate_id="cand_priya"),
                   LLMResponse(content="Done")])
    run = _run(store, repo, tools, llm)
    assert tools.attempts == 2
    assert _types(run) == [StepType.TOOL_CALL, StepType.ERROR, StepType.TOOL_RESULT,
                           StepType.LLM_MESSAGE]
    assert run.steps[1].error == "tool_unavailable: interview system down, retrying"


def test_unavailable_tool_after_retry_is_error_step_and_run_continues(store, repo):
    tools = FlakyTools(failures=5)
    llm = FakeLLM([_call("get_interview_status", candidate_id="cand_priya"),
                   LLMResponse(content="Done")])
    run = _run(store, repo, tools, llm)
    assert tools.attempts == 2  # one try plus exactly one retry
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert [s.type for s in run.steps[:3]] == [StepType.TOOL_CALL, StepType.ERROR, StepType.ERROR]
    assert run.steps[1].error.endswith("retrying")
    assert not run.steps[2].error.endswith("retrying")


def test_max_steps_marks_run_failed(store, repo, registry):
    llm = FakeLLM([_call("get_job", job_id="job_data")] * (MAX_STEPS + 3))
    run = _run(store, repo, registry, llm)
    assert run.status == RunStatus.FAILED
    assert "6 LLM calls" in run.error
    assert llm.calls == MAX_STEPS
    assert run.draft_text is None
    assert len(run.steps) == MAX_STEPS * 2  # trace kept for the failed run


def test_llm_error_marks_run_failed_with_trace_kept(store, repo, registry):
    llm = FakeLLM([_call("get_job", job_id="job_data"), LLMError("provider down")])
    run = _run(store, repo, registry, llm)
    assert run.status == RunStatus.FAILED
    assert run.error == "provider down"
    assert len(run.steps) == 2


def test_empty_llm_response_marks_run_failed(store, repo, registry):
    run = _run(store, repo, registry, FakeLLM([LLMResponse()]))
    assert run.status == RunStatus.FAILED
    assert "neither tool calls nor a draft" in run.error


def test_whitespace_only_draft_marks_run_failed(store, repo, registry):
    run = _run(store, repo, registry, FakeLLM([LLMResponse(content="   ")]))
    assert run.status == RunStatus.FAILED


def test_unexpected_exception_fails_run_without_leaking_details(store, repo, registry):
    run = _run(store, repo, registry, FakeLLM([RuntimeError("secret internal detail")]))
    assert run.status == RunStatus.FAILED
    assert run.error == "Unexpected internal error"


def test_instructions_are_persisted(store, repo, registry):
    run = _run(store, repo, registry, FakeLLM([LLMResponse(content="Hi")]),
               instructions="Keep it short")
    assert repo.get_run(run.id).instructions == "Keep it short"


class CrashingTools:
    def schemas(self):
        return []

    def execute(self, name, raw_args):
        raise RuntimeError("secret internal detail")


def test_non_app_error_in_a_tool_is_recorded_and_run_continues(store, repo):
    llm = FakeLLM([_call("get_job", job_id="job_data"), LLMResponse(content="Done")])
    run = _run(store, repo, CrashingTools(), llm)
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert run.steps[1].type == StepType.ERROR
    assert run.steps[1].error == "tool_failed: The tool failed unexpectedly"
    assert "secret" not in run.steps[1].error


def test_too_many_tool_calls_in_one_response_fails_the_run(store, repo):
    flaky = FlakyTools(failures=0)
    calls = [ToolCall(id=f"c{i}", name="get_job", arguments={"job_id": "job_data"})
             for i in range(MAX_TOOL_CALLS_PER_RESPONSE + 1)]
    run = _run(store, repo, flaky, FakeLLM([LLMResponse(tool_calls=calls)]))
    assert run.status == RunStatus.FAILED
    assert "5 tool calls in one response (maximum 4)" in run.error
    assert flaky.attempts == 0  # nothing was executed
    assert run.steps == []


def test_exactly_the_maximum_number_of_tool_calls_is_allowed(store, repo, registry):
    calls = [ToolCall(id=f"c{i}", name="get_job", arguments={"job_id": "job_data"})
             for i in range(MAX_TOOL_CALLS_PER_RESPONSE)]
    run = _run(store, repo, registry,
               FakeLLM([LLMResponse(tool_calls=calls), LLMResponse(content="Done")]))
    assert run.status == RunStatus.AWAITING_APPROVAL
