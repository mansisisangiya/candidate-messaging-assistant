from tests.api.test_drafts_api import assert_envelope


def test_list_conversations(client):
    items = client.get("/api/conversations").json()
    assert [i["id"] for i in items] == ["conv_priya", "conv_marcus", "conv_elena", "conv_tom"]
    priya = items[0]
    assert priya["candidate_name"] == "Priya Sharma"
    assert priya["job_title"] == "Senior Backend Engineer"
    assert priya["last_message_preview"].startswith("Thanks! Could you confirm")
    assert priya["latest_run_status"] is None


def test_latest_run_status_appears_after_drafting(client):
    client.post("/api/conversations/conv_priya/drafts", json={})
    items = {i["id"]: i for i in client.get("/api/conversations").json()}
    assert items["conv_priya"]["latest_run_status"] == "awaiting_approval"
    assert items["conv_tom"]["latest_run_status"] is None


def test_get_conversation_detail(client):
    run = client.post("/api/conversations/conv_tom/drafts", json={}).json()
    detail = client.get("/api/conversations/conv_tom").json()
    assert detail["candidate"]["name"] == "Tom Becker"
    assert detail["job"]["title"] == "Senior Backend Engineer"
    assert len(detail["conversation"]["messages"]) == 2
    assert detail["latest_run"]["id"] == run["id"]
    assert len(detail["latest_run"]["steps"]) == 7


def test_get_conversation_without_runs_has_null_latest_run(client):
    assert client.get("/api/conversations/conv_elena").json()["latest_run"] is None


def test_unknown_conversation_is_404(client):
    assert_envelope(client.get("/api/conversations/nope"), 404, "not_found")


def test_list_runs_returns_summaries_without_steps_newest_first(client):
    first = client.post("/api/conversations/conv_priya/drafts", json={}).json()
    second = client.post("/api/conversations/conv_priya/drafts", json={}).json()
    client.post("/api/conversations/conv_tom/drafts", json={})
    runs = client.get("/api/runs", params={"conversation_id": "conv_priya"}).json()
    assert [r["id"] for r in runs] == [second["id"], first["id"]]
    assert "steps" not in runs[0]
    assert runs[0]["step_count"] == 7
    assert len(client.get("/api/runs").json()) == 3


def test_get_run_with_steps(client):
    run = client.post("/api/conversations/conv_priya/drafts", json={}).json()
    fetched = client.get(f"/api/runs/{run['id']}").json()
    assert fetched == run


def test_unknown_run_is_404(client):
    assert_envelope(client.get("/api/runs/nope"), 404, "not_found")
