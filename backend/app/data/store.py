"""Read-only access to the JSON fixtures, validated once at load time."""
import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from app.errors import FixtureError, RecordNotFoundError
from app.models import Candidate, Conversation, Interview, Job

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load[T](directory: Path, filename: str, model: type[T]) -> list[T]:
    path = directory / filename
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return TypeAdapter(list[model]).validate_python(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise FixtureError(f"{filename}: {exc}") from exc


class FixtureStore:
    def __init__(self, directory: Path = FIXTURE_DIR) -> None:
        candidates = _load(directory, "candidates.json", Candidate)
        jobs = _load(directory, "jobs.json", Job)
        interviews = _load(directory, "interviews.json", Interview)
        conversations = _load(directory, "conversations.json", Conversation)

        self._candidates = self._index(candidates, "candidate")
        self._jobs = self._index(jobs, "job")
        self._conversations = self._index(conversations, "conversation")
        self._interviews = {i.candidate_id: i for i in interviews}
        if len(self._interviews) != len(interviews):
            raise FixtureError("duplicate interview record for a candidate")
        self._check_references()

    @staticmethod
    def _index[T: (Candidate, Job, Conversation)](items: list[T], kind: str) -> dict[str, T]:
        indexed = {item.id: item for item in items}
        if len(indexed) != len(items):
            raise FixtureError(f"duplicate {kind} id")
        return indexed

    def _check_references(self) -> None:
        for c in self._candidates.values():
            if c.job_id not in self._jobs:
                raise FixtureError(f"candidate {c.id} references unknown job {c.job_id}")
        for candidate_id in self._interviews:
            if candidate_id not in self._candidates:
                raise FixtureError(f"interview references unknown candidate {candidate_id}")
        for conv in self._conversations.values():
            if conv.candidate_id not in self._candidates:
                raise FixtureError(f"conversation {conv.id} references unknown candidate")

    def get_candidate(self, candidate_id: str) -> Candidate:
        return self._get(self._candidates, candidate_id, "candidate")

    def get_job(self, job_id: str) -> Job:
        return self._get(self._jobs, job_id, "job")

    def get_interview(self, candidate_id: str) -> Interview:
        return self._get(self._interviews, candidate_id, "interview record")

    def get_conversation(self, conversation_id: str) -> Conversation:
        return self._get(self._conversations, conversation_id, "conversation")

    def list_conversations(self) -> list[Conversation]:
        return list(self._conversations.values())

    @staticmethod
    def _get[T](items: dict[str, T], key: str, kind: str) -> T:
        try:
            return items[key]
        except KeyError:
            raise RecordNotFoundError(f"No {kind} found with id '{key}'") from None
