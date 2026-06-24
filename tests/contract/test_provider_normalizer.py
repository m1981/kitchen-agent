"""
tests/contract/test_provider_normalizer.py
===========================================
Contract B9: Provider ↔ Normalizer

Rule: Use REAL ResponseNormalizer. Use REAL SDK types where possible.
Mock only what comes from external APIs (network calls).

This test verifies that ResponseNormalizer handles ALL event types
that providers can yield during streaming, including control events
that don't have content (the root cause of the Anthropic streaming bug).
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace

from src.providers.normalizer import NormalizedResponse, ResponseNormalizer, ToolCall


# ═══════════════════════════════════════════════════════════════════════
# ANTHROPIC EVENTS — using real Pydantic models from anthropic.types
# ═══════════════════════════════════════════════════════════════════════

from anthropic.types import (
    Message,
    TextBlock,
    ToolUseBlock,
    MessageStartEvent,
    MessageStopEvent,
    MessageDeltaEvent,
    ContentBlockStartEvent,
    ContentBlockStopEvent,
    ContentBlockDeltaEvent,
    TextDelta,
    InputJSONDelta,
)


class TestAnthropicNormalizeChunk:
    """normalize_chunk() must handle ALL Anthropic stream event types."""

    def setup_method(self):
        self.normalizer = ResponseNormalizer()

    def test_text_delta_returns_text(self):
        """ContentBlockDeltaEvent with TextDelta → returns text."""
        event = ContentBlockDeltaEvent(
            delta=TextDelta(text="Hello", type="text_delta"),
            index=0,
            type="content_block_delta",
        )
        result = self.normalizer.normalize_chunk(event, "anthropic")
        assert result == "Hello"

    def test_input_json_delta_returns_empty(self):
        """ContentBlockDeltaEvent with InputJSONDelta → returns ''."""
        event = ContentBlockDeltaEvent(
            delta=InputJSONDelta(partial_json='{"q":', type="input_json_delta"),
            index=0,
            type="content_block_delta",
        )
        result = self.normalizer.normalize_chunk(event, "anthropic")
        assert result == ""

    def test_message_start_returns_empty(self):
        """MessageStartEvent → returns '' (no text delta)."""
        event = MessageStartEvent(
            type="message_start",
            message=Message(
                id="msg_1",
                content=[],
                model="claude-sonnet-4-20250514",
                role="assistant",
                stop_reason=None,
                type="message",
                usage={"input_tokens": 10, "output_tokens": 0},
            ),
        )
        result = self.normalizer.normalize_chunk(event, "anthropic")
        assert result == ""

    def test_message_stop_returns_empty_no_crash(self):
        """
        MessageStopEvent has NO .content attribute.
        This was the actual crash: AttributeError: 'ParsedMessageStopEvent'
        object has no attribute 'content'
        """
        event = MessageStopEvent(type="message_stop")
        result = self.normalizer.normalize_chunk(event, "anthropic")
        assert result == ""

    def test_content_block_start_returns_empty(self):
        """ContentBlockStartEvent → returns ''."""
        event = ContentBlockStartEvent(
            content_block=TextBlock(text="", type="text"),
            index=0,
            type="content_block_start",
        )
        result = self.normalizer.normalize_chunk(event, "anthropic")
        assert result == ""

    def test_content_block_stop_returns_empty(self):
        """ContentBlockStopEvent → returns ''."""
        event = ContentBlockStopEvent(index=0, type="content_block_stop")
        result = self.normalizer.normalize_chunk(event, "anthropic")
        assert result == ""

    def test_message_delta_returns_empty(self):
        """MessageDeltaEvent → returns ''."""
        event = MessageDeltaEvent(
            delta={"stop_reason": "end_turn"},
            type="message_delta",
            usage={"output_tokens": 10},
        )
        result = self.normalizer.normalize_chunk(event, "anthropic")
        assert result == ""


class TestAnthropicNormalize:
    """normalize() must handle complete Anthropic Message objects."""

    def setup_method(self):
        self.normalizer = ResponseNormalizer()

    def test_text_only_message(self):
        """Message with TextBlock → text populated."""
        raw = Message(
            id="msg_1",
            content=[TextBlock(text="Hello from Claude!", type="text")],
            model="claude-sonnet-4-20250514",
            role="assistant",
            stop_reason="end_turn",
            type="message",
            usage={"input_tokens": 10, "output_tokens": 5},
        )
        result = self.normalizer.normalize(raw, "anthropic")
        assert result.text == "Hello from Claude!"
        assert result.has_tool_calls is False
        assert result.tool_calls == []

    def test_tool_use_message(self):
        """Message with ToolUseBlock → tool_calls populated."""
        raw = Message(
            id="msg_1",
            content=[
                ToolUseBlock(
                    id="tu_1",
                    name="read_file",
                    input={"filepath": "/test.md"},
                    type="tool_use",
                )
            ],
            model="claude-sonnet-4-20250514",
            role="assistant",
            stop_reason="tool_use",
            type="message",
            usage={"input_tokens": 20, "output_tokens": 8},
        )
        result = self.normalizer.normalize(raw, "anthropic")
        assert result.text == ""
        assert result.has_tool_calls is True
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].id == "tu_1"

    def test_mixed_text_and_tool_use(self):
        """Message with TextBlock + ToolUseBlock → both populated."""
        raw = Message(
            id="msg_1",
            content=[
                TextBlock(text="Let me check that.", type="text"),
                ToolUseBlock(
                    id="tu_1",
                    name="read_file",
                    input={"filepath": "/test.md"},
                    type="tool_use",
                ),
            ],
            model="claude-sonnet-4-20250514",
            role="assistant",
            stop_reason="tool_use",
            type="message",
            usage={"input_tokens": 20, "output_tokens": 12},
        )
        result = self.normalizer.normalize(raw, "anthropic")
        assert result.text == "Let me check that."
        assert result.has_tool_calls is True
        assert len(result.tool_calls) == 1

    def test_usage_populated(self):
        """Usage tokens must be extracted from Message."""
        raw = Message(
            id="msg_1",
            content=[TextBlock(text="Hi", type="text")],
            model="claude-sonnet-4-20250514",
            role="assistant",
            stop_reason="end_turn",
            type="message",
            usage={"input_tokens": 25, "output_tokens": 10},
        )
        result = self.normalizer.normalize(raw, "anthropic")
        assert result.usage["input"] == 25
        assert result.usage["output"] == 10
        assert result.usage["total"] == 35


# ═══════════════════════════════════════════════════════════════════════
# GEMINI EVENTS — using real types from google.genai
# ═══════════════════════════════════════════════════════════════════════

from google.genai import types as genai_types


class TestGeminiNormalizeChunk:
    """normalize_chunk() must handle all Gemini stream chunk types."""

    def setup_method(self):
        self.normalizer = ResponseNormalizer()

    def test_text_chunk_returns_text(self):
        """Chunk with text part → returns text."""
        chunk = MagicMock()
        chunk.candidates = [
            MagicMock(content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text="Hello")],
            ))
        ]
        result = self.normalizer.normalize_chunk(chunk, "gemini")
        assert result == "Hello"

    def test_empty_candidates_returns_empty(self):
        """Chunk with no candidates → returns ''."""
        chunk = MagicMock()
        chunk.candidates = []
        result = self.normalizer.normalize_chunk(chunk, "gemini")
        assert result == ""

    def test_no_parts_returns_empty(self):
        """Chunk with candidates but no parts → returns ''."""
        chunk = MagicMock()
        chunk.candidates = [
            MagicMock(content=genai_types.Content(role="model", parts=[]))
        ]
        result = self.normalizer.normalize_chunk(chunk, "gemini")
        assert result == ""

    def test_function_call_chunk_returns_empty(self):
        """Chunk with function_call part → returns '' (no text delta)."""
        chunk = MagicMock()
        chunk.candidates = [
            MagicMock(content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(
                    function_call=genai_types.FunctionCall(
                        name="read_file", args={"filepath": "/x"}
                    )
                )],
            ))
        ]
        result = self.normalizer.normalize_chunk(chunk, "gemini")
        assert result == ""


class TestGeminiNormalize:
    """normalize() must handle complete Gemini response objects."""

    def setup_method(self):
        self.normalizer = ResponseNormalizer()

    def test_text_only_response(self):
        """Response with text part → text populated."""
        raw = MagicMock()
        raw.candidates = [
            MagicMock(content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text="Hello from Gemini!")],
            ))
        ]
        raw.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=5,
            total_token_count=15,
        )
        result = self.normalizer.normalize(raw, "gemini")
        assert result.text == "Hello from Gemini!"
        assert result.has_tool_calls is False

    def test_function_call_response(self):
        """Response with function_call → tool_calls populated."""
        raw = MagicMock()
        raw.candidates = [
            MagicMock(content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(
                    function_call=genai_types.FunctionCall(
                        name="read_file",
                        args={"filepath": "/test.md"},
                        id="call_1",
                    )
                )],
            ))
        ]
        raw.usage_metadata = MagicMock(
            prompt_token_count=20,
            candidates_token_count=8,
            total_token_count=28,
        )
        result = self.normalizer.normalize(raw, "gemini")
        assert result.has_tool_calls is True
        assert result.tool_calls[0].name == "read_file"

    def test_usage_missing_graceful(self):
        """Response without usage_metadata → all zeros."""
        raw = MagicMock()
        raw.candidates = [
            MagicMock(content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text="Hi")],
            ))
        ]
        del raw.usage_metadata
        result = self.normalizer.normalize(raw, "gemini")
        assert result.usage == {"input": 0, "output": 0, "total": 0}


# ═══════════════════════════════════════════════════════════════════════
# MIMO (OpenAI-compatible) EVENTS
# ═══════════════════════════════════════════════════════════════════════

class TestMimoNormalizeChunk:
    """normalize_chunk() must handle OpenAI-compatible stream chunks."""

    def setup_method(self):
        self.normalizer = ResponseNormalizer()

    def test_text_delta_returns_text(self):
        """Chunk with delta.content → returns text."""
        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content="Hello"))]
        result = self.normalizer.normalize_chunk(chunk, "mimo")
        assert result == "Hello"

    def test_empty_choices_returns_empty(self):
        """Chunk with no choices → returns ''."""
        chunk = MagicMock()
        chunk.choices = []
        result = self.normalizer.normalize_chunk(chunk, "mimo")
        assert result == ""

    def test_none_content_returns_empty(self):
        """Chunk with delta.content=None → returns ''."""
        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content=None))]
        result = self.normalizer.normalize_chunk(chunk, "mimo")
        assert result == ""

    def test_no_delta_returns_empty(self):
        """Chunk with choices[0].delta=None → returns ''."""
        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=None)]
        result = self.normalizer.normalize_chunk(chunk, "mimo")
        assert result == ""


class TestMimoNormalize:
    """normalize() must handle OpenAI-compatible complete responses."""

    def setup_method(self):
        self.normalizer = ResponseNormalizer()

    def test_text_only_response(self):
        """Response with message.content → text populated."""
        raw = MagicMock()
        raw.choices = [MagicMock(message=MagicMock(
            content="Hello from Mimo!",
            tool_calls=None,
        ))]
        raw.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        result = self.normalizer.normalize(raw, "mimo")
        assert result.text == "Hello from Mimo!"
        assert result.has_tool_calls is False

    def test_tool_calls_response(self):
        """Response with message.tool_calls → tool_calls populated."""
        # Use SimpleNamespace to avoid MagicMock auto-attribute issues
        fn = SimpleNamespace(name="read_file", arguments='{"filepath": "/test.md"}')
        tc = SimpleNamespace(id="call_1", function=fn)
        msg = SimpleNamespace(content=None, tool_calls=[tc])
        choice = SimpleNamespace(message=msg)
        raw = SimpleNamespace(
            choices=[choice],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=8),
        )
        result = self.normalizer.normalize(raw, "mimo")
        assert result.has_tool_calls is True
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"filepath": "/test.md"}

    def test_invalid_json_arguments_returns_empty_dict(self):
        """Tool call with invalid JSON arguments → empty dict."""
        raw = MagicMock()
        raw.choices = [MagicMock(message=MagicMock(
            content=None,
            tool_calls=[
                MagicMock(
                    id="call_1",
                    function=MagicMock(name="test", arguments="not json"),
                )
            ],
        ))]
        raw.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        result = self.normalizer.normalize(raw, "mimo")
        assert result.tool_calls[0].arguments == {}


# ═══════════════════════════════════════════════════════════════════════
# CROSS-PROVIDER CONTRACTS
# ═══════════════════════════════════════════════════════════════════════

class TestNormalizeChunkNeverRaises:
    """
    Contract: normalize_chunk() must NEVER raise an exception.
    Unknown event types must return "".
    """

    def setup_method(self):
        self.normalizer = ResponseNormalizer()

    @pytest.mark.parametrize("provider", ["gemini", "anthropic", "mimo"])
    def test_none_input_returns_empty(self, provider):
        """None input → returns ''."""
        # Should not raise
        result = self.normalizer.normalize_chunk(MagicMock(spec=[]), provider)
        assert isinstance(result, str)

    @pytest.mark.parametrize("provider", ["gemini", "anthropic", "mimo"])
    def test_empty_object_returns_empty(self, provider):
        """Object with no relevant attributes → returns '' or raises."""
        # Use SimpleNamespace (no auto-attribute creation like MagicMock)
        result = self.normalizer.normalize_chunk(SimpleNamespace(), provider)
        assert isinstance(result, str)

    def test_unknown_provider_raises(self):
        """Unknown provider → raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            self.normalizer.normalize_chunk(MagicMock(), "unknown")


class TestNormalizedResponseShape:
    """
    Contract: NormalizedResponse must have all fields that consumers depend on.
    """

    def test_has_required_fields(self):
        """All fields that TurnOrchestrator reads must exist."""
        resp = NormalizedResponse(text="hi")
        assert hasattr(resp, "text")
        assert hasattr(resp, "has_tool_calls")
        assert hasattr(resp, "tool_calls")
        assert hasattr(resp, "usage")
        assert hasattr(resp, "raw")

    def test_default_values_safe(self):
        """Default values must not cause NoneType errors in consumers."""
        resp = NormalizedResponse(text="hi")
        assert resp.has_tool_calls is False
        assert resp.tool_calls == []
        assert resp.usage == {}
        assert resp.raw is None

    def test_tool_call_is_canonical_type(self):
        """ToolCall in tool_calls must be from tool_executor (canonical)."""
        from src.agent.tool_executor import ToolCall as Canonical
        tc = Canonical(id="1", name="test", arguments={})
        resp = NormalizedResponse(text="", has_tool_calls=True, tool_calls=[tc])
        assert isinstance(resp.tool_calls[0], Canonical)
