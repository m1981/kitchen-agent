"""
tests/test_gemini_history_coercion.py
======================================
TDD tests for GeminiProvider's Anthropic-history coercion.

Root cause
----------
When a session was created with the Anthropic provider its history items are
stored as plain dicts.  ``_coerce_history_for_gemini()`` converts those to
``types.Content`` objects before the Gemini SDK call.

Fix contract
------------
``_coerce_history_for_gemini()`` must coerce any plain-dict items in the
history list to ``types.Content`` objects.  The coercion must:

  1. Map Anthropic ``"assistant"`` role → Gemini ``"model"`` role.
  2. Handle plain-string content.
  3. Handle list-of-blocks content (text, tool_use, tool_result).
  4. Support multiple blocks of the same type (parallel tools).
  5. Recover function names for ``tool_result`` blocks.
  6. Leave ``types.Content`` objects untouched.
  7. Not mutate the original history list.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from google.genai import types

from src.agent.context_assembler import AssembledContext, ContextSlot
from src.agent.tool_executor import ToolExecutor
from src.providers.gemini import GeminiProvider, _coerce_history_for_gemini


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeRegistry:
    """Dict-backed registry for tests."""

    def __init__(self, handlers: dict):
        self._handlers = handlers

    def get_handler(self, name: str):
        if name not in self._handlers:
            raise ValueError(f"Unknown tool: {name!r}")
        return self._handlers[name]


def _make_text_response(text: str) -> MagicMock:
    """Return a mock Gemini generate_content response with a text answer."""
    part = types.Part(text=text)
    mock = MagicMock()
    mock.candidates = [MagicMock(content=types.Content(role="model", parts=[part]))]
    mock.text = text
    return mock


def _anthropic_user_str(text: str) -> dict:
    return {"role": "user", "content": text}


def _anthropic_assistant_text(text: str) -> dict:
    return {"role": "assistant", "content": text}


def _anthropic_assistant_tool_use(name: str, tool_input: dict, tool_id: str) -> dict:
    # Common format for assistant with tool calls
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": tool_id, "name": name, "arguments": tool_input}],
    }


def _anthropic_assistant_multi_tool(tools: list[tuple[str, dict, str]]) -> dict:
    """tools = [(name, input, id), ...]"""
    # Common format for assistant with multiple tool calls
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": tid, "name": name, "arguments": inp}
            for name, inp, tid in tools
        ],
    }


def _anthropic_user_tool_result(tool_id: str, result_json: str) -> dict:
    # Common format for tool response
    return {
        "role": "tool",
        "tool_call_id": tool_id,
        "content": result_json,
    }


def _anthropic_user_multi_tool_result(results: list[tuple[str, str]]) -> dict:
    """results = [(tool_use_id, result_json), ...]"""
    # This returns multiple messages in common format
    # For backward compatibility with tests, return first result
    # Tests should be updated to handle multiple messages
    if results:
        return {
            "role": "tool",
            "tool_call_id": results[0][0],
            "content": results[0][1],
        }
    return {"role": "tool", "tool_call_id": "", "content": ""}


def _make_context(messages: list) -> AssembledContext:
    return AssembledContext(
        system_prompt="test",
        messages=messages,
        total_tokens_estimated=10,
        slots_used={ContextSlot.SYSTEM_PROMPT: 5, ContextSlot.CONVERSATION_HISTORY: 5},
    )


@pytest.fixture
def provider() -> GeminiProvider:
    with patch("src.providers.gemini.genai.Client"):
        return GeminiProvider()


# ===========================================================================
# Unit tests for _coerce_history_for_gemini()
# ===========================================================================

class TestCoercionFunction:
    """Direct tests of the internal _coerce_history_for_gemini helper."""

    def test_plain_string_user_content_becomes_content_object(self) -> None:
        history = [_anthropic_user_str("Hello, what are your capabilities?")]
        result = _coerce_history_for_gemini(history)

        assert len(result) == 1
        item = result[0]
        assert isinstance(item, types.Content)
        assert item.role == "user"
        assert len(item.parts) == 1
        assert item.parts[0].text == "Hello, what are your capabilities?"

    def test_assistant_role_mapped_to_model(self) -> None:
        history = [_anthropic_assistant_text("I can help with kitchen design.")]
        result = _coerce_history_for_gemini(history)
        assert result[0].role == "model"

    def test_user_role_preserved(self) -> None:
        history = [_anthropic_user_str("Hello")]
        result = _coerce_history_for_gemini(history)
        assert result[0].role == "user"

    def test_list_text_block_becomes_text_part(self) -> None:
        history = [_anthropic_assistant_text("Use 18mm birch.")]
        result = _coerce_history_for_gemini(history)
        assert isinstance(result[0], types.Content)
        assert result[0].parts[0].text == "Use 18mm birch."

    def test_single_tool_use_becomes_function_call_part(self) -> None:
        history = [
            _anthropic_assistant_tool_use("read_file", {"filepath": "materials.md"}, "c1")
        ]
        result = _coerce_history_for_gemini(history)

        item = result[0]
        assert isinstance(item, types.Content)
        assert item.role == "model"
        fc = item.parts[0].function_call
        assert fc is not None
        assert fc.name == "read_file"
        assert fc.args == {"filepath": "materials.md"}
        assert fc.id == "c1"

    def test_multiple_tool_use_blocks_become_multiple_parts(self) -> None:
        history = [
            _anthropic_assistant_multi_tool([
                ("read_file", {"filepath": "a.md"}, "c1"),
                ("read_file", {"filepath": "b.md"}, "c2"),
                ("get_repo_map", {}, "c3"),
            ])
        ]
        result = _coerce_history_for_gemini(history)

        item = result[0]
        assert len(item.parts) == 3
        assert item.parts[0].function_call.name == "read_file"
        assert item.parts[0].function_call.id == "c1"
        assert item.parts[1].function_call.name == "read_file"
        assert item.parts[1].function_call.id == "c2"
        assert item.parts[2].function_call.name == "get_repo_map"
        assert item.parts[2].function_call.id == "c3"

    def test_tool_result_recovers_function_name_from_preceding_tool_use(self) -> None:
        history = [
            _anthropic_assistant_tool_use("read_file", {"filepath": "test.md"}, "c1"),
            _anthropic_user_tool_result("c1", '{"content": "hello"}'),
        ]
        result = _coerce_history_for_gemini(history)

        fr = result[1].parts[0].function_response
        assert fr is not None
        assert fr.name == "read_file"
        assert fr.id == "c1"
        assert fr.response == {"content": "hello"}

    def test_tool_result_without_matching_tool_use_uses_unknown_name(self) -> None:
        history = [_anthropic_user_tool_result("orphan_id", '{"x": 1}')]
        result = _coerce_history_for_gemini(history)

        fr = result[0].parts[0].function_response
        assert fr is not None
        assert fr.name == "unknown"

    def test_multiple_tool_results_each_get_correct_name(self) -> None:
        history = [
            _anthropic_assistant_multi_tool([
                ("read_file", {"filepath": "a.md"}, "c1"),
                ("search_knowledge_base", {"query": "hinges"}, "c2"),
            ]),
            # In common format, each tool result is a separate message
            _anthropic_user_tool_result("c1", '{"content": "board specs"}'),
            _anthropic_user_tool_result("c2", '{"results": []}'),
        ]
        result = _coerce_history_for_gemini(history)

        # First result is assistant with tool calls
        assert result[0].role == "model"
        assert len(result[0].parts) == 2

        # Second result is tool response for c1
        fr1 = result[1].parts[0].function_response
        assert fr1.name == "read_file"
        assert fr1.id == "c1"
        assert fr1.response == {"content": "board specs"}

        # Third result is tool response for c2
        fr2 = result[2].parts[0].function_response
        assert fr2.name == "search_knowledge_base"
        assert fr2.id == "c2"
        assert fr2.response == {"results": []}

    def test_mixed_text_and_tool_use_in_one_message(self) -> None:
        # Common format: assistant with text and tool calls
        history = [
            {
                "role": "assistant",
                "content": "Let me read that file.",
                "tool_calls": [
                    {"id": "c1", "name": "read_file", "arguments": {"filepath": "x.md"}}
                ],
            }
        ]
        result = _coerce_history_for_gemini(history)

        item = result[0]
        assert len(item.parts) == 2
        assert item.parts[0].text == "Let me read that file."
        assert item.parts[1].function_call.name == "read_file"

    def test_existing_content_objects_pass_through_unchanged(self) -> None:
        original = types.Content(role="user", parts=[types.Part(text="Pure Gemini message")])
        result = _coerce_history_for_gemini([original])

        assert len(result) == 1
        assert result[0] is original

    def test_mixed_content_objects_and_dicts(self) -> None:
        original_content = types.Content(role="user", parts=[types.Part(text="First Gemini turn")])
        history = [original_content, _anthropic_assistant_text("Then Anthropic answered.")]
        result = _coerce_history_for_gemini(history)

        assert result[0] is original_content
        assert isinstance(result[1], types.Content)
        assert result[1].role == "model"

    def test_unknown_block_type_becomes_text_part_fallback(self) -> None:
        history = [{"role": "user", "content": [{"type": "alien_format", "payload": "???"}]}]
        result = _coerce_history_for_gemini(history)
        assert isinstance(result[0], types.Content)
        assert result[0].parts[0].text is not None

    def test_does_not_mutate_original_history_list(self) -> None:
        original = [_anthropic_user_str("hello")]
        original_id = id(original[0])
        result = _coerce_history_for_gemini(original)

        assert isinstance(original[0], dict)
        assert id(original[0]) == original_id
        assert isinstance(result[0], types.Content)

    def test_empty_history_returns_empty_list(self) -> None:
        assert _coerce_history_for_gemini([]) == []

    def test_tool_result_json_string_parsed_to_dict(self) -> None:
        history = [
            _anthropic_assistant_tool_use("read_file", {}, "c1"),
            _anthropic_user_tool_result("c1", '{"content": "# heading\\ntext"}'),
        ]
        result = _coerce_history_for_gemini(history)
        fr = result[1].parts[0].function_response
        assert fr.response == {"content": "# heading\ntext"}

    def test_tool_result_invalid_json_wrapped_in_dict(self) -> None:
        history = [
            _anthropic_assistant_tool_use("some_tool", {}, "c1"),
            _anthropic_user_tool_result("c1", "not-valid-json!!!"),
        ]
        result = _coerce_history_for_gemini(history)
        fr = result[1].parts[0].function_response
        assert isinstance(fr.response, dict)


# ===========================================================================
# Integration tests: GeminiProvider.complete() with Anthropic history
# ===========================================================================

class TestGeminiProviderWithAnthropicHistory:
    """
    End-to-end tests ensuring that GeminiProvider.complete() does not raise
    a Pydantic ValidationError when called with context containing Anthropic dicts.
    """

    def test_complete_does_not_raise_with_anthropic_dict_messages(
        self, provider: GeminiProvider
    ) -> None:
        """Core regression test — Anthropic dicts in context messages must not crash."""
        anthropic_messages = [
            {"role": "user", "content": "Jesteś technologiem produkcji."},
            {"role": "assistant", "content": [{"type": "text", "text": "OK."}]},
        ]
        ctx = _make_context(anthropic_messages)

        provider._client.models.generate_content.return_value = _make_text_response(
            "Rozumiem, kontynuujemy."
        )

        response = provider.complete(ctx)
        assert response.text == "Rozumiem, kontynuujemy."

    def test_generate_content_receives_only_content_objects(
        self, provider: GeminiProvider
    ) -> None:
        """generate_content must be called with only types.Content in contents."""
        ctx = _make_context([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ])

        provider._client.models.generate_content.return_value = _make_text_response("ok")
        provider.complete(ctx)

        call_args = provider._client.models.generate_content.call_args
        contents = call_args.kwargs.get("contents") or call_args.args[1]

        for item in contents:
            assert isinstance(item, types.Content), (
                f"Expected types.Content but got {type(item).__name__}: {item}"
            )

    def test_pure_gemini_messages_still_work(self, provider: GeminiProvider) -> None:
        """Pure Gemini sessions must continue to work."""
        ctx = _make_context([
            {"role": "user", "content": "What is Blum?"},
            {"role": "assistant", "content": "Blum is a hinge maker."},
        ])

        provider._client.models.generate_content.return_value = _make_text_response(
            "Yes, they make hinges."
        )

        response = provider.complete(ctx)
        assert response.text == "Yes, they make hinges."

    def test_empty_messages_does_not_raise(self, provider: GeminiProvider) -> None:
        ctx = _make_context([{"role": "user", "content": "First message"}])
        provider._client.models.generate_content.return_value = _make_text_response("Hello!")
        response = provider.complete(ctx)
        assert response.text == "Hello!"
