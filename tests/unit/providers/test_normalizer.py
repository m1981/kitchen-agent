"""
tests/unit/providers/test_normalizer.py
========================================
Unit tests for ResponseNormalizer — the provider-agnostic response adapter.

The normalizer absorbs all SDK-specific response shape differences so the
rest of the codebase only ever sees NormalizedResponse.

Phase 1 scope: normalize() and normalize_chunk() for Gemini and Anthropic.
Streaming chunk normalization is included but not yet wired to providers
(streaming is not used in the current codebase).

These tests use the same mock patterns as test_gemini_provider.py and
test_anthropic_provider.py to build realistic SDK response objects.
"""
import json
from unittest.mock import MagicMock

import pytest
import anthropic

from src.providers.normalizer import (
    NormalizedResponse,
    ResponseNormalizer,
    ToolCall,
)


# ---------------------------------------------------------------------------
# Gemini mock response helpers
# ---------------------------------------------------------------------------

def _gemini_text_response(text: str) -> MagicMock:
    """Build a mock Gemini response with a single text part."""
    from google.genai import types

    part = types.Part(text=text)
    mock = MagicMock()
    mock.candidates = [
        MagicMock(content=types.Content(role="model", parts=[part]))
    ]
    mock.text = text
    mock.usage_metadata = MagicMock(
        prompt_token_count=10,
        candidates_token_count=5,
        total_token_count=15,
    )
    return mock


def _gemini_tool_call_response(
    name: str, args: dict, call_id: str
) -> MagicMock:
    """Build a mock Gemini response with a single function_call part."""
    from google.genai import types

    part = types.Part(
        function_call=types.FunctionCall(name=name, args=args, id=call_id)
    )
    mock = MagicMock()
    mock.candidates = [
        MagicMock(content=types.Content(role="model", parts=[part]))
    ]
    mock.usage_metadata = MagicMock(
        prompt_token_count=20,
        candidates_token_count=8,
        total_token_count=28,
    )
    return mock


def _gemini_mixed_response(
    text: str, tool_calls: list[tuple[str, dict, str]]
) -> MagicMock:
    """Build a mock Gemini response with both text and function_call parts."""
    from google.genai import types

    parts = [types.Part(text=text)]
    for name, args, call_id in tool_calls:
        parts.append(
            types.Part(
                function_call=types.FunctionCall(name=name, args=args, id=call_id)
            )
        )
    mock = MagicMock()
    mock.candidates = [
        MagicMock(content=types.Content(role="model", parts=parts))
    ]
    mock.usage_metadata = MagicMock(
        prompt_token_count=30,
        candidates_token_count=12,
        total_token_count=42,
    )
    return mock


def _gemini_response_no_usage(text: str) -> MagicMock:
    """Build a mock Gemini response without usage_metadata."""
    from google.genai import types

    part = types.Part(text=text)
    mock = MagicMock()
    mock.candidates = [
        MagicMock(content=types.Content(role="model", parts=[part]))
    ]
    # No usage_metadata attribute at all
    del mock.usage_metadata
    return mock


# ---------------------------------------------------------------------------
# Anthropic mock response helpers
# ---------------------------------------------------------------------------

def _anthropic_text_block(text: str) -> MagicMock:
    block = MagicMock(spec=anthropic.types.TextBlock)
    block.type = "text"
    block.text = text
    return block


def _anthropic_tool_use_block(
    name: str, tool_input: dict, tool_id: str
) -> MagicMock:
    block = MagicMock(spec=anthropic.types.ToolUseBlock)
    block.type = "tool_use"
    block.name = name
    block.input = tool_input
    block.id = tool_id
    return block


def _anthropic_response(
    content_blocks: list, input_tokens: int = 10, output_tokens: int = 5
) -> MagicMock:
    msg = MagicMock()
    msg.content = content_blocks
    msg.usage = MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return msg


# ---------------------------------------------------------------------------
# Tests: Gemini text response
# ---------------------------------------------------------------------------

class TestGeminiTextResponse:
    def test_text_populated(self):
        normalizer = ResponseNormalizer()
        raw = _gemini_text_response("Hello from Gemini!")

        result = normalizer.normalize(raw, provider="gemini")

        assert result.text == "Hello from Gemini!"

    def test_has_tool_calls_false(self):
        normalizer = ResponseNormalizer()
        raw = _gemini_text_response("Hello!")

        result = normalizer.normalize(raw, provider="gemini")

        assert result.has_tool_calls is False

    def test_tool_calls_empty(self):
        normalizer = ResponseNormalizer()
        raw = _gemini_text_response("Hello!")

        result = normalizer.normalize(raw, provider="gemini")

        assert result.tool_calls == []

    def test_usage_populated(self):
        normalizer = ResponseNormalizer()
        raw = _gemini_text_response("Hello!")

        result = normalizer.normalize(raw, provider="gemini")

        assert result.usage["input"] == 10
        assert result.usage["output"] == 5
        assert result.usage["total"] == 15

    def test_usage_missing_graceful(self):
        normalizer = ResponseNormalizer()
        raw = _gemini_response_no_usage("Hello!")

        result = normalizer.normalize(raw, provider="gemini")

        # All zeros when usage_metadata absent
        assert result.usage["input"] == 0
        assert result.usage["output"] == 0
        assert result.usage["total"] == 0


# ---------------------------------------------------------------------------
# Tests: Gemini tool call response
# ---------------------------------------------------------------------------

class TestGeminiToolCallResponse:
    def test_has_tool_calls_true(self):
        normalizer = ResponseNormalizer()
        raw = _gemini_tool_call_response("read_file", {"filepath": "x.md"}, "call_1")

        result = normalizer.normalize(raw, provider="gemini")

        assert result.has_tool_calls is True

    def test_tool_calls_populated(self):
        normalizer = ResponseNormalizer()
        raw = _gemini_tool_call_response("read_file", {"filepath": "x.md"}, "call_1")

        result = normalizer.normalize(raw, provider="gemini")

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"filepath": "x.md"}
        assert result.tool_calls[0].id == "call_1"

    def test_tool_call_id_falls_back_to_name(self):
        """When function_call has no id, use name as id."""
        from google.genai import types

        part = types.Part(
            function_call=types.FunctionCall(
                name="search_knowledge_base", args={"query": "test"}
            )
        )
        # Remove id if present
        fc = part.function_call
        if hasattr(fc, "id"):
            fc.id = ""

        mock = MagicMock()
        mock.candidates = [
            MagicMock(content=types.Content(role="model", parts=[part]))
        ]
        mock.usage_metadata = MagicMock(
            prompt_token_count=5,
            candidates_token_count=3,
            total_token_count=8,
        )

        normalizer = ResponseNormalizer()
        result = normalizer.normalize(mock, provider="gemini")

        # Should still produce a tool call even without an explicit id
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "search_knowledge_base"

    def test_text_empty_for_tool_only_response(self):
        normalizer = ResponseNormalizer()
        raw = _gemini_tool_call_response("read_file", {"filepath": "x.md"}, "c1")

        result = normalizer.normalize(raw, provider="gemini")

        assert result.text == ""


# ---------------------------------------------------------------------------
# Tests: Gemini mixed response (text + tool calls)
# ---------------------------------------------------------------------------

class TestGeminiMixedResponse:
    def test_text_and_tool_calls_both_populated(self):
        normalizer = ResponseNormalizer()
        raw = _gemini_mixed_response("Thinking...", [
            ("read_file", {"filepath": "a.md"}, "c1"),
        ])

        result = normalizer.normalize(raw, provider="gemini")

        assert result.text == "Thinking..."
        assert len(result.tool_calls) == 1
        assert result.has_tool_calls is True


# ---------------------------------------------------------------------------
# Tests: Anthropic text response
# ---------------------------------------------------------------------------

class TestAnthropicTextResponse:
    def test_text_populated(self):
        normalizer = ResponseNormalizer()
        raw = _anthropic_response([_anthropic_text_block("Hello from Claude!")])

        result = normalizer.normalize(raw, provider="anthropic")

        assert result.text == "Hello from Claude!"

    def test_has_tool_calls_false(self):
        normalizer = ResponseNormalizer()
        raw = _anthropic_response([_anthropic_text_block("Hi!")])

        result = normalizer.normalize(raw, provider="anthropic")

        assert result.has_tool_calls is False

    def test_usage_populated(self):
        normalizer = ResponseNormalizer()
        raw = _anthropic_response(
            [_anthropic_text_block("Hi!")], input_tokens=25, output_tokens=10
        )

        result = normalizer.normalize(raw, provider="anthropic")

        assert result.usage["input"] == 25
        assert result.usage["output"] == 10
        assert result.usage["total"] == 35


# ---------------------------------------------------------------------------
# Tests: Anthropic tool use response
# ---------------------------------------------------------------------------

class TestAnthropicToolUseResponse:
    def test_has_tool_calls_true(self):
        normalizer = ResponseNormalizer()
        raw = _anthropic_response([
            _anthropic_tool_use_block("read_file", {"filepath": "x.md"}, "tu_1")
        ])

        result = normalizer.normalize(raw, provider="anthropic")

        assert result.has_tool_calls is True

    def test_tool_calls_populated(self):
        normalizer = ResponseNormalizer()
        raw = _anthropic_response([
            _anthropic_tool_use_block("read_file", {"filepath": "x.md"}, "tu_1")
        ])

        result = normalizer.normalize(raw, provider="anthropic")

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"filepath": "x.md"}
        assert result.tool_calls[0].id == "tu_1"

    def test_multiple_tool_use_blocks(self):
        normalizer = ResponseNormalizer()
        raw = _anthropic_response([
            _anthropic_tool_use_block("read_file", {"filepath": "a.md"}, "tu_a"),
            _anthropic_tool_use_block("read_file", {"filepath": "b.md"}, "tu_b"),
        ])

        result = normalizer.normalize(raw, provider="anthropic")

        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].id == "tu_a"
        assert result.tool_calls[1].id == "tu_b"

    def test_text_empty_for_tool_only_response(self):
        normalizer = ResponseNormalizer()
        raw = _anthropic_response([
            _anthropic_tool_use_block("read_file", {"filepath": "x.md"}, "tu_1")
        ])

        result = normalizer.normalize(raw, provider="anthropic")

        assert result.text == ""


# ---------------------------------------------------------------------------
# Tests: Anthropic mixed response (text + tool use)
# ---------------------------------------------------------------------------

class TestAnthropicMixedResponse:
    def test_text_and_tool_calls_both_populated(self):
        normalizer = ResponseNormalizer()
        raw = _anthropic_response([
            _anthropic_text_block("Let me look that up."),
            _anthropic_tool_use_block("read_file", {"filepath": "a.md"}, "tu_1"),
        ])

        result = normalizer.normalize(raw, provider="anthropic")

        assert result.text == "Let me look that up."
        assert len(result.tool_calls) == 1
        assert result.has_tool_calls is True


# ---------------------------------------------------------------------------
# Tests: Unknown provider
# ---------------------------------------------------------------------------

class TestUnknownProvider:
    def test_raises_value_error(self):
        normalizer = ResponseNormalizer()

        with pytest.raises(ValueError, match="Unknown provider"):
            normalizer.normalize(MagicMock(), provider="openai")

    def test_normalize_chunk_raises_for_unknown(self):
        normalizer = ResponseNormalizer()

        with pytest.raises(ValueError, match="Unknown provider"):
            normalizer.normalize_chunk(MagicMock(), provider="openai")


# ---------------------------------------------------------------------------
# Tests: Streaming chunk normalization
# ---------------------------------------------------------------------------

class TestGeminiStreamingChunk:
    def test_returns_text_delta(self):
        from google.genai import types

        chunk = MagicMock()
        chunk.candidates = [
            MagicMock(content=types.Content(role="model", parts=[types.Part(text="world")]))
        ]

        normalizer = ResponseNormalizer()
        result = normalizer.normalize_chunk(chunk, provider="gemini")

        assert result == "world"

    def test_empty_chunk_returns_empty_string(self):
        chunk = MagicMock()
        chunk.candidates = []

        normalizer = ResponseNormalizer()
        result = normalizer.normalize_chunk(chunk, provider="gemini")

        assert result == ""


class TestAnthropicStreamingChunk:
    def test_returns_text_delta(self):
        chunk = MagicMock()
        chunk.type = "content_block_delta"
        chunk.delta = MagicMock(type="text_delta", text="Hello")

        normalizer = ResponseNormalizer()
        result = normalizer.normalize_chunk(chunk, provider="anthropic")

        assert result == "Hello"

    def test_non_text_delta_returns_empty(self):
        chunk = MagicMock()
        chunk.type = "message_start"
        # No delta attribute matching text_delta

        normalizer = ResponseNormalizer()
        result = normalizer.normalize_chunk(chunk, provider="anthropic")

        assert result == ""


# ---------------------------------------------------------------------------
# Tests: NormalizedResponse dataclass
# ---------------------------------------------------------------------------

class TestNormalizedResponseDataclass:
    def test_default_values(self):
        resp = NormalizedResponse(text="hello")

        assert resp.text == "hello"
        assert resp.has_tool_calls is False
        assert resp.tool_calls == []
        assert resp.usage == {}
        assert resp.raw is None

    def test_with_tool_calls(self):
        tc = ToolCall(id="c1", name="read_file", arguments={"filepath": "x.md"})
        resp = NormalizedResponse(
            text="",
            has_tool_calls=True,
            tool_calls=[tc],
            usage={"input": 10, "output": 5, "total": 15},
        )

        assert resp.has_tool_calls is True
        assert resp.tool_calls[0].name == "read_file"


# ---------------------------------------------------------------------------
# Tests: ToolCall dataclass
# ---------------------------------------------------------------------------

class TestToolCallDataclass:
    def test_fields(self):
        tc = ToolCall(id="c1", name="search", arguments={"query": "test"})

        assert tc.id == "c1"
        assert tc.name == "search"
        assert tc.arguments == {"query": "test"}
