"""Environment-based configuration. All values have safe defaults; no secrets live here."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: str | None = None  # only read if llm_provider == "openai"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    database_path: str = "data/app.db"  # mutable run state; git-ignored (*.db)


@lru_cache
def get_settings() -> Settings:
    return Settings()
