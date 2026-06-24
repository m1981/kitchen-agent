"""
Tests for provider streaming methods.

Each provider must implement:
- stream(context) → yields raw SDK chunks
- stream_with_tools(context, tool_calls, tool_results) → yields raw SDK chunks

The normalizer already has chunk text extractors for each provider.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Iterator, Any


# ---------------------------------------------------------------------------
# Gemini Provider Streaming
# ---------------------------------------------------------------------------

class TestGeminiProviderStream:
    """Test GeminiProvider.stream() method."""

    def _make_provider(self):
        """Create a GeminiProvider with mocked dependencies."""
        with patch("src.providers.gemini.genai.Client") as mock_client_cls, \
             patch("src.providers.gemini._build_default_registry") as mock_registry:
            
            mock_registry.return_value = MagicMock(
                get_all_entries=MagicMock(return_value=[])
            )
            
            from src.providers.gemini import GeminiProvider
            provider = GeminiProvider.__new__(GeminiProvider)
            provider._client = MagicMock()
            provider._model = "gemini-2.5-flash"
            provider._normalizer = MagicMock()
            provider._registry = MagicMock()
            provider._tool_executor = MagicMock()
            provider._conversation_state = []
            
            return provider

    def test_stream_method_exists(self):
        """GeminiProvider must have a stream() method."""
        from src.providers.gemini import GeminiProvider
        assert hasattr(GeminiProvider, "stream")
        assert callable(getattr(GeminiProvider, "stream"))

    def test_stream_returns_iterator(self):
        """stream() must return an iterator."""
        provider = self._make_provider()
        
        # Mock generate_content_stream to return an iterator
        provider._client.models.generate_content_stream = MagicMock(
            return_value=iter([
                MagicMock(candidates=[MagicMock(content=MagicMock(parts=[MagicMock(text="Hello")]))]),
                MagicMock(candidates=[MagicMock(content=MagicMock(parts=[MagicMock(text=" world")]))]),
            ])
        )
        
        context = MagicMock(
            system_prompt="test",
            messages=[{"role": "user", "content": "hi"}],
            images=[],
            context_files=[],
            tool_schemas=[],
        )
        
        result = provider.stream(context)
        assert hasattr(result, "__iter__")
        assert hasattr(result, "__next__")

    def test_stream_yields_chunks(self):
        """stream() must yield raw SDK chunks."""
        provider = self._make_provider()
        
        chunk1 = MagicMock(candidates=[MagicMock(content=MagicMock(parts=[MagicMock(text="Hello")]))])
        chunk2 = MagicMock(candidates=[MagicMock(content=MagicMock(parts=[MagicMock(text=" world")]))])
        
        provider._client.models.generate_content_stream = MagicMock(
            return_value=iter([chunk1, chunk2])
        )
        
        context = MagicMock(
            system_prompt="test",
            messages=[{"role": "user", "content": "hi"}],
            images=[],
            context_files=[],
            tool_schemas=[],
        )
        
        chunks = list(provider.stream(context))
        assert len(chunks) == 2
        assert chunks[0] is chunk1
        assert chunks[1] is chunk2

    def test_stream_with_tools_method_exists(self):
        """GeminiProvider must have a stream_with_tools() method."""
        from src.providers.gemini import GeminiProvider
        assert hasattr(GeminiProvider, "stream_with_tools")
        assert callable(getattr(GeminiProvider, "stream_with_tools"))


# ---------------------------------------------------------------------------
# Anthropic Provider Streaming
# ---------------------------------------------------------------------------

class TestAnthropicProviderStream:
    """Test AnthropicProvider.stream() method."""

    def _make_provider(self):
        """Create an AnthropicProvider with mocked dependencies."""
        with patch("src.providers.anthropic_provider.settings") as mock_settings:
            
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.anthropic_model = "claude-sonnet-4-20250514"
            mock_settings.anthropic_max_tokens = 4096
            
            from src.providers.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider.__new__(AnthropicProvider)
            provider._client = MagicMock()
            provider._model = "claude-sonnet-4-20250514"
            provider._registry = MagicMock()
            provider._tool_schemas = []
            provider._conversation_state = []
            
            return provider

    def test_stream_method_exists(self):
        """AnthropicProvider must have a stream() method."""
        from src.providers.anthropic_provider import AnthropicProvider
        assert hasattr(AnthropicProvider, "stream")
        assert callable(getattr(AnthropicProvider, "stream"))

    def test_stream_returns_iterator(self):
        """stream() must return an iterator."""
        provider = self._make_provider()
        
        # Mock the messages.stream context manager
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter([
            MagicMock(type="content_block_delta", delta=MagicMock(type="text_delta", text="Hello")),
        ]))
        
        provider._client.messages.stream = MagicMock(return_value=mock_stream)
        
        context = MagicMock(
            system_prompt="test",
            messages=[{"role": "user", "content": "hi"}],
            images=[],
            context_files=[],
        )
        
        result = provider.stream(context)
        assert hasattr(result, "__iter__")
        assert hasattr(result, "__next__")

    def test_stream_with_tools_method_exists(self):
        """AnthropicProvider must have a stream_with_tools() method."""
        from src.providers.anthropic_provider import AnthropicProvider
        assert hasattr(AnthropicProvider, "stream_with_tools")
        assert callable(getattr(AnthropicProvider, "stream_with_tools"))


# ---------------------------------------------------------------------------
# Mimo Provider Streaming
# ---------------------------------------------------------------------------

class TestMimoProviderStream:
    """Test MimoProvider.stream() method."""

    def _make_provider(self):
        """Create a MimoProvider with mocked dependencies."""
        with patch("src.providers.mimo_provider.settings") as mock_settings, \
             patch("src.providers.mimo_provider._build_default_registry") as mock_registry:
            
            mock_settings.mimo_api_key = "test-key"
            mock_settings.mimo_base_url = "https://test.api.com"
            mock_settings.mimo_model = "mimo-v2.5-pro"
            mock_settings.mimo_temperature = 0.7
            mock_settings.mimo_max_tokens = 4096
            
            mock_registry.return_value = MagicMock(
                get_all_entries=MagicMock(return_value=[])
            )
            
            from src.providers.mimo_provider import MimoProvider
            provider = MimoProvider.__new__(MimoProvider)
            provider._client = MagicMock()
            provider._model = "mimo-v2.5-pro"
            provider._temperature = 0.7
            provider._max_tokens = 4096
            provider._registry = MagicMock()
            provider._tool_executor = MagicMock()
            provider._conversation_state = []
            
            return provider

    def test_stream_method_exists(self):
        """MimoProvider must have a stream() method."""
        from src.providers.mimo_provider import MimoProvider
        assert hasattr(MimoProvider, "stream")
        assert callable(getattr(MimoProvider, "stream"))

    def test_stream_returns_iterator(self):
        """stream() must return an iterator."""
        provider = self._make_provider()
        
        # Mock chat.completions.create with stream=True
        provider._client.chat.completions.create = MagicMock(
            return_value=iter([
                MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))]),
            ])
        )
        
        context = MagicMock(
            system_prompt="test",
            messages=[{"role": "user", "content": "hi"}],
            images=[],
            context_files=[],
            tool_schemas=[],
        )
        
        result = provider.stream(context)
        assert hasattr(result, "__iter__")
        assert hasattr(result, "__next__")

    def test_stream_passes_stream_true(self):
        """stream() must pass stream=True to the API client."""
        provider = self._make_provider()
        
        provider._client.chat.completions.create = MagicMock(
            return_value=iter([])
        )
        
        context = MagicMock(
            system_prompt="test",
            messages=[{"role": "user", "content": "hi"}],
            images=[],
            context_files=[],
            tool_schemas=None,  # No tools
        )
        
        list(provider.stream(context))
        
        # Verify stream=True was passed
        call_kwargs = provider._client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("stream") is True or call_kwargs[1].get("stream") is True

    def test_stream_with_tools_method_exists(self):
        """MimoProvider must have a stream_with_tools() method."""
        from src.providers.mimo_provider import MimoProvider
        assert hasattr(MimoProvider, "stream_with_tools")
        assert callable(getattr(MimoProvider, "stream_with_tools"))
