import sqlite3
from itertools import product

import pytest

from app.errors import InvalidTransition, RecordNotFoundError
from app.models import RunStatus
from app.services.run_state import ALLOWED_TRANSITIONS, transition

ALLOWED = {
    (RunStatus.RUNNING, RunStatus.AWAITING_APPROVAL),
    (RunStatus.RUNNING, RunStatus.FAILED),
    (RunStatus.AWAITING_APPROVAL, RunStatus.APPROVED),
    (RunStatus.AWAITING_APPROVAL, RunStatus.REJECTED),
}
TERMINAL = [RunStatus.APPROVED, RunStatus.REJECTED, RunStatus.FAILED]


def force_status(repo, run_id, status):
    """Test-only: put a run in any state, bypassing the state machine."""
    with sqlite3.connect(repo._db_path) as conn:
        conn.execute("UPDATE runs SET status = ? WHERE id = ?", (status, run_id))


@pytest.mark.parametrize(("source", "target"), list(product(RunStatus, RunStatus)))
def test_full_transition_matrix(repo, source, target):
    run = repo.create_run("conv_priya")
    force_status(repo, run.id, source)
    if (source, target) in ALLOWED:
        assert transition(repo, run.id, target).status == target
    else:
        with pytest.raises(InvalidTransition):
            transition(repo, run.id, target)
        assert repo.get_run(run.id).status == source  # unchanged


def test_table_matches_expected_edges():
    assert {(s, t) for s, targets in ALLOWED_TRANSITIONS.items() for t in targets} == ALLOWED


@pytest.mark.parametrize("terminal", TERMINAL)
def test_terminal_states_allow_nothing_even_themselves(terminal):
    assert ALLOWED_TRANSITIONS[terminal] == frozenset()


def test_transition_writes_fields_atomically_with_status(repo):
    run = repo.create_run("conv_priya")
    result = transition(repo, run.id, RunStatus.AWAITING_APPROVAL, draft_text="Hello")
    assert (result.status, result.draft_text) == (RunStatus.AWAITING_APPROVAL, "Hello")


def test_rejected_transition_does_not_write_fields(repo):
    run = repo.create_run("conv_priya")
    force_status(repo, run.id, RunStatus.FAILED)
    with pytest.raises(InvalidTransition):
        transition(repo, run.id, RunStatus.AWAITING_APPROVAL, draft_text="sneaky")
    assert repo.get_run(run.id).draft_text is None


def test_invalid_transition_maps_to_code_invalid_transition():
    assert InvalidTransition("x").code == "invalid_transition"


def test_unknown_run_is_not_found(repo):
    with pytest.raises(RecordNotFoundError):
        transition(repo, "nope", RunStatus.FAILED)


def test_status_cannot_be_passed_as_a_plain_field(repo):
    run = repo.create_run("conv_priya")
    with pytest.raises(ValueError):
        transition(repo, run.id, RunStatus.FAILED, status="approved")
