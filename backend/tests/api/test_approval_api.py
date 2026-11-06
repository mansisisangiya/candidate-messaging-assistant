import pytest

from app.api.deps import get_settings
from app.config import Settings
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM
from app.main import app
from tests.api.test_drafts_api import assert_envelope


@pytest.fixture
def run_id(client) -> str:
    return client.post("/api/conversations/conv_priya/drafts", json={}).json()["id"]


def test_approve_as_is(client, run_id):
    draft = client.get(f"/api/runs/{run_id}").json()["draft_text"]
    response = client.post(f"/api/runs/{run_id}/approve")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["final_text"] == draft
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "approved"


def test_approve_edited_text_is_stripped(client, run_id):
    body = client.post(f"/api/runs/{run_id}/approve", json={"edited_text": "  Hello there  "}).json()
    assert body["final_text"] == "Hello there"
    assert body["draft_text"] != body["final_text"]


def test_reject_with_reason(client, run_id):
    response = client.post(f"/api/runs/{run_id}/reject", json={"reason": "  Too long  "})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["rejection_reason"] == "Too long"


@pytest.mark.parametrize(("path", "payload", "field"), [
    ("approve", {"edited_text": "   "}, "edited_text"),
    ("approve", {"edited_text": ""}, "edited_text"),
    ("approve", {"edited_text": "x" * 2001}, "edited_text"),
    ("reject", {"reason": "ab"}, "reason"),
    ("reject", {"reason": "   "}, "reason"),
    ("reject", {}, "reason"),
    ("reject", {"reason": "x" * 501}, "reason"),
])
def test_invalid_bodies_are_422_and_change_nothing(client, run_id, path, payload, field):
    error = assert_envelope(client.post(f"/api/runs/{run_id}/{path}", json=payload),
                            422, "validation_error")
    assert field in error["message"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "awaiting_approval"


@pytest.mark.parametrize(("path", "payload"), [("approve", {}), ("reject", {"reason": "nope"})])
def test_unknown_run_is_404(client, path, payload):
    assert_envelope(client.post(f"/api/runs/missing/{path}", json=payload), 404, "not_found")


def test_double_approve_is_409(client, run_id):
    assert client.post(f"/api/runs/{run_id}/approve").status_code == 200
    error = assert_envelope(client.post(f"/api/runs/{run_id}/approve"), 409, "invalid_transition")
    assert "approved" in error["message"]


def test_approve_after_reject_is_409(client, run_id):
    client.post(f"/api/runs/{run_id}/reject", json={"reason": "not right"})
    assert_envelope(client.post(f"/api/runs/{run_id}/approve"), 409, "invalid_transition")
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "rejected"


def test_reject_after_approve_is_409(client, run_id):
    client.post(f"/api/runs/{run_id}/approve")
    assert_envelope(client.post(f"/api/runs/{run_id}/reject", json={"reason": "changed mind"}),
                    409, "invalid_transition")


def test_approving_a_failed_run_is_409(client, use_llm):
    use_llm(FakeLLM([LLMResponse(content="Hi [Name]")]))  # guardrail failure
    failed = client.post("/api/conversations/conv_priya/drafts", json={}).json()
    assert failed["status"] == "failed"
    assert_envelope(client.post(f"/api/runs/{failed['id']}/approve"), 409, "invalid_transition")
    assert_envelope(client.post(f"/api/runs/{failed['id']}/reject", json={"reason": "not good"}),
                    409, "invalid_transition")


def test_guardrail_failure_over_api_has_error_and_no_draft(client, use_llm):
    use_llm(FakeLLM([LLMResponse(content="Your salary is 90k")]))
    run = client.post("/api/conversations/conv_tom/drafts", json={}).json()
    assert run["status"] == "failed"
    assert run["draft_text"] is None
    assert "compensation" in run["error"]
    assert run["steps"][-1]["type"] == "error"


def test_injected_failure_candidate_gets_degraded_draft_over_api(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        inject_interview_failure_for="cand_priya")
    response = client.post("/api/conversations/conv_priya/drafts", json={})
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "awaiting_approval"
    errors = [s for s in run["steps"] if s["type"] == "error"]
    assert len(errors) == 2 and errors[0]["error"].endswith("retrying")
    assert "2026-11-12" not in run["draft_text"]
    # the same API call for a different candidate is unaffected
    other = client.post("/api/conversations/conv_tom/drafts", json={}).json()
    assert not [s for s in other["steps"] if s["type"] == "error"]
