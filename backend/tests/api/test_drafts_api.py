from app.api.deps import get_repo
from app.errors import LLMError
from app.llm.fake import FakeLLM
from app.main import app


def assert_envelope(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]


def test_create_draft_returns_201_with_run_and_steps(client):
    response = client.post("/api/conversations/conv_priya/drafts",
                           json={"instructions": "Keep it short"})
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "awaiting_approval"
    assert "2026-11-12 at 14:00 UTC" in run["draft_text"]
    assert run["instructions"] == "Keep it short"
    assert len(run["steps"]) == 7


def test_create_draft_without_body_is_allowed(client):
    assert client.post("/api/conversations/conv_elena/drafts").status_code == 201


def test_failed_run_still_returns_201(client, use_llm):
    use_llm(FakeLLM([LLMError("provider down")]))
    response = client.post("/api/conversations/conv_priya/drafts", json={})
    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "provider down"


def test_unknown_conversation_is_404(client):
    error = assert_envelope(client.post("/api/conversations/nope/drafts", json={}), 404, "not_found")
    assert "nope" in error["message"]


def test_instructions_over_500_chars_is_422_in_envelope(client):
    response = client.post("/api/conversations/conv_priya/drafts",
                           json={"instructions": "x" * 501})
    error = assert_envelope(response, 422, "validation_error")
    assert "instructions" in error["message"]
    assert "xxxxx" not in error["message"]  # the input is not echoed back


def test_unexpected_exception_returns_500_envelope_without_traceback(client):
    def broken_repo():
        raise RuntimeError("secret internal detail")

    app.dependency_overrides[get_repo] = broken_repo
    response = client.get("/api/runs")
    error = assert_envelope(response, 500, "internal_error")
    assert error["message"] == "Internal server error"
    assert "secret" not in response.text
    assert "Traceback" not in response.text


def test_unknown_path_uses_envelope(client):
    assert_envelope(client.get("/api/nope"), 404, "not_found")


def test_blank_instructions_are_stored_as_null(client):
    run = client.post("/api/conversations/conv_priya/drafts", json={"instructions": "   "}).json()
    assert run["instructions"] is None
