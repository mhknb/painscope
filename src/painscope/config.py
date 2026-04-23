"""Runtime configuration loaded from environment variables and/or .env file."""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM (OpenRouter) ─────────────────────────────────────────────────
    openrouter_api_key: str = Field(..., description="OpenRouter API key")
    llm_model_tr: str = Field(
        default="google/gemini-2.0-flash-001",
        description="Default model for Turkish content",
    )
    llm_model_en: str = Field(
        default="google/gemini-2.0-flash-001",
        description="Default model for English content",
    )
    llm_model_fallback: str = Field(
        default="anthropic/claude-haiku-4.5",
        description="Fallback model if primary fails",
    )

    # ── Reddit ───────────────────────────────────────────────────────────
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "painscope/0.1 (personal research tool)"

    # ── Xpoz (Reddit) ────────────────────────────────────────────────────
    xpoz_api_key: str | None = None

    # ── YouTube ──────────────────────────────────────────────────────────
    youtube_api_key: str | None = None

    # ── Product Hunt ─────────────────────────────────────────────────────
    producthunt_api_key: str | None = None
    producthunt_api_secret: str | None = None

    # ── GitHub ───────────────────────────────────────────────────────────
    github_token: str | None = None

    # ── Embedding model (local) ──────────────────────────────────────────
    embedding_model: str = Field(
        default="intfloat/multilingual-e5-base",
        description="Sentence-transformers model; used locally (CPU ok)",
    )

    # ── Storage ──────────────────────────────────────────────────────────
    data_dir: Path = Field(default=Path.home() / ".painscope")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "painscope.db"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


# Singleton accessor
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
