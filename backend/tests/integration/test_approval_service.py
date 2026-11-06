import pytest

from app.errors import InvalidTransition, RecordNotFoundError
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM
from app.models import RunStatus
from app.services.approval import ApprovalService
from app.services.drafting import DraftingService


@pytest.fixture
def run(store, repo):
    return DraftingService(store, repo, FakeLLM()).create_draft("conv_priya")


def test_approve_as_is_uses_the_draft(repo, run):
    approved = ApprovalService(repo).approve(run.id)
    assert approved.status == RunStatus.APPROVED
    assert approved.final_text == run.draft_text
    assert repo.get_run(run.id) == approved


def test_approve_edited_keeps_the_original_draft(repo, run):
    approved = ApprovalService(repo).approve(run.id, "My own words")
    assert approved.final_text == "My own words"
    assert approved.draft_text == run.draft_text


def test_reject_stores_the_reason(repo, run):
    rejected = ApprovalService(repo).reject(run.id, "too formal")
    assert rejected.status == RunStatus.REJECTED
    assert rejected.rejection_reason == "too formal"
    assert rejected.final_text is None


def test_unknown_run_is_not_found(repo):
    with pytest.raises(RecordNotFoundError):
        ApprovalService(repo).approve("nope")
    with pytest.raises(RecordNotFoundError):
        ApprovalService(repo).reject("nope", "reason")


@pytest.mark.parametrize("first", ["approve", "reject"])
@pytest.mark.parametrize("second", ["approve", "reject"])
def test_a_decided_run_cannot_be_decided_again(repo, run, first, second):
    service = ApprovalService(repo)
    getattr(service, first)(run.id, *(["a reason"] if first == "reject" else []))
    before = repo.get_run(run.id)
    with pytest.raises(InvalidTransition):
        getattr(service, second)(run.id, *(["a reason"] if second == "reject" else []))
    assert repo.get_run(run.id) == before  # nothing changed


def test_a_failed_run_cannot_be_approved_or_rejected(store, repo):
    failed = DraftingService(store, repo, FakeLLM([LLMResponse(content="")])).create_draft("conv_priya")
    assert failed.status == RunStatus.FAILED
    with pytest.raises(InvalidTransition):
        ApprovalService(repo).approve(failed.id)
    with pytest.raises(InvalidTransition):
        ApprovalService(repo).reject(failed.id, "reason")
    assert repo.get_run(failed.id).final_text is None


def test_stale_approval_loses_to_a_concurrent_reject(repo, run, monkeypatch):
    """The approver read the run as awaiting_approval, but a reject lands before its write."""
    real_get_run = repo.get_run
    seen = []

    def get_run_then_reject(run_id):
        result = real_get_run(run_id)
        if not seen:  # first read is the approver's; the reject sneaks in right after
            seen.append(result)
            repo.update_status_if(run_id, RunStatus.AWAITING_APPROVAL, RunStatus.REJECTED,
                                  rejection_reason="raced")
        return result

    monkeypatch.setattr(repo, "get_run", get_run_then_reject)
    with pytest.raises(InvalidTransition):
        ApprovalService(repo).approve(run.id)
    monkeypatch.undo()
    assert repo.get_run(run.id).status == RunStatus.REJECTED
    assert repo.get_run(run.id).final_text is None
