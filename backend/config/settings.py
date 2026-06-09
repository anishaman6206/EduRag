"""
EduRag settings — all configuration flows through this module.

Loaded once at process start via `get_settings()`. Cached so the env is
read a single time (lru_cache returns the same instance thereafter).
"""

from __future__ import annotations
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env with override=True BEFORE BaseSettings is constructed.
# Why: pydantic-settings reads os.environ, which is normally populated by
# the shell. If a user previously exported OPENAI_API_KEY etc. in their
# shell (e.g. an `irm | iex` one-liner from a third-party dashboard),
# those values will shadow the .env file. Forcing dotenv override
# ensures the project's .env is the single source of truth.
from dotenv import load_dotenv
load_dotenv(override=True)


# ─────────────────────────────────────────────────────────────────────────
# Model selection
# All text roles use gpt-4o-mini. Embeddings use text-embedding-3-small.
# DEV_MODE is currently a no-op (the same model is used regardless) —
# it's kept in the env so we have one knob to flip when we add a more
# expensive model for production.
# Add new roles here and consume settings.MODELS["..."] everywhere —
# never hardcode model IDs in business code.
# ─────────────────────────────────────────────────────────────────────────
_PROD_MODELS = {
    "classifier": "gpt-4o-mini",
    "answer":     "gpt-4o-mini",
    "ingestion":  "gpt-4o-mini",
    "vision":     "gpt-4o-mini",   # not used yet (no vision in this build)
}
_DEV_MODELS = {
    "classifier": "gpt-4o-mini",
    "answer":     "gpt-4o-mini",
    "ingestion":  "gpt-4o-mini",
    "vision":     "gpt-4o-mini",
}


class Settings(BaseSettings):
    """
    All env-driven configuration. Field names map 1:1 with the .env keys
    declared in .env.example. Do NOT read os.environ directly anywhere else.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── OpenAI (text + embeddings) ─────────────────────────────────────
    openai_api_key: str
    openai_text_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # ── Pinecone ───────────────────────────────────────────────────────
    pinecone_api_key: str
    pinecone_index_name: str = "edurag"

    # ── Supabase ───────────────────────────────────────────────────────
    supabase_url: str
    supabase_service_key: str   # service-role key, server-side only

    # ── Redis ──────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── Cohere (optional reranker — off until a key is set) ────────────
    # Empty string means "not configured" → rerank step is skipped silently.
    cohere_api_key: str = ""

    # ── Runtime mode ───────────────────────────────────────────────────
    # Currently a no-op (same model in dev and prod). Kept so we have one
    # knob to flip when we add a more expensive production model.
    dev_mode: bool = True

    # ── Derived: model selection dict ──────────────────────────────────
    @property
    def models(self) -> dict[str, str]:
        """Return the active model ID per role, based on DEV_MODE."""
        return _DEV_MODELS if self.dev_mode else _PROD_MODELS

    @property
    def has_cohere(self) -> bool:
        """True if a non-empty Cohere key was provided."""
        return bool(self.cohere_api_key and self.cohere_api_key.strip())

    @property
    def environment(self) -> Literal["dev", "prod"]:
        return "dev" if self.dev_mode else "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Singleton accessor. Importing this from anywhere returns the same
    Settings instance, so .env is parsed exactly once per process.
    """
    return Settings()  # type: ignore[call-arg]
