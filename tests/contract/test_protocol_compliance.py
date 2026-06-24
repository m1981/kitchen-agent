"""
tests/test_providers_base.py
============================
Tests for the LLMProvider Protocol and provider registry.

Verifies:
  - Protocol structural compliance (duck-typing) — any object that implements
    ``complete`` and ``complete_with_tools`` satisfies the protocol.
  - ``get_provider()`` factory returns the correct concrete class based on
    ``settings.llm_provider``.
  - ``get_provider()`` raises ``ValueError`` for unknown provider names.
"""
from unittest.mock import patch, MagicMock

import pytest

from src.providers.base import LLMProvider, get_provider
from src.providers.gemini import GeminiProvider
from src.providers.anthropic_provider import AnthropicProvider


# ---------------------------------------------------------------------------
# Protocol structural compliance
# ---------------------------------------------------------------------------

class _MinimalProvider:
    """Minimal duck-type implementation with ALL 4 required methods."""

    def complete(self, context):
        return MagicMock()

    def complete_with_tools(self, context, tool_calls, tool_results):
        return MagicMock()

    def stream(self, context):
        return iter([])

    def stream_with_tools(self, context, tool_calls, tool_results):
        return iter([])


def test_minimal_provider_satisfies_protocol() -> None:
    """Any object with all 4 methods satisfies LLMProvider (structural subtyping)."""
    provider = _MinimalProvider()
    assert isinstance(provider, LLMProvider)


def test_gemini_provider_satisfies_protocol() -> None:
    with patch("src.providers.gemini.genai.Client"):
        provider = GeminiProvider()
    assert isinstance(provider, LLMProvider)


def test_anthropic_provider_satisfies_protocol() -> None:
    with patch("src.providers.anthropic_provider.anthropic.Anthropic"):
        provider = AnthropicProvider()
    assert isinstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# get_provider() factory
# ---------------------------------------------------------------------------

def test_get_provider_returns_gemini_by_default() -> None:
    with patch("src.config.settings") as mock_settings, \
         patch("src.providers.gemini.genai.Client"):
        mock_settings.llm_provider = "gemini"
        provider = get_provider()
    assert isinstance(provider, GeminiProvider)


def test_get_provider_returns_anthropic_when_configured() -> None:
    with patch("src.config.settings") as mock_settings, \
         patch("src.providers.anthropic_provider.anthropic.Anthropic"):
        mock_settings.llm_provider = "anthropic"
        mock_settings.anthropic_api_key = None
        provider = get_provider()
    assert isinstance(provider, AnthropicProvider)


def test_get_provider_raises_for_unknown_provider() -> None:
    with patch("src.config.settings") as mock_settings:
        mock_settings.llm_provider = "openai"
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider()


# ---------------------------------------------------------------------------
# Protocol completeness — stream methods must be declared
# ---------------------------------------------------------------------------

class _FullProvider:
    """Minimal duck-type with ALL 4 methods (complete + stream)."""

    def complete(self, context):
        return MagicMock()

    def complete_with_tools(self, context, tool_calls, tool_results):
        return MagicMock()

    def stream(self, context):
        return iter([])

    def stream_with_tools(self, context, tool_calls, tool_results):
        return iter([])


def test_protocol_declares_stream() -> None:
    """LLMProvider must declare stream() — all providers implement it."""
    assert hasattr(LLMProvider, "stream")


def test_protocol_declares_stream_with_tools() -> None:
    """LLMProvider must declare stream_with_tools() — all providers implement it."""
    assert hasattr(LLMProvider, "stream_with_tools")


def test_full_provider_satisfies_protocol() -> None:
    """Implementation with all 4 methods must satisfy protocol."""
    provider = _FullProvider()
    assert isinstance(provider, LLMProvider)


class _IncompleteProvider:
    """Only has complete + complete_with_tools — missing stream methods."""

    def complete(self, context):
        return MagicMock()

    def complete_with_tools(self, context, tool_calls, tool_results):
        return MagicMock()


def test_incomplete_provider_fails_isinstance() -> None:
    """Implementation missing stream() must NOT satisfy protocol."""
    provider = _IncompleteProvider()
    assert not isinstance(provider, LLMProvider)
