"""
src/config.py
=============
Central application settings powered by pydantic-settings.

All knobs live here.  Values can be overridden via environment variables
(names match the field names, upper-cased) or a .env file in the project root.

Usage:
    from src.config import settings

    settings.data_dir           # Path("data")
    settings.prompts_dir        # Path("prompts")
    settings.app_title          # "Agentic Workspace API"
    settings.app_description    # "Domain-agnostic AI agent..."
    settings.gemini_model       # "gemini-2.5-flash"
    settings.allowed_origins    # ["http://localhost:5173"]
    settings.llm_provider       # "gemini" | "anthropic"
    settings.anthropic_model    # "claude-sonnet-4-5"

Domain-agnostic app metadata
-----------------------------
Set ``APP_TITLE`` and ``APP_DESCRIPTION`` in your ``.env`` (or environment)
to customise the FastAPI OpenAPI title and description without touching source
code.  This allows the same backend to serve any knowledge domain.

Provider selection
------------------
Set ``LLM_PROVIDER=anthropic`` in your ``.env`` (or environment) to switch
from Gemini to Anthropic Claude.  The Anthropic provider also requires
``ANTHROPIC_API_KEY`` to be set.
"""

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.providers.config import (
    ANTHROPIC_DEFAULT_MODEL,
    GEMINI_DEFAULT_MODEL,
    MIMO_DEFAULT_MODEL,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application metadata ─────────────────────────────────────────────────
    # Override via APP_TITLE / APP_DESCRIPTION env vars to adapt to any domain.
    app_title: str = "Agentic Workspace API"
    app_description: str = (
        "Domain-agnostic AI agent with tool-calling, session management, "
        "and a knowledge-base file system."
    )

    # ── Debug mode ───────────────────────────────────────────────────────────
    # Enable test helpers (X-Test-Delay-Ms header, seed endpoints, etc.)
    debug: bool = False

    # ── Paths ────────────────────────────────────────────────────────────────
    data_dir: Path = Path("data")

    # F05 — prompts directory for backend-managed system prompts
    prompts_dir: Path = Path("prompts")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "chats.db"

    @property
    def prompt_log_path(self) -> Path:
        return self.data_dir / "prompt_log.md"

    # ── Gemini ───────────────────────────────────────────────────────────────
    gemini_model: str = GEMINI_DEFAULT_MODEL
    gemini_temperature: float = 0.2

    # ── Anthropic ────────────────────────────────────────────────────────────
    # API key — optional when using Gemini (the default provider).
    # Required when LLM_PROVIDER=anthropic.
    anthropic_api_key: str | None = None

    # Model name.  Default: claude-sonnet-4-6 (fast, capable, cost-effective).
    anthropic_model: str = ANTHROPIC_DEFAULT_MODEL

    # Sampling temperature (0.0–1.0 recommended for Claude).
    anthropic_temperature: float = 0.2

    # Maximum tokens in the assistant response.
    # Anthropic requires this parameter (Gemini does not).
    anthropic_max_tokens: int = 8096

    # ── Xiaomi Mimo ──────────────────────────────────────────────────────────
    # OpenAI-compatible API provided by Xiaomi.
    mimo_api_key: str | None = None
    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_model: str = MIMO_DEFAULT_MODEL
    mimo_temperature: float = 0.2
    mimo_max_tokens: int = 8096

    # ── Provider selection ────────────────────────────────────────────────────
    # Controls which LLM backend is used for all chat turns.
    # Accepted values: "gemini" | "anthropic" | "mimo"
    # Additional providers can be added by implementing LLMProvider and
    # registering them in src/providers/base.py get_provider().
    llm_provider: str = "gemini"

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated list in env:  ALLOWED_ORIGINS=http://localhost:5173,https://example.com
    # Include both dev (5173) and E2E (5174) ports
    allowed_origins: list[str] = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v  # type: ignore[return-value]


# Singleton — import this everywhere instead of instantiating Settings() again.
settings = Settings()
