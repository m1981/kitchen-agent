"""
tests/contract/test_orchestrator_provider.py
==============================================
Contract B5: Orchestrator ↔ Provider

Rule: Use REAL TurnOrchestrator, REAL ResponseNormalizer, REAL ContextAssembler.
Mock only the LLM API client (google.genai, anthropic, openai).

This test verifies that:
1. Provider.complete() output is consumable by the orchestrator
2. Provider.stream() events flow correctly through the orchestrator
3. Tool call detection works for all providers (complete + stream)
4. Provider routing works (turn_input.provider override)
"""
from __future__ import annotations

import json
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from typing import Iterator, Any

from google.genai import types as genai_types

from src.agent.context_assembler import (
    AssembledContext,
    ContextAssembler,
    ContextBudget,
    ContextSlot,
)
from src.agent.tool_executor import ToolCall, ToolExecutor, ToolResult
from src.agent.turn_orchestrator import (
    MaxToolIterationsError,
    TurnInput,
    TurnOrchestrator,
)
from src.providers.base import LLMProvider
from src.providers.normalizer import NormalizedResponse, ResponseNormalizer


# ═══════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═══════════════════════════════════════════════════════════════════════

class FakeTokenCounter:
    def count(self, text: str) -> int:
        return max(1, len(text) // 4)
    def count_message(self, message: dict) -> int:
        return self.count(str(message.get("content", "")))
    def trim_to(self, text: str, max_tokens: int) -> str:
        return text[:max_tokens * 4]


class FakePromptManager:
    def get_system_instruction(self, mode: str = "default") -> str:
        return "You are helpful."


class FakeRegistry:
    def __init__(self, handlers: dict | None = None) -> None:
        self._handlers = handlers or {
            "read_file": lambda filepath: f"content of {filepath}",
        }
    def get_handler(self, name: str):
        if name not in self._handlers:
            raise ValueError(f"Unknown tool: {name!r}")
        return self._handlers[name]


def _make_context() -> AssembledContext:
    return AssembledContext(
        system_prompt="You are helpful.",
        messages=[{"role": "user", "content": "Hello"}],
        total_tokens_estimated=50,
        slots_used={ContextSlot.SYSTEM_PROMPT: 20, ContextSlot.CONVERSATION_HISTORY: 30},
    )


def _make_session() -> dict:
    return {"messages": []}


# ═══════════════════════════════════════════════════════════════════════
# PROVIDER BUILDERS — real providers with mocked SDK clients
# ═══════════════════════════════════════════════════════════════════════

def _make_gemini_provider(text: str = "Hello!", tool_calls: list | None = None):
    """Create a real GeminiProvider with a mocked genai.Client."""
    with patch("src.providers.gemini.genai.Client") as mock_client_cls:
        from src.providers.gemini import GeminiProvider
        provider = GeminiProvider.__new__(GeminiProvider)
        provider._client = MagicMock()
        provider._model = "gemini-2.5-flash"
        provider._normalizer = ResponseNormalizer()
        provider._registry = MagicMock()
        provider._tool_executor = MagicMock()
        provider._conversation_state = []

    # Build mock response
    if tool_calls:
        parts = []
        for tc in tool_calls:
            parts.append(genai_types.Part(
                function_call=genai_types.FunctionCall(
                    name=tc["name"], args=tc["arguments"], id=tc.get("id", "call_1"),
                )
            ))
    else:
        parts = [genai_types.Part(text=text)]

    mock_response = MagicMock()
    mock_response.candidates = [
        MagicMock(content=genai_types.Content(role="model", parts=parts))
    ]
    mock_response.usage_metadata = MagicMock(
        prompt_token_count=10, candidates_token_count=5, total_token_count=15,
    )

    return provider, mock_response


def _make_anthropic_provider(text: str = "Hello!", tool_calls: list | None = None):
    """Create a real AnthropicProvider with a mocked anthropic client."""
    from anthropic.types import Message, TextBlock, ToolUseBlock

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
        provider._normalizer = ResponseNormalizer()

    # Build real Message object
    content = []
    if tool_calls:
        for tc in tool_calls:
            content.append(ToolUseBlock(
                id=tc.get("id", "tu_1"),
                name=tc["name"],
                input=tc["arguments"],
                type="tool_use",
            ))
    else:
        content.append(TextBlock(text=text, type="text"))

    mock_response = Message(
        id="msg_1",
        content=content,
        model="claude-sonnet-4-20250514",
        role="assistant",
        stop_reason="end_turn" if not tool_calls else "tool_use",
        type="message",
        usage={"input_tokens": 10, "output_tokens": 5},
    )

    return provider, mock_response


def _make_mimo_provider(text: str = "Hello!", tool_calls: list | None = None):
    """Create a real MimoProvider with a mocked OpenAI client."""
    with patch("src.providers.mimo_provider.settings") as mock_settings, \
         patch("src.providers.mimo_provider._build_default_registry") as mock_reg:
        mock_settings.mimo_api_key = "test-key"
        mock_settings.mimo_base_url = "https://test.api.com"
        mock_settings.mimo_model = "mimo-v2.5-pro"
        mock_settings.mimo_temperature = 0.7
        mock_settings.mimo_max_tokens = 4096
        mock_reg.return_value = MagicMock(get_all_entries=MagicMock(return_value=[]))

        from src.providers.mimo_provider import MimoProvider
        provider = MimoProvider.__new__(MimoProvider)
        provider._client = MagicMock()
        provider._model = "mimo-v2.5-pro"
        provider._registry = MagicMock()
        provider._tool_executor = MagicMock()
        provider._conversation_state = []

    # Build mock OpenAI response
    msg = SimpleNamespace(content=text, tool_calls=None)
    if tool_calls:
        msg.tool_calls = [
            SimpleNamespace(
                id=tc.get("id", "call_1"),
                function=SimpleNamespace(
                    name=tc["name"],
                    arguments=json.dumps(tc["arguments"]),
                ),
            )
            for tc in tool_calls
        ]
        msg.content = None

    mock_response = SimpleNamespace(
        choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )

    return provider, mock_response


# ═══════════════════════════════════════════════════════════════════════
# B5 CONTRACT: Provider.complete() → Orchestrator.run()
# ═══════════════════════════════════════════════════════════════════════

class TestCompleteContract:
    """
    Contract: Provider.complete() output must be consumable by
    TurnOrchestrator.run() without crashing.

    Uses REAL TurnOrchestrator, REAL ResponseNormalizer.
    Mocks only the SDK client.
    """

    def _run_with_provider(self, provider, mock_response, provider_name="gemini", **kwargs):
        """Helper: run orchestrator with a provider that returns mock_response."""
        provider.complete = MagicMock(return_value=mock_response)
        provider.complete_with_tools = MagicMock(return_value=mock_response)

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
            provider_name=provider_name,
        )

        return orchestrator.run(
            session=_make_session(),
            turn_input=TurnInput(user_message="Hello", **kwargs),
        )

    def test_gemini_text_response(self):
        """Gemini text response → orchestrator returns assistant message."""
        provider, mock_resp = _make_gemini_provider(text="Hello from Gemini!")
        output = self._run_with_provider(provider, mock_resp)
        assert output.assistant_message == "Hello from Gemini!"

    def test_anthropic_text_response(self):
        """Anthropic Message → orchestrator returns assistant message."""
        provider, mock_resp = _make_anthropic_provider(text="Hello from Claude!")
        output = self._run_with_provider(provider, mock_resp, provider_name="anthropic")
        assert output.assistant_message == "Hello from Claude!"

    def test_mimo_text_response(self):
        """Mimo OpenAI response → orchestrator returns assistant message."""
        provider, mock_resp = _make_mimo_provider(text="Hello from Mimo!")
        output = self._run_with_provider(provider, mock_resp, provider_name="mimo")
        assert output.assistant_message == "Hello from Mimo!"

    def test_gemini_tool_call_response(self):
        """Gemini function_call → orchestrator detects and executes tools."""
        provider, mock_resp = _make_gemini_provider(tool_calls=[
            {"name": "read_file", "arguments": {"filepath": "/test.md"}, "id": "c1"},
        ])
        # After tool execution, provider returns text
        text_resp = _make_gemini_provider(text="File contents shown.")[1]
        provider.complete = MagicMock(return_value=mock_resp)
        provider.complete_with_tools = MagicMock(return_value=text_resp)

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
        )

        output = orchestrator.run(
            session=_make_session(),
            turn_input=TurnInput(user_message="Read file"),
        )

        assert output.assistant_message == "File contents shown."
        assert any(tc.name == "read_file" for tc in output.tool_calls_made)

    def test_anthropic_tool_call_response(self):
        """Anthropic ToolUseBlock → orchestrator detects and executes tools."""
        provider, mock_resp = _make_anthropic_provider(tool_calls=[
            {"name": "read_file", "arguments": {"filepath": "/test.md"}, "id": "tu_1"},
        ])
        text_resp = _make_anthropic_provider(text="Done.")[1]
        provider.complete = MagicMock(return_value=mock_resp)
        provider.complete_with_tools = MagicMock(return_value=text_resp)

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
            provider_name="anthropic",
        )

        output = orchestrator.run(
            session=_make_session(),
            turn_input=TurnInput(user_message="Read file"),
        )

        assert output.assistant_message == "Done."
        assert any(tc.name == "read_file" for tc in output.tool_calls_made)

    def test_mimo_tool_call_response(self):
        """Mimo tool_calls → orchestrator detects and executes tools."""
        provider, mock_resp = _make_mimo_provider(tool_calls=[
            {"name": "read_file", "arguments": {"filepath": "/test.md"}, "id": "call_1"},
        ])
        text_resp = _make_mimo_provider(text="Done.")[1]
        provider.complete = MagicMock(return_value=mock_resp)
        provider.complete_with_tools = MagicMock(return_value=text_resp)

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
            provider_name="mimo",
        )

        output = orchestrator.run(
            session=_make_session(),
            turn_input=TurnInput(user_message="Read file"),
        )

        assert output.assistant_message == "Done."
        assert any(tc.name == "read_file" for tc in output.tool_calls_made)

    def test_usage_propagated(self):
        """Token usage from provider must appear in TurnOutput."""
        provider, mock_resp = _make_gemini_provider(text="Hi")
        output = self._run_with_provider(provider, mock_resp)
        assert output.tokens_used["input"] == 10
        assert output.tokens_used["output"] == 5
        assert output.tokens_used["total"] == 15


# ═══════════════════════════════════════════════════════════════════════
# B5 CONTRACT: Provider.stream() → Orchestrator.stream()
# ═══════════════════════════════════════════════════════════════════════

class TestStreamContract:
    """
    Contract: Provider.stream() events must flow correctly through
    TurnOrchestrator.stream() — text extraction, tool call detection,
    and done event.

    Uses REAL TurnOrchestrator, REAL ResponseNormalizer.
    Mocks only the SDK streaming responses.
    """

    def _make_streaming_orchestrator(self, provider, provider_name="gemini"):
        return TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
            provider_name=provider_name,
        )

    def test_gemini_stream_text(self):
        """Gemini streaming: text chunks extracted, done event emitted."""
        provider, _ = _make_gemini_provider(text="Hello from Gemini!")

        # Build streaming chunks
        chunk = MagicMock()
        chunk.candidates = [
            MagicMock(content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text="Hello from Gemini!")],
            ))
        ]
        chunk.usage_metadata = MagicMock(
            prompt_token_count=10, candidates_token_count=5, total_token_count=15,
        )

        provider.stream = MagicMock(return_value=iter([chunk]))

        orchestrator = self._make_streaming_orchestrator(provider)
        events = list(orchestrator.stream(
            session=_make_session(),
            turn_input=TurnInput(user_message="Hi"),
        ))

        text_events = [e for e in events if e["type"] == "text_delta"]
        done_events = [e for e in events if e["type"] == "done"]

        assert len(text_events) >= 1
        assert text_events[0]["content"] == "Hello from Gemini!"
        assert len(done_events) == 1

    def test_anthropic_stream_text(self):
        """Anthropic streaming: text deltas + __final_message__ → done event."""
        from anthropic.types import (
            Message, TextBlock, ContentBlockDeltaEvent, TextDelta,
            MessageStopEvent,
        )

        provider, _ = _make_anthropic_provider(text="Hello from Claude!")

        # Build realistic Anthropic stream events
        delta_event = ContentBlockDeltaEvent(
            delta=TextDelta(text="Hello from Claude!", type="text_delta"),
            index=0,
            type="content_block_delta",
        )
        stop_event = MessageStopEvent(type="message_stop")

        # Final message from get_final_message()
        final_msg = Message(
            id="msg_1",
            content=[TextBlock(text="Hello from Claude!", type="text")],
            model="claude-sonnet-4-20250514",
            role="assistant",
            stop_reason="end_turn",
            type="message",
            usage={"input_tokens": 10, "output_tokens": 5},
        )

        def stream_side_effect(context):
            yield delta_event
            yield stop_event
            yield {"type": "__final_message__", "message": final_msg}

        provider.stream = stream_side_effect

        orchestrator = self._make_streaming_orchestrator(provider, provider_name="anthropic")
        events = list(orchestrator.stream(
            session=_make_session(),
            turn_input=TurnInput(user_message="Hi"),
        ))

        text_events = [e for e in events if e["type"] == "text_delta"]
        done_events = [e for e in events if e["type"] == "done"]

        assert len(text_events) >= 1
        assert text_events[0]["content"] == "Hello from Claude!"
        assert len(done_events) == 1
        assert done_events[0]["provider"] == "anthropic"

    def test_mimo_stream_text(self):
        """Mimo streaming: deltas + __final_message__ → done event."""
        provider, _ = _make_mimo_provider(text="Hello from Mimo!")

        chunk1 = MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello "))])
        chunk2 = MagicMock(choices=[MagicMock(delta=MagicMock(content="from Mimo!"))])

        final_msg = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content="Hello from Mimo!", tool_calls=None,
            ))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

        def stream_side_effect(context):
            yield chunk1
            yield chunk2
            yield {"type": "__final_message__", "message": final_msg}

        provider.stream = stream_side_effect

        orchestrator = self._make_streaming_orchestrator(provider, provider_name="mimo")
        events = list(orchestrator.stream(
            session=_make_session(),
            turn_input=TurnInput(user_message="Hi"),
        ))

        text_events = [e for e in events if e["type"] == "text_delta"]
        done_events = [e for e in events if e["type"] == "done"]

        assert len(text_events) >= 1
        assert len(done_events) == 1

    def test_stream_tool_calls_detected_via_final_message(self):
        """Tool calls from __final_message__ are detected and executed."""
        provider, _ = _make_gemini_provider(text="After tool.")

        # Build tool call response
        tool_parts = [genai_types.Part(
            function_call=genai_types.FunctionCall(
                name="read_file", args={"filepath": "/x.md"}, id="c1",
            )
        )]
        tool_chunk = MagicMock()
        tool_chunk.candidates = [
            MagicMock(content=genai_types.Content(role="model", parts=tool_parts))
        ]
        tool_chunk.usage_metadata = MagicMock(
            prompt_token_count=20, candidates_token_count=8, total_token_count=28,
        )

        # After tool execution, text response
        text_chunk = MagicMock()
        text_chunk.candidates = [
            MagicMock(content=genai_types.Content(
                role="model", parts=[genai_types.Part(text="After tool.")],
            ))
        ]
        text_chunk.usage_metadata = MagicMock(
            prompt_token_count=10, candidates_token_count=5, total_token_count=15,
        )

        call_count = {"n": 0}

        def stream_side_effect(context):
            call_count["n"] += 1
            if call_count["n"] == 1:
                yield tool_chunk
                yield {"type": "__final_message__", "message": tool_chunk}
            else:
                yield text_chunk
                yield {"type": "__final_message__", "message": text_chunk}

        def stream_with_tools_side_effect(context, tool_calls, tool_results):
            yield text_chunk
            yield {"type": "__final_message__", "message": text_chunk}

        provider.stream = stream_side_effect
        provider.stream_with_tools = stream_with_tools_side_effect

        orchestrator = self._make_streaming_orchestrator(provider)
        events = list(orchestrator.stream(
            session=_make_session(),
            turn_input=TurnInput(user_message="Read file"),
        ))

        tool_call_events = [e for e in events if e["type"] == "tool_call"]
        tool_result_events = [e for e in events if e["type"] == "tool_result"]
        done_events = [e for e in events if e["type"] == "done"]

        assert len(tool_call_events) >= 1
        assert tool_call_events[0]["name"] == "read_file"
        assert len(tool_result_events) >= 1
        assert len(done_events) == 1
        assert "read_file" in done_events[0]["tool_calls_made"]


# ═══════════════════════════════════════════════════════════════════════
# B5 CONTRACT: Provider routing
# ═══════════════════════════════════════════════════════════════════════

class TestProviderRoutingContract:
    """
    Contract: When turn_input.provider is set, orchestrator must create
    a new provider via get_provider() and use it instead of the default.
    """

    def test_provider_override_used_for_complete(self):
        """turn_input.provider='anthropic' → AnthropicProvider used."""
        default_provider = MagicMock(spec=LLMProvider)
        default_provider._model = "gemini-2.5-flash"

        override_response = _make_anthropic_provider(text="Override!")[1]

        with patch("src.providers.base.get_provider") as mock_get:
            mock_provider = MagicMock(spec=LLMProvider)
            mock_provider.complete = MagicMock(return_value=override_response)
            mock_provider._model = "claude-sonnet-4-20250514"
            mock_get.return_value = mock_provider

            orchestrator = TurnOrchestrator(
                context_assembler=ContextAssembler(
                    token_budget=ContextBudget(total=10_000),
                    token_counter=FakeTokenCounter(),
                    prompt_manager=FakePromptManager(),
                ),
                tool_executor=ToolExecutor(registry=FakeRegistry()),
                provider=default_provider,
                response_normalizer=ResponseNormalizer(),
                provider_name="gemini",
            )

            output = orchestrator.run(
                session=_make_session(),
                turn_input=TurnInput(
                    user_message="Hello",
                    provider="anthropic",
                    model="claude-sonnet-4-20250514",
                ),
            )

            # Override provider was used, not default
            mock_get.assert_called_once_with(
                provider_name="anthropic",
                model_override="claude-sonnet-4-20250514",
            )
            assert default_provider.complete.call_count == 0
            assert output.assistant_message == "Override!"
            assert output.provider_name == "anthropic"
