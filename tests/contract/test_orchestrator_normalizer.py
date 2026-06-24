"""
tests/unit/agent/test_stream_final_message.py
===============================================
Tests for the streaming final message handling in TurnOrchestrator.

Bug: After the streaming loop, the orchestrator calls
``normalizer.normalize(chunk, provider_name)`` where ``chunk`` is the
LAST event from the provider's stream.  But different providers yield
different event types as their last chunk:

  - Gemini:  Full response object (works by coincidence)
  - Mimo:    Streaming delta with choices[0].delta (fails silently)
  - Anthropic: ParsedMessageStopEvent (crashes — no .content)

Fix: Providers yield a ``{"type": "__final_message__", "message": ...}``
event after all stream events.  The orchestrator detects this and uses
it for tool call detection instead of normalizing the last raw chunk.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from typing import Iterator, Any

from google.genai import types

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gemini_text_response(text: str) -> MagicMock:
    """Build a mock Gemini response with a single text part."""
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


def _gemini_tool_call_response(tool_calls: list[ToolCall]) -> MagicMock:
    """Build a mock Gemini response with function_call parts."""
    parts = []
    for tc in tool_calls:
        parts.append(
            types.Part(
                function_call=types.FunctionCall(
                    name=tc.name, args=tc.arguments, id=tc.id,
                )
            )
        )
    mock = MagicMock()
    mock.candidates = [
        MagicMock(content=types.Content(role="model", parts=parts))
    ]
    mock.usage_metadata = MagicMock(
        prompt_token_count=20,
        candidates_token_count=8,
        total_token_count=28,
    )
    return mock


# ---------------------------------------------------------------------------
# Fake provider with streaming support
# ---------------------------------------------------------------------------

class FakeStreamingProvider:
    """
    Fake LLM provider that supports both complete() and stream().
    Yields chunks then a final_message event.
    """

    def __init__(
        self,
        text: str = "Default response.",
        stream_tool_calls: list[ToolCall] | None = None,
        stream_chunks: list[str] | None = None,
    ) -> None:
        self._text = text
        self._stream_tool_calls = stream_tool_calls or []
        self._stream_chunks = stream_chunks or [text]
        self.complete_call_count = 0
        self.stream_call_count = 0

    def complete(self, context: AssembledContext) -> MagicMock:
        self.complete_call_count += 1
        if self._stream_tool_calls:
            return _gemini_tool_call_response(self._stream_tool_calls)
        return _gemini_text_response(self._text)

    def complete_with_tools(
        self, context: AssembledContext,
        tool_calls: list[ToolCall], tool_results: list[ToolResult],
    ) -> MagicMock:
        return self.complete(context)

    def stream(self, context: AssembledContext) -> Iterator[Any]:
        """Yield Gemini-style chunks then a __final_message__ event."""
        self.stream_call_count += 1

        # Yield Gemini-style text chunks (so normalizer can extract text)
        for chunk_text in self._stream_chunks:
            yield _gemini_text_response(chunk_text)

        # Yield the final message for tool call detection
        if self._stream_tool_calls:
            final = _gemini_tool_call_response(self._stream_tool_calls)
        else:
            final = _gemini_text_response("".join(self._stream_chunks))

        yield {"type": "__final_message__", "message": final}

    def stream_with_tools(
        self, context: AssembledContext,
        tool_calls: list[ToolCall], tool_results: list[ToolResult],
    ) -> Iterator[Any]:
        """Continue streaming after tool execution."""
        yield _gemini_text_response(self._text)
        yield {"type": "__final_message__", "message": _gemini_text_response(self._text)}


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


def make_streaming_orchestrator(
    text: str = "Default response.",
    stream_tool_calls: list[ToolCall] | None = None,
    stream_chunks: list[str] | None = None,
) -> TurnOrchestrator:
    provider = FakeStreamingProvider(
        text=text,
        stream_tool_calls=stream_tool_calls,
        stream_chunks=stream_chunks,
    )
    return TurnOrchestrator(
        context_assembler=ContextAssembler(
            token_budget=ContextBudget(total=10_000),
            token_counter=FakeTokenCounter(),
            prompt_manager=FakePromptManager(),
        ),
        tool_executor=ToolExecutor(registry=FakeRegistry()),
        provider=provider,
        response_normalizer=ResponseNormalizer(),
    )


def make_session(messages: list[dict] | None = None) -> dict:
    return {"messages": messages or []}


# ---------------------------------------------------------------------------
# Tests: streaming text-only response
# ---------------------------------------------------------------------------

class TestStreamingTextResponse:
    def test_stream_yields_text_deltas(self):
        """Streaming should yield text_delta events for each chunk."""
        orchestrator = make_streaming_orchestrator(
            stream_chunks=["Hello ", "world!"],
        )
        events = list(orchestrator.stream(
            session=make_session(),
            turn_input=TurnInput(user_message="Hi"),
        ))

        text_events = [e for e in events if e["type"] == "text_delta"]
        assert len(text_events) == 2
        assert text_events[0]["content"] == "Hello "
        assert text_events[1]["content"] == "world!"

    def test_stream_yields_done_event(self):
        """Streaming should yield a done event at the end."""
        orchestrator = make_streaming_orchestrator(text="Answer.")
        events = list(orchestrator.stream(
            session=make_session(),
            turn_input=TurnInput(user_message="Question"),
        ))

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        assert "provider" in done_events[0]
        assert "model" in done_events[0]


# ---------------------------------------------------------------------------
# Tests: streaming with tool calls
# ---------------------------------------------------------------------------

class TestStreamingToolCalls:
    def test_stream_detects_tool_calls_from_final_message(self):
        """Tool calls must be detected from __final_message__, not from raw last chunk."""
        tool_call = ToolCall(
            id="c1", name="read_file", arguments={"filepath": "/test.md"}
        )
        orchestrator = make_streaming_orchestrator(
            text="After tool.",
            stream_tool_calls=[tool_call],
        )
        events = list(orchestrator.stream(
            session=make_session(),
            turn_input=TurnInput(user_message="Read file"),
        ))

        tool_call_events = [e for e in events if e["type"] == "tool_call"]
        assert len(tool_call_events) == 1
        assert tool_call_events[0]["name"] == "read_file"

    def test_stream_executes_tool_and_continues(self):
        """After tool execution, streaming should continue with tool results."""
        tool_call = ToolCall(
            id="c1", name="read_file", arguments={"filepath": "/test.md"}
        )
        orchestrator = make_streaming_orchestrator(
            text="File contents shown.",
            stream_tool_calls=[tool_call],
        )
        events = list(orchestrator.stream(
            session=make_session(),
            turn_input=TurnInput(user_message="Read file"),
        ))

        tool_result_events = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_result_events) == 1
        assert tool_result_events[0]["name"] == "read_file"

    def test_stream_done_event_includes_tool_calls(self):
        """Done event should list tool calls that were made."""
        tool_call = ToolCall(
            id="c1", name="read_file", arguments={"filepath": "/x.md"}
        )
        orchestrator = make_streaming_orchestrator(
            text="Done.",
            stream_tool_calls=[tool_call],
        )
        events = list(orchestrator.stream(
            session=make_session(),
            turn_input=TurnInput(user_message="Read"),
        ))

        done = [e for e in events if e["type"] == "done"][0]
        assert "read_file" in done["tool_calls_made"]


# ---------------------------------------------------------------------------
# Tests: Anthropic-style last chunk (the actual bug)
# ---------------------------------------------------------------------------

class TestAnthropicStreamingBug:
    """
    The actual bug: Anthropic's last stream event is a ParsedMessageStopEvent
    which has no .content attribute.  The orchestrator must NOT try to
    normalize the last raw chunk — it should use __final_message__ instead.
    """

    def test_last_chunk_not_used_for_normalization(self):
        """
        The orchestrator must NOT pass the last raw chunk to normalizer.normalize().
        It should use the __final_message__ event's message instead.
        """
        # Simulate Anthropic-style stream: text deltas + stop event (no .content)
        provider = FakeStreamingProvider(text="Response.")

        # Override stream to yield a "stop event" as last chunk (like Anthropic)
        original_stream = provider.stream

        def anthropic_like_stream(context):
            yield {"type": "content_block_delta", "delta": {"text": "Response."}}
            # Last event is a stop event with no content attribute
            stop_event = MagicMock()
            stop_event.type = "message_stop"
            del stop_event.content  # Simulate missing .content
            yield stop_event
            # Then the final message
            yield {"type": "__final_message__", "message": _gemini_text_response("Response.")}

        provider.stream = anthropic_like_stream

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

        # Must not crash with AttributeError: 'MagicMock' has no attribute 'content'
        events = list(orchestrator.stream(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello"),
        ))

        text_events = [e for e in events if e["type"] == "text_delta"]
        assert len(text_events) >= 1


class TestMimoStreamingBug:
    """
    Mimo's last stream chunk is a streaming delta (choices[0].delta),
    not a complete message (choices[0].message).  normalize() would
    silently return empty text/tool_calls.
    """

    def test_mimo_style_last_chunk_not_used(self):
        """Orchestrator must use __final_message__ for Mimo streaming too."""
        provider = FakeStreamingProvider(text="Mimo response.")

        def mimo_like_stream(context):
            # Streaming deltas
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="Mimo "))])
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="response."))])
            # Final message event
            yield {"type": "__final_message__", "message": _gemini_text_response("Mimo response.")}

        provider.stream = mimo_like_stream

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

        events = list(orchestrator.stream(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello"),
        ))

        done = [e for e in events if e["type"] == "done"][0]
        assert done["provider"] == "gemini"  # default provider name


# ---------------------------------------------------------------------------
# Tests: recursive streaming tool loop (Fix #4)
# ---------------------------------------------------------------------------

class TestRecursiveStreamingToolLoop:
    """
    stream() must handle multiple tool-call iterations, just like run().

    Before Fix #4: stream() only handled one tool-call iteration.
    After Fix #4: stream() has a while loop matching run() logic.
    """

    def test_stream_handles_sequential_tool_calls(self):
        """LLM calls tool, gets result, calls another tool, then responds."""
        first_tool = ToolCall(id="c1", name="read_file", arguments={"filepath": "/a.md"})
        second_tool = ToolCall(id="c2", name="echo", arguments={"text": "processed"})

        provider = FakeStreamingProvider(text="Final answer.")
        call_count = 0

        def multi_iter_stream(context, *args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"type": "__final_message__", "message": _gemini_tool_call_response([first_tool])}
            elif call_count == 2:
                yield {"type": "__final_message__", "message": _gemini_tool_call_response([second_tool])}
            else:
                yield {"type": "__final_message__", "message": _gemini_text_response("Final answer.")}

        provider.stream = multi_iter_stream
        provider.stream_with_tools = multi_iter_stream  # same generator for both

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
            max_tool_iterations=10,
        )

        events = list(orchestrator.stream(
            session=make_session(),
            turn_input=TurnInput(user_message="Multi-step"),
        ))

        tool_call_events = [e for e in events if e["type"] == "tool_call"]
        tool_result_events = [e for e in events if e["type"] == "tool_result"]
        done_events = [e for e in events if e["type"] == "done"]

        assert len(tool_call_events) == 2
        assert tool_call_events[0]["name"] == "read_file"
        assert tool_call_events[1]["name"] == "echo"
        assert len(tool_result_events) == 2
        assert len(done_events) == 1
        assert done_events[0]["tool_calls_made"] == ["read_file", "echo"]

    def test_stream_max_iterations_enforced(self):
        """Infinite tool loop in streaming must raise MaxToolIterationsError."""
        provider = FakeStreamingProvider(text="loop")
        tool_call = ToolCall(id="c1", name="read_file", arguments={"filepath": "/loop"})

        def infinite_stream(context, *args):
            yield {"type": "__final_message__", "message": _gemini_tool_call_response([tool_call])}

        provider.stream = infinite_stream
        provider.stream_with_tools = infinite_stream  # same for both

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
            max_tool_iterations=3,
        )

        with pytest.raises(MaxToolIterationsError) as exc_info:
            list(orchestrator.stream(
                session=make_session(),
                turn_input=TurnInput(user_message="Loop"),
            ))

        assert exc_info.value.max_iterations == 3

    def test_stream_tool_details_in_done_event(self):
        """Done event must include tool_details for history building."""
        tool_call = ToolCall(id="c1", name="read_file", arguments={"filepath": "/x.md"})
        provider = FakeStreamingProvider(text="Done.")

        call_count = 0

        def two_iter_stream(context, *args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"type": "__final_message__", "message": _gemini_tool_call_response([tool_call])}
            else:
                yield {"type": "__final_message__", "message": _gemini_text_response("Done.")}

        provider.stream = two_iter_stream
        provider.stream_with_tools = two_iter_stream  # same for both

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

        events = list(orchestrator.stream(
            session=make_session(),
            turn_input=TurnInput(user_message="Read"),
        ))

        done = [e for e in events if e["type"] == "done"][0]
        assert "tool_details" in done
        assert len(done["tool_details"]) == 1
        assert done["tool_details"][0].name == "read_file"
