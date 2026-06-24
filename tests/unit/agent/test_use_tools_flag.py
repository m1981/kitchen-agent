"""
tests/unit/agent/test_use_tools_flag.py
========================================
Tests for the use_tools flag in TurnOrchestrator.

Bug: When use_tools=False, the orchestrator still executed tools if the
LLM returned tool calls (e.g. Anthropic hallucinating tools without schemas).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from google.genai import types as genai_types

from src.agent.context_assembler import (
    AssembledContext,
    ContextAssembler,
    ContextBudget,
    ContextSlot,
)
from src.agent.tool_executor import ToolCall, ToolExecutor, ToolResult
from src.agent.turn_orchestrator import TurnInput, TurnOrchestrator
from src.providers.normalizer import ResponseNormalizer


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
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
    def __init__(self):
        self.executed = []
    def get_handler(self, name):
        def handler(**kwargs):
            self.executed.append(name)
            return {"result": "ok"}
        return handler


def _gemini_text_response(text: str) -> MagicMock:
    part = genai_types.Part(text=text)
    mock = MagicMock()
    mock.candidates = [
        MagicMock(content=genai_types.Content(role="model", parts=[part]))
    ]
    mock.usage_metadata = MagicMock(
        prompt_token_count=10, candidates_token_count=5, total_token_count=15,
    )
    return mock


def _gemini_tool_call_response(tool_calls: list[ToolCall]) -> MagicMock:
    parts = []
    for tc in tool_calls:
        parts.append(genai_types.Part(
            function_call=genai_types.FunctionCall(
                name=tc.name, args=tc.arguments, id=tc.id,
            )
        ))
    mock = MagicMock()
    mock.candidates = [
        MagicMock(content=genai_types.Content(role="model", parts=parts))
    ]
    mock.usage_metadata = MagicMock(
        prompt_token_count=20, candidates_token_count=8, total_token_count=28,
    )
    return mock


def _make_orchestrator(
    responses: list,
    use_tools: bool = True,
    registry: FakeRegistry | None = None,
) -> tuple[TurnOrchestrator, FakeRegistry]:
    call_count = {"n": 0}
    if registry is None:
        registry = FakeRegistry()

    def complete(context, *args):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    provider = MagicMock()
    provider.complete = complete
    provider.complete_with_tools = complete
    provider._model = "test-model"

    def stream(context):
        for resp in responses:
            yield resp
            yield {"type": "__final_message__", "message": resp}

    provider.stream = stream
    provider.stream_with_tools = stream

    orchestrator = TurnOrchestrator(
        context_assembler=ContextAssembler(
            token_budget=ContextBudget(total=10_000),
            token_counter=FakeTokenCounter(),
            prompt_manager=FakePromptManager(),
        ),
        tool_executor=ToolExecutor(registry=registry),
        provider=provider,
        response_normalizer=ResponseNormalizer(),
    )

    return orchestrator, registry


def _make_session() -> dict:
    return {"messages": []}


# ═══════════════════════════════════════════════════════════════════════
# BUG: use_tools=False but LLM returns tool calls
# ═══════════════════════════════════════════════════════════════════════

class TestUseToolsFalseRun:
    """
    When use_tools=False, orchestrator must NOT execute tools
    even if the LLM returns tool calls.
    """

    def test_run_skips_tool_execution(self):
        """use_tools=False → tools must not be executed."""
        tool_call = ToolCall(id="c1", name="read_file", arguments={"filepath": "/x"})
        text_resp = _gemini_text_response("Here is my answer.")

        orchestrator, registry = _make_orchestrator(
            responses=[_gemini_tool_call_response([tool_call]), text_resp],
            use_tools=True,  # need tools enabled for the fake to work
        )

        # Now run with use_tools=False
        # The LLM returns tool calls, but orchestrator should skip them
        tool_call_resp = _gemini_tool_call_response([tool_call])

        provider = MagicMock()
        provider.complete = MagicMock(return_value=tool_call_resp)
        provider.complete_with_tools = MagicMock(return_value=text_resp)
        provider._model = "test-model"

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
        )

        output = orchestrator.run(
            session=_make_session(),
            turn_input=TurnInput(user_message="Hello", use_tools=False),
        )

        # Tools must NOT have been executed
        assert registry.executed == [], \
            f"Tools were executed when use_tools=False: {registry.executed}"
        assert output.tool_calls_made == []

    def test_run_still_returns_response(self):
        """use_tools=False with tool calls → must return empty or partial text."""
        tool_call = ToolCall(id="c1", name="read_file", arguments={"filepath": "/x"})
        tool_resp = _gemini_tool_call_response([tool_call])

        provider = MagicMock()
        provider.complete = MagicMock(return_value=tool_resp)
        provider._model = "test-model"

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

        # Must not raise
        output = orchestrator.run(
            session=_make_session(),
            turn_input=TurnInput(user_message="Hello", use_tools=False),
        )

        # Response should be empty (tool call only, no text)
        assert output.tool_calls_made == []


class TestUseToolsFalseStream:
    """
    When use_tools=False, stream must NOT execute tools.
    """

    def test_stream_skips_tool_execution(self):
        """use_tools=False → stream must not execute tools."""
        tool_call = ToolCall(id="c1", name="read_file", arguments={"filepath": "/x"})
        tool_resp = _gemini_tool_call_response([tool_call])

        registry = FakeRegistry()

        provider = MagicMock()
        provider._model = "test-model"

        def stream(context):
            yield tool_resp
            yield {"type": "__final_message__", "message": tool_resp}

        provider.stream = stream

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
        )

        events = list(orchestrator.stream(
            session=_make_session(),
            turn_input=TurnInput(user_message="Hello", use_tools=False),
        ))

        tool_call_events = [e for e in events if e.get("type") == "tool_call"]
        assert tool_call_events == [], \
            f"Tool call events emitted when use_tools=False: {tool_call_events}"
        assert registry.executed == []

    def test_use_tools_true_still_executes(self):
        """Sanity: use_tools=True → tools ARE executed."""
        tool_call = ToolCall(id="c1", name="read_file", arguments={"filepath": "/x"})
        tool_resp = _gemini_tool_call_response([tool_call])
        text_resp = _gemini_text_response("Done.")

        registry = FakeRegistry()

        provider = MagicMock()
        provider._model = "test-model"

        call_count = {"n": 0}

        def stream(context):
            call_count["n"] += 1
            if call_count["n"] == 1:
                yield tool_resp
                yield {"type": "__final_message__", "message": tool_resp}
            else:
                yield text_resp
                yield {"type": "__final_message__", "message": text_resp}

        def stream_with_tools(context, tool_calls, tool_results):
            yield text_resp
            yield {"type": "__final_message__", "message": text_resp}

        provider.stream = stream
        provider.stream_with_tools = stream_with_tools

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
        )

        events = list(orchestrator.stream(
            session=_make_session(),
            turn_input=TurnInput(user_message="Hello", use_tools=True),
        ))

        tool_call_events = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_call_events) == 1
        assert "read_file" in registry.executed
