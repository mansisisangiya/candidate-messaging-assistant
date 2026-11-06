"""Read-only views assembled for the API."""
from app.data.store import FixtureStore
from app.db.repo import RunRepository
from app.models import AgentRun, ConversationDetail, ConversationSummary, RunSummary

PREVIEW_LENGTH = 80


def list_conversations(store: FixtureStore, repo: RunRepository) -> list[ConversationSummary]:
    latest_status = {}
    for run in reversed(repo.list_run_summaries()):  # oldest first, so the newest overwrites
        latest_status[run.conversation_id] = run.status
    summaries = []
    for conv in store.list_conversations():
        candidate = store.get_candidate(conv.candidate_id)
        preview = conv.messages[-1].text
        if len(preview) > PREVIEW_LENGTH:
            preview = preview[: PREVIEW_LENGTH - 1].rstrip() + "…"
        summaries.append(ConversationSummary(
            id=conv.id, candidate_name=candidate.name,
            job_title=store.get_job(candidate.job_id).title,
            last_message_preview=preview, latest_run_status=latest_status.get(conv.id)))
    return summaries


def get_conversation(store: FixtureStore, repo: RunRepository, conversation_id: str
                     ) -> ConversationDetail:
    conversation = store.get_conversation(conversation_id)
    candidate = store.get_candidate(conversation.candidate_id)
    latest = repo.list_run_summaries(conversation_id)
    return ConversationDetail(
        conversation=conversation, candidate=candidate, job=store.get_job(candidate.job_id),
        latest_run=repo.get_run(latest[0].id) if latest else None)


def list_runs(repo: RunRepository, conversation_id: str | None) -> list[RunSummary]:
    return repo.list_run_summaries(conversation_id)


def get_run(repo: RunRepository, run_id: str) -> AgentRun:
    return repo.get_run(run_id)
