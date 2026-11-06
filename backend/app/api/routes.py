from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import RepoDep, StoreDep, get_drafting_service
from app.config import Settings, get_settings
from app.models import (
    AgentRun,
    ConversationDetail,
    ConversationSummary,
    DraftRequest,
    RunSummary,
)
from app.services import queries
from app.services.drafting import DraftingService

router = APIRouter(prefix="/api")


@router.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    return {"status": "ok", "llm_provider": settings.llm_provider}


@router.get("/conversations")
def list_conversations(store: StoreDep, repo: RepoDep) -> list[ConversationSummary]:
    return queries.list_conversations(store, repo)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, store: StoreDep, repo: RepoDep) -> ConversationDetail:
    return queries.get_conversation(store, repo, conversation_id)


@router.post("/conversations/{conversation_id}/drafts", status_code=201)
def create_draft(
    conversation_id: str,
    service: Annotated[DraftingService, Depends(get_drafting_service)],
    body: DraftRequest | None = None,
) -> AgentRun:
    # A failed run is still a created run: 201 with status "failed" and an error message.
    return service.create_draft(conversation_id, body.instructions if body else None)


@router.get("/runs")
def list_runs(repo: RepoDep, conversation_id: Annotated[str | None, Query()] = None
              ) -> list[RunSummary]:
    return queries.list_runs(repo, conversation_id)


@router.get("/runs/{run_id}")
def get_run(run_id: str, repo: RepoDep) -> AgentRun:
    return queries.get_run(repo, run_id)
