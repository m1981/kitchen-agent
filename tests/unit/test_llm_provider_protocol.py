"""
tests/unit/test_llm_provider_protocol.py
==========================================
Tests for the LLMProvider Protocol — completeness and correctness.

Observations addressed:
  2. Protocol only declares complete() and complete_with_tools() but all
     implementations also have stream() and stream_with_tools().
  3. @runtime_checkable with incomplete protocol gives false positives —
     any object with complete+complete_with_tools passes isinstance even
     if it lacks stream methods.

After fix:
  - LLMProvider Protocol declares all 4 methods
  - @runtime_checkable isinstance checks are accurate
  - All concrete providers still satisfy the protocol
"""
from __future__ import annotations

import inspect
from typing import Iterator, Any

import pytest

from src.providers.base import LLMProvider
from src.agent.context_assembler import AssembledContext
from src.agent.tool_executor import ToolCall, ToolResult


# ---------------------------------------------------------------------------
# Minimal implementations for testing protocol shape
# ---------------------------------------------------------------------------

class FullProvider:
    """Minimal implementation with ALL 4 methods."""

    def complete(self, context: AssembledContext) -> Any:
        return MagicMock()

    def complete_with_tools(
        self, context: AssembledContext,
        tool_calls: list[ToolCall], tool_results: list[ToolResult],
    ) -> Any:
        return MagicMock()

    def stream(self, context: AssembledContext) -> Iterator[Any]:
        return iter([])

    def stream_with_tools(
        self, context: AssembledContext,
        tool_calls: list[ToolCall], tool_results: list[ToolResult],
    ) -> Iterator[Any]:
        return iter([])


class IncompleteProvider:
    """Only has complete + complete_with_tools — missing stream methods."""

    def complete(self, context: AssembledContext) -> Any:
        return MagicMock()

    def complete_with_tools(
        self, context: AssembledContext,
        tool_calls: list[ToolCall], tool_results: list[ToolResult],
    ) -> Any:
        return MagicMock()


# Use MagicMock for return values in protocol tests
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Tests: Protocol method declarations
# ---------------------------------------------------------------------------

class TestLLMProviderProtocolMethods:
    """LLMProvider Protocol must declare all 4 provider methods."""

    def test_declares_complete(self):
        """Protocol must declare complete()."""
        assert hasattr(LLMProvider, "complete")

    def test_declares_complete_with_tools(self):
        """Protocol must declare complete_with_tools()."""
        assert hasattr(LLMProvider, "complete_with_tools")

    def test_declares_stream(self):
        """Protocol must declare stream()."""
        assert hasattr(LLMProvider, "stream"), (
            "LLMProvider Protocol must declare stream() — "
            "all providers implement it but Protocol omits it."
        )

    def test_declares_stream_with_tools(self):
        """Protocol must declare stream_with_tools()."""
        assert hasattr(LLMProvider, "stream_with_tools"), (
            "LLMProvider Protocol must declare stream_with_tools() — "
            "all providers implement it but Protocol omits it."
        )


# ---------------------------------------------------------------------------
# Tests: runtime_checkable isinstance accuracy
# ---------------------------------------------------------------------------

class TestRuntimeCheckableAccuracy:
    """
    @runtime_checkable Protocol: isinstance checks must be accurate.
    An incomplete implementation must NOT pass isinstance.
    """

    def test_full_provider_passes_isinstance(self):
        """Full implementation (all 4 methods) must satisfy protocol."""
        provider = FullProvider()
        assert isinstance(provider, LLMProvider), (
            "FullProvider implements all 4 methods but isinstance fails."
        )

    def test_incomplete_provider_fails_isinstance(self):
        """Incomplete implementation (missing stream) must FAIL isinstance."""
        provider = IncompleteProvider()
        assert not isinstance(provider, LLMProvider), (
            "IncompleteProvider lacks stream() but isinstance passes — "
            "Protocol is missing method declarations."
        )


# ---------------------------------------------------------------------------
# Tests: Concrete providers satisfy the full protocol
# ---------------------------------------------------------------------------

class TestConcreteProvidersSatisfyProtocol:
    """All 3 concrete providers must satisfy the full LLMProvider protocol."""

    def test_gemini_satisfies_protocol(self):
        from unittest.mock import patch
        with patch("src.providers.gemini.genai.Client"):
            from src.providers.gemini import GeminiProvider
            provider = GeminiProvider()
        assert isinstance(provider, LLMProvider)

    def test_anthropic_satisfies_protocol(self):
        from unittest.mock import patch
        with patch("src.providers.anthropic_provider.anthropic.Anthropic"):
            from src.providers.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider()
        assert isinstance(provider, LLMProvider)

    def test_mimo_satisfies_protocol(self):
        from unittest.mock import patch
        with patch("src.providers.mimo_provider.OpenAI"):
            from src.providers.mimo_provider import MimoProvider
            provider = MimoProvider()
        assert isinstance(provider, LLMProvider)
