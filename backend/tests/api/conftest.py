import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm, get_repo
from app.db.repo import RunRepository
from app.llm.fake import FakeLLM
from app.main import app


@pytest.fixture
def repo(tmp_path) -> RunRepository:
    return RunRepository(tmp_path / "api.db")


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_llm] = lambda: FakeLLM()
    # raise_server_exceptions=False: let the catch-all handler answer, as in production.
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def use_llm():
    """Swap in a scripted FakeLLM for the current test."""
    def _use(llm: FakeLLM) -> None:
        app.dependency_overrides[get_llm] = lambda: llm
    return _use
