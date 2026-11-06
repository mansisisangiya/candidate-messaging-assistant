"""JSON log format, run_id correlation and the no-PII rule."""
import io
import json
import logging

import pytest

from app.agent.loop import run_agent
from app.api.deps import get_drafting_service
from app.config import Settings
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM
from app.logging_config import (
    JsonFormatter,
    RunIdFilter,
    bind_run_id,
    configure_logging,
    run_id_var,
)
from app.services.approval import ApprovalService


@pytest.fixture
def json_logs():
    """Route all logging through configure_logging into a buffer; yields a parser."""
    stream = io.StringIO()
    configure_logging("DEBUG", stream)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, "_cma_json_handler", False)]:
        root.removeHandler(handler)


def _draft(store, repo, conv="conv_priya", llm=None, inject=""):
    settings = Settings(inject_interview_failure_for=inject)
    return get_drafting_service(store, repo, llm or FakeLLM(), settings).create_draft(conv)


def test_formatter_emits_valid_json_with_extras():
    record = logging.LogRecord("app.x", logging.WARNING, __file__, 1, "hello %s", ("world",), None)
    record.tool = "get_job"
    record.run_id = "abc"
    entry = json.loads(JsonFormatter().format(record))
    assert entry["message"] == "hello world"
    assert entry["level"] == "WARNING"
    assert entry["logger"] == "app.x"
    assert entry["run_id"] == "abc"
    assert entry["tool"] == "get_job"
    assert entry["timestamp"].endswith("+00:00")


def test_formatter_omits_run_id_when_none_and_includes_exceptions():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "bad", (), sys.exc_info())
    record.run_id = None
    entry = json.loads(JsonFormatter().format(record))
    assert "run_id" not in entry
    assert "ValueError: boom" in entry["exception"]


def test_run_id_is_on_every_loop_log_and_cleared_after(store, repo, caplog):
    caplog.handler.addFilter(RunIdFilter())  # caplog's handler is not ours, so install the filter
    with caplog.at_level(logging.INFO):
        run = _draft(store, repo)
        logging.getLogger("app.test").info("after the run")
    loop_records = [r for r in caplog.records if r.name != "app.test"]
    assert loop_records
    assert {r.run_id for r in loop_records} == {run.id}
    assert caplog.records[-1].run_id is None
    assert run_id_var.get() is None


def test_run_id_is_reset_even_when_the_run_crashes(store, repo):
    class Boom:
        def complete(self, messages, tools):
            raise RuntimeError("provider exploded")

    _draft(store, repo, llm=Boom())
    assert run_id_var.get() is None


def test_bind_run_id_restores_the_previous_value():
    with bind_run_id("outer"):
        with bind_run_id("inner"):
            assert run_id_var.get() == "inner"
        assert run_id_var.get() == "outer"
    assert run_id_var.get() is None


def test_successful_run_logs_start_completion_transition_with_duration(store, repo, json_logs):
    run = _draft(store, repo)
    entries = [e for e in json_logs() if e["run_id"] == run.id]
    messages = [e["message"] for e in entries]
    assert messages == ["run started", "run completed", "run transition"]
    completed = entries[1]
    assert completed["duration_ms"] >= 0
    assert completed["status"] == "awaiting_approval"
    assert (entries[2]["from_status"], entries[2]["to_status"]) == ("running", "awaiting_approval")


def test_tool_errors_are_logged_with_code_not_content(store, repo, json_logs):
    run = _draft(store, repo, inject="cand_priya")
    entries = [e for e in json_logs() if e.get("run_id") == run.id]
    retry = [e for e in entries if e["message"] == "tool unavailable, retrying"]
    errors = [e for e in entries if e["message"] == "tool error"]
    assert len(retry) == 1 and retry[0]["tool"] == "get_interview_status"
    assert errors[0]["error_code"] == "tool_unavailable"


def test_failed_run_and_guardrail_violation_are_logged(store, repo, json_logs):
    run = _draft(store, repo, llm=FakeLLM([LLMResponse(content="Hi [Name]")]))
    entries = [e for e in json_logs() if e.get("run_id") == run.id]
    messages = [e["message"] for e in entries]
    assert "guardrail violation" in messages
    failed = next(e for e in entries if e["message"] == "run failed")
    assert failed["level"] == "WARNING" and "placeholder" in failed["error"]
    assert "duration_ms" in failed


def test_approval_transition_is_logged_with_run_id(store, repo, json_logs):
    run = _draft(store, repo)
    ApprovalService(repo).reject(run.id, "too long")
    last = json_logs()[-1]
    assert last["message"] == "run transition" and last["run_id"] == run.id
    assert (last["from_status"], last["to_status"]) == ("awaiting_approval", "rejected")


def test_rejected_transition_is_logged(store, repo, json_logs):
    run = _draft(store, repo)
    ApprovalService(repo).approve(run.id)
    with pytest.raises(Exception, match="Cannot move"):
        ApprovalService(repo).approve(run.id)
    assert json_logs()[-1]["message"] == "invalid transition rejected"


@pytest.mark.parametrize(("conv", "inject"), [
    ("conv_priya", ""), ("conv_tom", ""), ("conv_priya", "cand_priya")])
def test_logs_never_contain_emails_or_message_text(store, repo, json_logs, conv, inject):
    run = _draft(store, repo, conv, inject=inject)
    ApprovalService(repo).approve(run.id, "Edited text that must not be logged")
    text = " ".join(json.dumps(e) for e in json_logs()).lower()
    conversation = store.get_conversation(conv)
    forbidden = [store.get_candidate(conversation.candidate_id).email.lower(),
                 "example.com", "edited text that must not", run.draft_text.lower()]
    forbidden += [m.text.lower() for m in conversation.messages]
    for fragment in forbidden:
        assert fragment not in text


def test_run_agent_accepts_logging_without_configuration(store, repo, registry):
    """Library code only calls logging.getLogger; it works with no handler set up."""
    run = run_agent(llm=FakeLLM(), tools=registry, repo=repo,
                    conversation=store.get_conversation("conv_elena"))
    assert run.status == "awaiting_approval"


def test_configure_logging_is_idempotent():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    configure_logging("INFO", stream)
    marked = [h for h in logging.getLogger().handlers if getattr(h, "_cma_json_handler", False)]
    assert len(marked) == 1
    logging.getLogger().removeHandler(marked[0])


def test_invalid_log_level_is_rejected_by_settings():
    with pytest.raises(ValueError):
        Settings(log_level="LOUD")
