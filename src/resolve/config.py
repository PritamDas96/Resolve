"""Application configuration for RESOLVE.

All runtime configuration is loaded from environment variables (and the local
``.env`` file during development) into a single, validated :class:`Settings`
object. Centralising configuration here means:

* secrets never appear as string literals in the codebase (plan rule 6);
* every setting is typed and validated once, at process start-up;
* tests can construct :class:`Settings` with explicit values and ignore ``.env``.

Secrets are wrapped in :class:`pydantic.SecretStr` so they are redacted in logs,
``repr()`` output and tracebacks. Call ``.get_secret_value()`` only at the exact
point the raw value is needed (e.g. when configuring an HTTP client).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings, sourced from the environment / ``.env``.

    Environment variables are matched to field names case-insensitively, so the
    field ``gemini_api_key`` is populated from ``GEMINI_API_KEY``. Explicit
    environment variables take precedence over values in ``.env``; unknown
    variables are ignored rather than raising.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM provider credentials -------------------------------------------
    gemini_api_key: SecretStr = Field(
        description="Google AI Studio key for Gemini (router + drafter).",
    )
    google_api_key: SecretStr | None = Field(
        default=None,
        description="Alias of GEMINI_API_KEY used by Google's own SDK.",
    )
    groq_api_key: SecretStr = Field(
        description="Groq key (gsk_...) for the judge model.",
    )

    # --- Observability (LangSmith) ------------------------------------------
    langsmith_api_key: SecretStr | None = Field(default=None)
    langsmith_tracing: bool = Field(
        default=False,
        description="When true, traces are exported to LangSmith.",
    )
    langsmith_project: str = Field(default="resolve")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com")

    # --- Optional tooling ----------------------------------------------------
    hf_token: SecretStr | None = Field(
        default=None,
        description="Hugging Face token; optional, raises model-download limits.",
    )

    # --- Model routing (model IDs, not secrets) -----------------------------
    # These are LiteLLM-style identifiers ("<provider>/<model>"). Defaults match
    # what is available on the free tier as of 2026-10-02 (see ADR-013).
    router_model: str = Field(default="gemini/gemini-3.8-flash")
    drafter_model: str = Field(default="gemini/gemini-3.8-flash")
    judge_model: str = Field(default="groq/openai/gpt-oss-120b")

    # --- Local infrastructure ------------------------------------------------
    postgres_dsn: str = Field(
        default="postgresql://resolve:resolve@localhost:5432/resolve",
        description="SQLAlchemy/asyncpg DSN for the PostgreSQL instance.",
    )
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Base URL of the Qdrant vector database.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, constructed once and cached.

    The ``lru_cache`` makes this a lazy singleton: the first call reads the
    environment and ``.env``; later calls return the identical object. Tests that
    need to re-read configuration should call ``get_settings.cache_clear()``
    first.

    Returns:
        The validated application settings.
    """
    return Settings()
