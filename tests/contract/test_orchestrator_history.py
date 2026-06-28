"""
tests/contract/test_orchestrator_history.py
============================================
Contract B8: Orchestrator ↔ History Format

Rule: Use REAL TurnOrchestrator, REAL serializers (dehydrate_history, hydrate_history).
Mock only the LLM API.

This test verifies that:
1. TurnOutput.updated_api_history survives dehydrate → hydrate roundtrip
2. Tool call/response pairs in history are properly serialized
3. History format matches what SessionRepository expects
"""
from __future__ import annotations

import json
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
from src.serializers import dehydrate_history, hydrate_history


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
    def __init__(self, handlers=None):
        self._handlers = handlers or {
            "read_file": lambda filepath: f"content of {filepath}",
        }
    def get_handler(self, name):
        if name not in self._handlers:
            raise ValueError(f"Unknown tool: {name!r}")
        return self._handlers[name]


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


def _make_orchestrator(responses: list) -> TurnOrchestrator:
    """Orchestrator with sequence of responses."""
    call_count = {"n": 0}

    def complete(context, *args):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    provider = MagicMock()
    provider.complete = complete
    provider.complete_with_tools = complete
    provider._model = "test-model"

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


# ═══════════════════════════════════════════════════════════════════════
# B8 CONTRACT: History roundtrip (via ChatService._build_api_history)
# ═══════════════════════════════════════════════════════════════════════

class TestHistoryRoundtripContract:
    """
    Contract: ChatService._build_api_history() produces history that
    survives dehydrate_history → hydrate_history roundtrip.

    History building moved from TurnOrchestrator to ChatService.
    """

    @staticmethod
    def _build_history(existing, turn_input, output):
        """Call ChatService._build_api_history without a real service."""
        from src.chat_service import ChatService
        # Use the static method directly
        return ChatService._build_api_history(None, existing, turn_input, output)

    def test_text_turn_survives_roundtrip(self):
        """Simple text turn → dehydrate → hydrate → same structure."""
        orchestrator = _make_orchestrator([_gemini_text_response("Hello!")])

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Hi"),
        )

        history = self._build_history([], TurnInput(user_message="Hi"), output)

        # Serialize
        json_str = dehydrate_history(history, turn_ids=None)

        # Deserialize
        restored = hydrate_history(json_str)

        # Verify structure
        assert len(restored) == len(history)

        # User message preserved
        user_msgs = [m for m in restored if m.get("role") == "user"]
        assert len(user_msgs) >= 1
        assert user_msgs[0]["content"] == "Hi"

        # Assistant message preserved
        asst_msgs = [m for m in restored if m.get("role") == "assistant"]
        assert len(asst_msgs) >= 1
        assert asst_msgs[-1]["content"] == "Hello!"

    def test_tool_turn_survives_roundtrip(self):
        """Tool call + response + final answer → roundtrip."""
        tool_call = ToolCall(id="c1", name="read_file", arguments={"filepath": "/x.md"})
        orchestrator = _make_orchestrator([
            _gemini_tool_call_response([tool_call]),
            _gemini_text_response("File contents."),
        ])

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Read file"),
        )

        history = self._build_history([], TurnInput(user_message="Read file"), output)

        # Serialize
        json_str = dehydrate_history(history, turn_ids=None)

        # Deserialize
        restored = hydrate_history(json_str)

        # Verify structure
        assert len(restored) == len(history)

        # Must have user, assistant (tool call), tool, assistant (text)
        roles = [m.get("role") for m in restored]
        assert "user" in roles
        assert "tool" in roles

    def test_multi_turn_survives_roundtrip(self):
        """Multiple turns in history → roundtrip preserves all."""
        existing = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ]

        orchestrator = _make_orchestrator([_gemini_text_response("New answer!")])

        output = orchestrator.run(
            session={"messages": existing},
            turn_input=TurnInput(user_message="New question"),
        )

        history = self._build_history(existing, TurnInput(user_message="New question"), output)

        # Serialize
        json_str = dehydrate_history(history, turn_ids=None)

        # Deserialize
        restored = hydrate_history(json_str)

        # Must have all messages (2 existing + user + assistant)
        assert len(restored) >= 4

    def test_roundtrip_preserves_tool_call_arguments(self):
        """Tool call arguments must survive roundtrip (important for re-sending)."""
        tool_call = ToolCall(
            id="c1", name="read_file", arguments={"filepath": "/important.md"}
        )
        orchestrator = _make_orchestrator([
            _gemini_tool_call_response([tool_call]),
            _gemini_text_response("Done."),
        ])

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Read"),
        )

        history = self._build_history([], TurnInput(user_message="Read"), output)

        json_str = dehydrate_history(history, turn_ids=None)
        restored = hydrate_history(json_str)

        # Find the tool call in restored history
        tool_call_msgs = [
            m for m in restored
            if m.get("role") == "assistant" and m.get("tool_calls")
        ]
        assert len(tool_call_msgs) >= 1
        tc = tool_call_msgs[0]["tool_calls"][0]
        assert tc["name"] == "read_file"
        assert tc["arguments"]["filepath"] == "/important.md"
