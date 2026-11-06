import pytest
from pydantic import ValidationError

from app.models import Candidate, GetCandidateInput, Interview, Message


def test_candidate_rejects_unknown_stage():
    with pytest.raises(ValidationError):
        Candidate(id="c1", name="A", email="a@example.com", job_id="j1", stage="hired")


def test_candidate_rejects_bad_email():
    with pytest.raises(ValidationError):
        Candidate(id="c1", name="A", email="not-an-email", job_id="j1", stage="applied")


def test_models_forbid_extra_fields():
    with pytest.raises(ValidationError):
        Candidate(id="c1", name="A", email="a@example.com", job_id="j1", stage="applied", x=1)


def test_scheduled_interview_requires_a_time():
    with pytest.raises(ValidationError):
        Interview(candidate_id="c1", status="scheduled")
    assert Interview(candidate_id="c1", status="not_scheduled").scheduled_at is None


def test_message_requires_text_and_valid_sender():
    with pytest.raises(ValidationError):
        Message(sender="candidate", text="", sent_at="2026-11-01T10:00:00Z")
    with pytest.raises(ValidationError):
        Message(sender="bot", text="hi", sent_at="2026-11-01T10:00:00Z")


@pytest.mark.parametrize("bad_id", ["", "has space", "../etc", "a" * 65])
def test_record_ids_are_restricted(bad_id):
    with pytest.raises(ValidationError):
        GetCandidateInput(candidate_id=bad_id)


def test_draft_request_strips_and_blank_becomes_none():
    from app.models import DraftRequest
    assert DraftRequest(instructions="  be brief  ").instructions == "be brief"
    assert DraftRequest(instructions="   ").instructions is None
    assert DraftRequest(instructions="").instructions is None


def test_approve_and_reject_requests_strip_and_validate():
    from app.models import ApproveRequest, RejectRequest
    assert ApproveRequest().edited_text is None
    assert ApproveRequest(edited_text="  Hi  ").edited_text == "Hi"
    assert RejectRequest(reason="  too pushy ").reason == "too pushy"
    for bad in ("", "   "):
        with pytest.raises(ValidationError):
            ApproveRequest(edited_text=bad)
    with pytest.raises(ValidationError):
        ApproveRequest(edited_text="x" * 2001)
    with pytest.raises(ValidationError):
        RejectRequest(reason="  a ")
    with pytest.raises(ValidationError):
        RejectRequest(reason="x" * 501)
