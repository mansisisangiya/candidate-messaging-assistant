import pytest

from app.agent.tools import ToolRegistry
from app.data.store import FixtureStore
from app.db.repo import RunRepository


@pytest.fixture(scope="session")
def store() -> FixtureStore:
    return FixtureStore()


@pytest.fixture
def registry(store: FixtureStore) -> ToolRegistry:
    return ToolRegistry(store)


@pytest.fixture
def repo(tmp_path) -> RunRepository:
    return RunRepository(tmp_path / "test.db")
