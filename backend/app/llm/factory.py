from app.errors import ConfigurationError
from app.llm.base import LLMClient
from app.llm.fake import FakeLLM


def create_llm(provider: str) -> LLMClient:
    """The single place a provider is chosen from config."""
    if provider == "fake":
        return FakeLLM()
    raise ConfigurationError(f"LLM provider '{provider}' is not implemented")
