"""
src/providers/config.py
========================
Provider-specific configuration dataclasses.

**Single Source of Truth for default model names.**

The constants ``GEMINI_DEFAULT_MODEL``, ``ANTHROPIC_DEFAULT_MODEL``,
``MIMO_DEFAULT_MODEL`` are the canonical default model ids.  All other
modules reference these constants instead of hardcoding strings:

- ``config.py`` (Settings defaults)
- ``api/providers.py`` (_PROVIDER_CATALOGUE, get_active_provider)
- ``providers/config.py`` (dataclass defaults — same module)

This eliminates the 4-way duplication that caused sync bugs when
adding or changing models.

Usage::

    # In api/providers.py
    from src.providers.config import GEMINI_DEFAULT_MODEL
    _PROVIDER_CATALOGUE = [
        ProviderInfo(default_model=GEMINI_DEFAULT_MODEL, ...),
    ]

    # In config.py
    from src.providers.config import GEMINI_DEFAULT_MODEL
    class Settings:
        gemini_model: str = GEMINI_DEFAULT_MODEL
"""
from __future__ import annotations

from dataclasses import dataclass


# ── Canonical default model names (SINGLE SOURCE OF TRUTH) ──────────────────

GEMINI_DEFAULT_MODEL: str = "gemini-3.1-pro-preview"
ANTHROPIC_DEFAULT_MODEL: str = "claude-sonnet-4-6"
MIMO_DEFAULT_MODEL: str = "mimo-v2.5-pro"


# ── Provider config dataclasses ─────────────────────────────────────────────

@dataclass(frozen=True)
class GeminiConfig:
    """Configuration for the Google Gemini provider."""

    model: str = GEMINI_DEFAULT_MODEL
    temperature: float = 0.2


@dataclass(frozen=True)
class AnthropicConfig:
    """Configuration for the Anthropic Claude provider."""

    api_key: str | None = None
    model: str = ANTHROPIC_DEFAULT_MODEL
    temperature: float = 0.2
    max_tokens: int = 8096


@dataclass(frozen=True)
class MimoConfig:
    """Configuration for the Xiaomi Mimo provider (OpenAI-compatible)."""

    api_key: str | None = None
    base_url: str = "https://api.xiaomimimo.com/v1"
    model: str = MIMO_DEFAULT_MODEL
    temperature: float = 0.2
    max_tokens: int = 8096
