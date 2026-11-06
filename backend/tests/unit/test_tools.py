import pytest

from app.errors import RecordNotFoundError, ToolInputError, UnknownToolError


def test_get_candidate(registry):
    result = registry.execute("get_candidate", {"candidate_id": "cand_priya"})
    assert result["name"] == "Priya Sharma"
    assert result["job_id"] == "job_backend"
    assert result["stage"] == "interview"


def test_get_interview_status_scheduled(registry):
    result = registry.execute("get_interview_status", {"candidate_id": "cand_priya"})
    assert result["status"] == "scheduled"
    assert result["scheduled_at"].startswith("2026-11-12T14:00")
    assert result["interviewer"] == "Daniel Okafor"


def test_get_interview_status_not_scheduled(registry):
    result = registry.execute("get_interview_status", {"candidate_id": "cand_elena"})
    assert result["status"] == "not_scheduled"
    assert result["scheduled_at"] is None


def test_get_job(registry):
    result = registry.execute("get_job", {"job_id": "job_data"})
    assert result == {"id": "job_data", "title": "Data Analyst", "team": "Insights",
                      "location": "Berlin"}


@pytest.mark.parametrize(
    ("tool", "args"),
    [("get_candidate", {"candidate_id": "cand_nope"}),
     ("get_interview_status", {"candidate_id": "cand_nope"}),
     ("get_job", {"job_id": "job_nope"})],
)
def test_unknown_record_raises_not_found(registry, tool, args):
    with pytest.raises(RecordNotFoundError):
        registry.execute(tool, args)


@pytest.mark.parametrize(
    ("tool", "args"),
    [("get_candidate", {}),
     ("get_candidate", {"candidate_id": 5}),
     ("get_candidate", {"candidate_id": "bad id!"}),
     ("get_job", {"candidate_id": "cand_priya"}),  # wrong argument name
     ("get_job", {"job_id": "job_data", "extra": 1})],
)
def test_invalid_arguments_raise_tool_input_error(registry, tool, args):
    with pytest.raises(ToolInputError):
        registry.execute(tool, args)


def test_unknown_tool_raises(registry):
    with pytest.raises(UnknownToolError):
        registry.execute("send_email", {})


def test_schemas_describe_all_three_tools(registry):
    schemas = {s["name"]: s for s in registry.schemas()}
    assert set(schemas) == {"get_candidate", "get_interview_status", "get_job"}
    assert schemas["get_job"]["parameters"]["required"] == ["job_id"]
