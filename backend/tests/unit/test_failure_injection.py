import pytest

from app.agent.failure_injection import FailingTools
from app.errors import ToolUnavailableError


def test_failing_tool_raises_every_time(registry):
    tools = FailingTools(registry)
    for _ in range(3):
        with pytest.raises(ToolUnavailableError):
            tools.execute("get_interview_status", {"candidate_id": "cand_priya"})


def test_other_tools_pass_through(registry):
    tools = FailingTools(registry)
    assert tools.execute("get_candidate", {"candidate_id": "cand_priya"})["name"] == "Priya Sharma"
    assert tools.schemas() == registry.schemas()
