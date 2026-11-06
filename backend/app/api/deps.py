"""Builds the store, repository, LLM and services from config in one place.

Tests replace these with `app.dependency_overrides` (temp database, scripted FakeLLM).
"""
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.data.store import FixtureStore
from app.db.repo import RunRepository
from app.llm.base import LLMClient
from app.llm.factory import create_llm
from app.services.drafting import DraftingService


@lru_cache
def get_store() -> FixtureStore:
    return FixtureStore()


@lru_cache
def _repo_for(path: str) -> RunRepository:
    return RunRepository(path)


def get_repo(settings: Annotated[Settings, Depends(get_settings)]) -> RunRepository:
    return _repo_for(settings.database_path)


def get_llm(settings: Annotated[Settings, Depends(get_settings)]) -> LLMClient:
    return create_llm(settings.llm_provider)  # new instance per request: no shared state


StoreDep = Annotated[FixtureStore, Depends(get_store)]
RepoDep = Annotated[RunRepository, Depends(get_repo)]


def get_drafting_service(store: StoreDep, repo: RepoDep,
                         llm: Annotated[LLMClient, Depends(get_llm)]) -> DraftingService:
    return DraftingService(store, repo, llm)
