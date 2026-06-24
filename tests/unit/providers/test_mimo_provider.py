"""
tests/test_mimo_provider.py
============================
Tests for the Xiaomi Mimo provider.

Verifies:
  - MimoProvider satisfies LLMProvider Protocol
  - get_provider() returns MimoProvider when configured
  - Normalizer handles OpenAI-compatible responses
  - Provider catalogue includes mimo
"""
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass

import pytest

from src.providers.base import LLMProvider, get_provider
from src.providers.mimo_provider import MimoProvider
from src.providers.normalizer import ResponseNormalizer, NormalizedResponse


# ---------------------------------------------------------------------------
# Mock OpenAI response objects
# ---------------------------------------------------------------------------

def _make_mock_message(content="Hello", tool_calls=None):
    """Create a mock OpenAI ChatCompletionMessage."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    return msg


def _make_mock_choice(message=None):
    """Create a mock OpenAI Choice."""
    choice = MagicMock()
    choice.message = message or _make_mock_message()
    return choice


def _make_mock_completion(choices=None, input_tokens=10, output_tokens=5):
    """Create a mock OpenAI ChatCompletion."""
    completion = MagicMock()
    completion.choices = choices or [_make_mock_choice()]
    completion.usage = MagicMock(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
    )
    return completion


def _make_mock_tool_call(name="read_file", args='{"filepath": "test.md"}', call_id="call-1"):
    """Create a mock OpenAI ToolCall."""
    tc = MagicMock()
    tc.id = call_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = args
    return tc


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_mimo_provider_satisfies_protocol() -> None:
    """MimoProvider must satisfy the LLMProvider Protocol."""
    with patch("src.providers.mimo_provider.OpenAI"):
        provider = MimoProvider()
    assert isinstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# get_provider() factory
# ---------------------------------------------------------------------------

def test_get_provider_returns_mimo_when_configured() -> None:
    with patch("src.config.settings") as mock_settings, \
         patch("src.providers.mimo_provider.OpenAI"):
        mock_settings.llm_provider = "mimo"
        mock_settings.mimo_api_key = None
        mock_settings.mimo_base_url = "https://api.xiaomimimo.com/v1"
        mock_settings.mimo_model = "mimo-v2.5-pro"
        provider = get_provider()
    assert isinstance(provider, MimoProvider)


def test_get_provider_mimo_with_model_override() -> None:
    with patch("src.config.settings") as mock_settings, \
         patch("src.providers.mimo_provider.OpenAI"):
        mock_settings.llm_provider = "mimo"
        mock_settings.mimo_api_key = None
        mock_settings.mimo_base_url = "https://api.xiaomimimo.com/v1"
        mock_settings.mimo_model = "mimo-v2.5-pro"
        provider = get_provider(model_override="mimo-v2.5")
    assert isinstance(provider, MimoProvider)
    assert provider._model == "mimo-v2.5"


# ---------------------------------------------------------------------------
# Normalizer — OpenAI-compatible responses
# ---------------------------------------------------------------------------

class TestNormalizerMimo:
    def test_text_response(self):
        normalizer = ResponseNormalizer()
        mock_response = _make_mock_completion(
            choices=[_make_mock_choice(_make_mock_message("Hello from MiMo"))]
        )

        result = normalizer.normalize(mock_response, "mimo")

        assert result.text == "Hello from MiMo"
        assert result.has_tool_calls is False
        assert result.tool_calls == []

    def test_tool_call_response(self):
        normalizer = ResponseNormalizer()
        mock_tc = _make_mock_tool_call("read_file", '{"filepath": "test.md"}', "call-1")
        mock_response = _make_mock_completion(
            choices=[_make_mock_choice(_make_mock_message(None, tool_calls=[mock_tc]))]
        )

        result = normalizer.normalize(mock_response, "mimo")

        assert result.text == ""
        assert result.has_tool_calls is True
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"filepath": "test.md"}
        assert result.tool_calls[0].id == "call-1"

    def test_usage_populated(self):
        normalizer = ResponseNormalizer()
        mock_response = _make_mock_completion(input_tokens=100, output_tokens=50)

        result = normalizer.normalize(mock_response, "mimo")

        assert result.usage["input"] == 100
        assert result.usage["output"] == 50
        assert result.usage["total"] == 150

    def test_mixed_text_and_tool_calls(self):
        normalizer = ResponseNormalizer()
        mock_tc = _make_mock_tool_call("search_knowledge_base", '{"query": "blum"}', "call-2")
        mock_response = _make_mock_completion(
            choices=[_make_mock_choice(_make_mock_message("Let me search...", tool_calls=[mock_tc]))]
        )

        result = normalizer.normalize(mock_response, "mimo")

        assert result.text == "Let me search..."
        assert result.has_tool_calls is True
        assert len(result.tool_calls) == 1

    def test_chunk_text(self):
        normalizer = ResponseNormalizer()
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Hello"

        result = normalizer.normalize_chunk(chunk, "mimo")
        assert result == "Hello"

    def test_chunk_empty(self):
        normalizer = ResponseNormalizer()
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = None

        result = normalizer.normalize_chunk(chunk, "mimo")
        assert result == ""


# ---------------------------------------------------------------------------
# Provider catalogue
# ---------------------------------------------------------------------------

def test_provider_catalogue_includes_mimo() -> None:
    from src.api.providers import _PROVIDER_CATALOGUE

    provider_ids = [p.id for p in _PROVIDER_CATALOGUE]
    assert "mimo" in provider_ids


def test_mimo_provider_has_two_models() -> None:
    from src.api.providers import _PROVIDER_CATALOGUE

    mimo = next(p for p in _PROVIDER_CATALOGUE if p.id == "mimo")
    model_ids = [m.id for m in mimo.models]
    assert "mimo-v2.5-pro" in model_ids
    assert "mimo-v2.5" in model_ids


def test_mimo_default_model_is_pro() -> None:
    from src.api.providers import _PROVIDER_CATALOGUE

    mimo = next(p for p in _PROVIDER_CATALOGUE if p.id == "mimo")
    assert mimo.default_model == "mimo-v2.5-pro"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_config_has_mimo_settings() -> None:
    from src.config import Settings

    s = Settings()
    assert hasattr(s, "mimo_api_key")
    assert hasattr(s, "mimo_base_url")
    assert hasattr(s, "mimo_model")
    assert hasattr(s, "mimo_temperature")
    assert hasattr(s, "mimo_max_tokens")


def test_config_mimo_defaults() -> None:
    from src.config import Settings

    s = Settings()
    assert s.mimo_base_url == "https://api.xiaomimimo.com/v1"
    assert s.mimo_model == "mimo-v2.5-pro"
    assert s.mimo_temperature == 0.2
    assert s.mimo_max_tokens == 8096


# ---------------------------------------------------------------------------
# Active provider endpoint
# ---------------------------------------------------------------------------

def test_active_provider_mimo() -> None:
    from src.api.providers import get_active_provider
    from src.config import settings

    with patch.object(settings, "llm_provider", "mimo"), \
         patch.object(settings, "mimo_model", "mimo-v2.5-pro"):
        result = get_active_provider()
    assert result.provider == "mimo"
    assert result.model == "mimo-v2.5-pro"


# ---------------------------------------------------------------------------
# Regression: tool_call_id preserved across turns (OpenAI format)
# ---------------------------------------------------------------------------

class TestToolHistoryConversion:
    """
    Regression tests for the bug where tool call/response messages from
    previous turns were passed through naively, losing tool_calls and
    tool_call_id fields. This caused:
        openai.BadRequestError: '`tool_call_id` is not set'
    """

    @staticmethod
    def _make_context_with_tool_history():
        """Build a mock context with tool call/response history (common format)."""
        from unittest.mock import MagicMock

        context = MagicMock()
        context.system_prompt = "You are helpful."
        context.messages = [
            {"role": "user", "content": "Find hinges", "turn_id": "t1"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-abc123",
                        "name": "search_knowledge_base",
                        "arguments": {"query": "hinge"},
                    }
                ],
                "turn_id": "t2",
            },
            {
                "role": "tool",
                "tool_call_id": "call-abc123",
                "content": '{"content": "Blum hinges are..."}',
                "turn_id": "t2",
            },
            {
                "role": "assistant",
                "content": "I found info about Blum hinges.",
                "turn_id": "t3",
            },
        ]
        context.context_files = []
        context.images = []
        return context

    def test_assistant_tool_call_message_has_tool_calls_key(self):
        """Assistant messages with tool_calls must preserve tool_calls in OpenAI format."""
        with patch("src.providers.mimo_provider.OpenAI"):
            provider = MimoProvider()

        context = self._make_context_with_tool_history()
        messages = provider._build_messages(context)

        # Message 2 is the assistant tool call (index 0=system, 1=user, 2=assistant)
        tool_call_msg = messages[2]
        assert tool_call_msg["role"] == "assistant"
        assert "tool_calls" in tool_call_msg
        assert len(tool_call_msg["tool_calls"]) == 1

    def test_assistant_tool_call_has_openai_structure(self):
        """Tool calls must have id, type, and function wrapper (OpenAI format)."""
        with patch("src.providers.mimo_provider.OpenAI"):
            provider = MimoProvider()

        context = self._make_context_with_tool_history()
        messages = provider._build_messages(context)

        tc = messages[2]["tool_calls"][0]
        assert tc["id"] == "call-abc123"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "search_knowledge_base"
        assert tc["function"]["arguments"] == '{"query": "hinge"}'

    def test_tool_result_message_has_tool_call_id(self):
        """Tool result messages must preserve tool_call_id for OpenAI API."""
        with patch("src.providers.mimo_provider.OpenAI"):
            provider = MimoProvider()

        context = self._make_context_with_tool_history()
        messages = provider._build_messages(context)

        # Message 3 is the tool result
        tool_result_msg = messages[3]
        assert tool_result_msg["role"] == "tool"
        assert tool_result_msg["tool_call_id"] == "call-abc123"
        assert "content" in tool_result_msg

    def test_tool_result_message_stripped_of_extra_fields(self):
        """Extra fields like turn_id should not leak into API messages."""
        with patch("src.providers.mimo_provider.OpenAI"):
            provider = MimoProvider()

        context = self._make_context_with_tool_history()
        messages = provider._build_messages(context)

        tool_result_msg = messages[3]
        assert "turn_id" not in tool_result_msg
        # Only role, tool_call_id, content should be present
        assert set(tool_result_msg.keys()) == {"role", "tool_call_id", "content"}

    def test_multiple_tool_calls_all_converted(self):
        """Multiple tool calls in one assistant message are all converted."""
        from unittest.mock import MagicMock

        with patch("src.providers.mimo_provider.OpenAI"):
            provider = MimoProvider()

        context = MagicMock()
        context.system_prompt = None
        context.messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-1", "name": "read_file", "arguments": {"filepath": "a.md"}},
                    {"id": "call-2", "name": "read_file", "arguments": {"filepath": "b.md"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "content A"},
            {"role": "tool", "tool_call_id": "call-2", "content": "content B"},
        ]
        context.context_files = []
        context.images = []

        messages = provider._build_messages(context)

        # First message: assistant with 2 tool calls
        assert len(messages[0]["tool_calls"]) == 2
        assert messages[0]["tool_calls"][0]["id"] == "call-1"
        assert messages[0]["tool_calls"][1]["id"] == "call-2"

        # Tool results
        assert messages[1]["tool_call_id"] == "call-1"
        assert messages[2]["tool_call_id"] == "call-2"

    def test_user_message_without_tools_passes_through(self):
        """Plain user/assistant messages without tools are unaffected."""
        from unittest.mock import MagicMock

        with patch("src.providers.mimo_provider.OpenAI"):
            provider = MimoProvider()

        context = MagicMock()
        context.system_prompt = None
        context.messages = [
            {"role": "user", "content": "Hello", "turn_id": "t1"},
            {"role": "assistant", "content": "Hi!", "turn_id": "t2"},
        ]
        context.context_files = []
        context.images = []

        messages = provider._build_messages(context)

        assert messages[0] == {"role": "user", "content": "Hello"}
        assert messages[1] == {"role": "assistant", "content": "Hi!"}
        # turn_id should be stripped
        assert "turn_id" not in messages[0]
        assert "turn_id" not in messages[1]
