import json
import shutil

import pytest

from app.data.store import FIXTURE_DIR, FixtureStore
from app.errors import FixtureError, RecordNotFoundError


def test_fixtures_load_and_references_resolve(store):
    conversations = store.list_conversations()
    assert len(conversations) >= 3
    for conv in conversations:
        candidate = store.get_candidate(conv.candidate_id)
        assert store.get_job(candidate.job_id)
        assert store.get_interview(candidate.id).candidate_id == candidate.id


def test_every_fixture_candidate_has_an_interview_record(store):
    for conv in store.list_conversations():
        store.get_interview(conv.candidate_id)


def test_missing_record_raises_not_found(store):
    with pytest.raises(RecordNotFoundError, match="cand_nope"):
        store.get_candidate("cand_nope")


@pytest.fixture
def fixture_copy(tmp_path):
    target = tmp_path / "fixtures"
    shutil.copytree(FIXTURE_DIR, target)
    return target


def test_dangling_job_reference_is_rejected(fixture_copy):
    path = fixture_copy / "candidates.json"
    data = json.loads(path.read_text())
    data[0]["job_id"] = "job_missing"
    path.write_text(json.dumps(data))
    with pytest.raises(FixtureError, match="unknown job"):
        FixtureStore(fixture_copy)


def test_malformed_fixture_is_rejected(fixture_copy):
    (fixture_copy / "jobs.json").write_text("{not json")
    with pytest.raises(FixtureError, match="jobs.json"):
        FixtureStore(fixture_copy)


def test_duplicate_ids_are_rejected(fixture_copy):
    path = fixture_copy / "jobs.json"
    data = json.loads(path.read_text())
    path.write_text(json.dumps([*data, data[0]]))
    with pytest.raises(FixtureError, match="duplicate job"):
        FixtureStore(fixture_copy)
