"""
tests/unit/agent/test_token_budget.py
======================================
TDD tests for token budget enforcement in the tool loop.

Feature: F01 — Token Budget in Tool Loop
Design:  docs/f01-token-tool-loop.md

These tests define the expected behavior BEFORE implementation.
They should FAIL until the feature is implemented.

Decision log (from design doc):
  - Truncation strategy: Truncate + warn LLM
  - Where to count: In Orchestrator (not ToolExecutor)
  - Budget source: From ContextBudget (ContextSlot.TOOL_RESULTS)
  - What to truncate: Raw content string
  - Warning message: Append to context (LLM can adapt)
  - Metric tracking: Yes (tool_tokens_used in TurnOutput.context_slots)
"""
import pytest
from unittest.mock import MagicMock

from google.genai import types

from src.agent.context_assembler import (
    AssembledContext,
    ContextAssembler,
    ContextBudget,
    ContextSlot,
)
from src.agent.tool_executor import ToolCall, ToolExecutor, ToolResult
from src.agent.turn_orchestrator import (
    TurnInput,
    TurnOrchestrator,
    TurnOutput,
)
from src.providers.normalizer import NormalizedResponse, ResponseNormalizer


# ---------------------------------------------------------------------------
# Reuse fakes from test_turn_orchestrator
# ---------------------------------------------------------------------------

class FakeTokenCounter:
    """Predictable token counter: 1 token per 4 characters."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)

    def count_message(self, message: dict) -> int:
        content = message.get("content", "")
        return self.count(str(content))

    def trim_to(self, text: str, max_tokens: int) -> str:
        max_chars = max_tokens * 4
        return text[:max_chars]


class FakePromptManager:
    def __init__(self, prompt: str = "You are a helpful assistant.") -> None:
        self._prompt = prompt

    def get_system_instruction(self, mode: str = "default") -> str:
        return self._prompt


class FakeRegistry:
    """Registry with controllable tool handlers."""

    def __init__(self, handlers: dict | None = None) -> None:
        self._handlers = handlers or {
            "search": lambda query, **kw: {"content": f"Results for: {query}" + "x" * 500},
            "read_file": lambda filepath: {"content": f"Content of {filepath}" + "y" * 200},
        }

    def get_handler(self, name: str):
        if name not in self._handlers:
            raise ValueError(f"Unknown tool: {name!r}")
        return self._handlers[name]


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


class FakeCompleter:
    """Controllable LLM provider."""

    def __init__(
        self,
        responses: list[tuple[str, list[ToolCall]]] | None = None,
    ) -> None:
        self._call_count = 0
        self.complete_call_count = 0
        self.last_context: AssembledContext | None = None
        self.all_contexts: list[AssembledContext] = []
        self._responses = responses or [("Default response.", [])]

    def complete(self, context: AssembledContext) -> MagicMock:
        self.complete_call_count += 1
        self.last_context = context
        self.all_contexts.append(context)

        text, tool_calls = self._responses[
            min(self._call_count, len(self._responses) - 1)
        ]
        self._call_count += 1

        if tool_calls:
            return _gemini_tool_call_response(tool_calls)
        return _gemini_text_response(text)

    def complete_with_tools(
        self,
        context: AssembledContext,
        tool_calls: list[ToolCall],
        tool_results: list[ToolResult],
    ) -> MagicMock:
        return self.complete(context)


def _make_large_content(size: int = 10_000) -> str:
    """Generate content of approximate token size (4 chars per token)."""
    return "x" * (size * 4)


# ---------------------------------------------------------------------------
# Tests: Token counting after tool execution
# ---------------------------------------------------------------------------

class TestTokenCountingAfterExecution:
    """
    CHECKPOINT 1: After _execute_tool_calls(), the orchestrator should
    count tokens for each tool result and accumulate them.
    """

    def test_tool_tokens_counted_in_output(self):
        """
        After a tool call, TurnOutput.context_slots should include
        ContextSlot.TOOL_RESULTS with the accumulated token count.
        """
        tool_call = ToolCall(id="c1", name="search", arguments={"query": "hinge"})
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=128_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=FakeCompleter(responses=[
                ("", [tool_call]),
                ("Here are the results.", []),
            ]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=ContextBudget(total=128_000),
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Search for hinges"),
        )

        # TOOL_RESULTS slot should be populated with actual token count
        assert ContextSlot.TOOL_RESULTS in output.context_slots
        assert output.context_slots[ContextSlot.TOOL_RESULTS] > 0

    def test_multiple_tool_calls_tokens_summed(self):
        """
        When the LLM requests multiple tools in one iteration,
        token counts from all results should be summed.
        """
        tool_calls = [
            ToolCall(id="c1", name="search", arguments={"query": "hinge"}),
            ToolCall(id="c2", name="read_file", arguments={"filepath": "/data.md"}),
        ]
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=128_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=FakeCompleter(responses=[
                ("", tool_calls),
                ("Done.", []),
            ]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=ContextBudget(total=128_000),
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Search and read"),
        )

        # TOOL_RESULTS should be sum of both results
        assert ContextSlot.TOOL_RESULTS in output.context_slots
        assert output.context_slots[ContextSlot.TOOL_RESULTS] > 0


# ---------------------------------------------------------------------------
# Tests: Truncation when budget exceeded
# ---------------------------------------------------------------------------

class TestTruncationWhenOverBudget:
    """
    CHECKPOINT 2: When accumulated tool tokens exceed the budget,
    the current result should be truncated to fit remaining budget.
    """

    def test_large_result_truncated(self):
        """
        When a single tool result exceeds the budget, it should be
        truncated and a warning appended.
        """
        # Budget: 128K * 5% = 6,400 tokens
        # FakeTokenCounter: 1 token per 4 chars
        # So 6,400 tokens = 25,600 chars
        # Make a result that's 10,000 tokens (40,000 chars) — way over budget

        big_content = _make_large_content(10_000)  # 40,000 chars = 10,000 tokens
        registry = FakeRegistry(handlers={
            "search": lambda query, **kw: {"content": big_content},
        })

        tool_call = ToolCall(id="c1", name="search", arguments={"query": "everything"})
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=128_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=FakeCompleter(responses=[
                ("", [tool_call]),
                ("Based on partial results.", []),
            ]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=ContextBudget(total=128_000),
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Search everything"),
        )

        # The tool log should show truncated content
        assert len(output.tool_logs) == 1
        result_content = output.tool_logs[0]["result"].get("content", "")
        # Truncated content should be shorter than original
        assert len(result_content) < len(big_content)
        # Should contain truncation marker
        assert "truncat" in result_content.lower()

    def test_truncation_preserves_budget_boundary(self):
        """
        After truncation, the result should fit within the remaining budget.
        """
        budget = ContextBudget(total=128_000)
        tool_budget_tokens = budget.tokens_for(ContextSlot.TOOL_RESULTS)  # 6,400

        # Content that's 3x the budget
        big_content = _make_large_content(tool_budget_tokens * 3)
        registry = FakeRegistry(handlers={
            "search": lambda query, **kw: {"content": big_content},
        })

        tool_call = ToolCall(id="c1", name="search", arguments={"query": "big"})
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=budget,
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=FakeCompleter(responses=[
                ("", [tool_call]),
                ("Partial results.", []),
            ]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=budget,
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Big search"),
        )

        # TOOL_RESULTS in context_slots should not exceed budget
        tool_tokens = output.context_slots.get(ContextSlot.TOOL_RESULTS, 0)
        assert tool_tokens <= tool_budget_tokens


# ---------------------------------------------------------------------------
# Tests: Warning message when truncated
# ---------------------------------------------------------------------------

class TestWarningMessageOnTruncation:
    """
    When tool results are truncated, a warning message should be appended
    to the context so the LLM knows results were incomplete.
    """

    def test_warning_appended_to_tool_result_on_truncation(self):
        """
        After truncation, the tool result content should contain
        a warning about truncated results. This warning is visible to
        the LLM because it's part of the tool result passed to
        complete_with_tools().
        """
        big_content = _make_large_content(10_000)
        registry = FakeRegistry(handlers={
            "search": lambda query, **kw: {"content": big_content},
        })

        tool_call = ToolCall(id="c1", name="search", arguments={"query": "big"})
        provider = FakeCompleter(responses=[
            ("", [tool_call]),
            ("I found partial results.", []),
        ])

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=128_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=ContextBudget(total=128_000),
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Big search"),
        )

        # The tool log should contain the truncation warning
        assert len(output.tool_logs) == 1
        result_content = output.tool_logs[0]["result"]["content"]
        assert "truncat" in result_content.lower()
        assert "answer from what you have" in result_content.lower()


# ---------------------------------------------------------------------------
# Tests: Loop termination on budget exceeded
# ---------------------------------------------------------------------------

class TestLoopTerminationOnBudget:
    """
    CHECKPOINT 3: When the tool budget is exhausted, the tool loop
    should stop even if the LLM requested more tool calls.
    """

    def test_loop_stops_when_budget_exceeded(self):
        """
        After a large tool result exceeds budget, the loop should stop
        and the LLM should produce a text response from what it has.
        """
        big_content = _make_large_content(10_000)  # Over budget
        registry = FakeRegistry(handlers={
            "search": lambda query, **kw: {"content": big_content},
        })

        # LLM wants to call tools twice, but first result is too big
        tool_call = ToolCall(id="c1", name="search", arguments={"query": "big"})
        provider = FakeCompleter(responses=[
            ("", [tool_call]),
            # If loop continues, this would be called — but it shouldn't
            ("", [ToolCall(id="c2", name="search", arguments={"query": "more"})]),
            ("Final answer.", []),
        ])

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=128_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=provider,
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=ContextBudget(total=128_000),
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Big search"),
        )

        # Only 1 tool call should have been made (the first one)
        # The second should have been prevented by budget
        assert len(output.tool_calls_made) == 1
        assert output.tool_calls_made[0].name == "search"

    def test_loop_continues_when_within_budget(self):
        """
        When tool results are within budget, the loop should continue normally.
        """
        small_content = _make_large_content(100)  # Well within budget
        registry = FakeRegistry(handlers={
            "search": lambda query, **kw: {"content": small_content},
        })

        tool_call_1 = ToolCall(id="c1", name="search", arguments={"query": "a"})
        tool_call_2 = ToolCall(id="c2", name="search", arguments={"query": "b"})

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=128_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=FakeCompleter(responses=[
                ("", [tool_call_1]),
                ("", [tool_call_2]),
                ("Done.", []),
            ]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=ContextBudget(total=128_000),
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Two small searches"),
        )

        # Both tool calls should have been made
        assert len(output.tool_calls_made) == 2


# ---------------------------------------------------------------------------
# Tests: Normal operation unaffected
# ---------------------------------------------------------------------------

class TestNormalOperationUnaffected:
    """
    When tool results are within budget, behavior should be identical
    to the current implementation (no regression).
    """

    def test_text_only_response_unchanged(self):
        """Text-only responses (no tools) should be unaffected."""
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=128_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=FakeCompleter(responses=[("Hello!", [])]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=ContextBudget(total=128_000),
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Hi"),
        )

        assert output.assistant_message == "Hello!"
        assert output.tool_calls_made == []

    def test_small_tool_result_unchanged(self):
        """Small tool results within budget should pass through unchanged."""
        small_content = "Small result"
        registry = FakeRegistry(handlers={
            "read_file": lambda filepath: {"content": small_content},
        })

        tool_call = ToolCall(id="c1", name="read_file", arguments={"filepath": "/x.md"})
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=128_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=FakeCompleter(responses=[
                ("", [tool_call]),
                ("File contents shown.", []),
            ]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=ContextBudget(total=128_000),
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Read file"),
        )

        # Result should NOT be truncated
        assert len(output.tool_logs) == 1
        result_content = output.tool_logs[0]["result"]["content"]
        assert "truncat" not in result_content.lower()
        assert small_content in result_content


# ---------------------------------------------------------------------------
# Tests: Token accumulation across iterations
# ---------------------------------------------------------------------------

class TestTokenAccumulation:
    """
    Tokens from multiple tool iterations should accumulate.
    Budget is checked against the total, not per-iteration.
    """

    def test_accumulated_tokens_from_multiple_iterations(self):
        """
        Two iterations with medium results — together they exceed budget,
        but individually they don't.
        """
        # Budget: 6,400 tokens
        # Each result: 4,000 tokens (16,000 chars)
        # First iteration: 4,000 tokens (within budget)
        # Second iteration: 4,000 + 4,000 = 8,000 tokens (over budget)
        medium_content = _make_large_content(4_000)
        registry = FakeRegistry(handlers={
            "search": lambda query, **kw: {"content": medium_content},
        })

        tool_call_1 = ToolCall(id="c1", name="search", arguments={"query": "a"})
        tool_call_2 = ToolCall(id="c2", name="search", arguments={"query": "b"})

        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=128_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=FakeCompleter(responses=[
                ("", [tool_call_1]),
                ("", [tool_call_2]),
                ("Done.", []),
            ]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=ContextBudget(total=128_000),
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Two medium searches"),
        )

        # First call should succeed, second should be truncated or stopped
        # Total TOOL_RESULTS should exceed single iteration but not double
        tool_tokens = output.context_slots.get(ContextSlot.TOOL_RESULTS, 0)
        assert tool_tokens > 0
        # Should be less than 2x the budget (second was truncated/stopped)
        budget = ContextBudget(total=128_000).tokens_for(ContextSlot.TOOL_RESULTS)
        assert tool_tokens <= budget * 2  # At most slightly over due to first iteration


# ---------------------------------------------------------------------------
# Tests: Budget source from ContextBudget
# ---------------------------------------------------------------------------

class TestBudgetSource:
    """
    The tool budget should come from ContextBudget.tokens_for(TOOL_RESULTS).
    """

    def test_budget_respects_context_budget_allocation(self):
        """
        Changing ContextBudget.TOOL_RESULTS allocation should change
        the effective tool budget.
        """
        # Custom budget: 10% for tool results (instead of default 5%)
        custom_budget = ContextBudget(
            total=100_000,
            allocations={
                ContextSlot.SYSTEM_PROMPT: 0.05,
                ContextSlot.CONVERSATION_HISTORY: 0.50,
                ContextSlot.ATTACHED_NOTES: 0.15,
                ContextSlot.ATTACHED_FILES: 0.15,
                ContextSlot.SEARCH_RESULTS: 0.05,
                ContextSlot.TOOL_RESULTS: 0.10,  # 10% = 10,000 tokens
            },
        )

        # Content that's 8,000 tokens (within 10% budget but over 5%)
        content_8k = _make_large_content(8_000)
        registry = FakeRegistry(handlers={
            "search": lambda query, **kw: {"content": content_8k},
        })

        tool_call = ToolCall(id="c1", name="search", arguments={"query": "test"})
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=custom_budget,
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=FakeCompleter(responses=[
                ("", [tool_call]),
                ("Results.", []),
            ]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=custom_budget,
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Search"),
        )

        # With 10% budget (10,000 tokens), 8,000 token result should fit
        result_content = output.tool_logs[0]["result"]["content"]
        assert "truncat" not in result_content.lower()

    def test_small_budget_triggers_truncation(self):
        """
        A very small TOOL_RESULTS budget should trigger truncation
        even for moderate results.
        """
        # Very small budget: 1% of 10,000 = 100 tokens
        small_budget = ContextBudget(
            total=10_000,
            allocations={
                ContextSlot.SYSTEM_PROMPT: 0.05,
                ContextSlot.CONVERSATION_HISTORY: 0.50,
                ContextSlot.ATTACHED_NOTES: 0.15,
                ContextSlot.ATTACHED_FILES: 0.15,
                ContextSlot.SEARCH_RESULTS: 0.14,
                ContextSlot.TOOL_RESULTS: 0.01,  # 1% = 100 tokens
            },
        )

        # Content that's 500 tokens (2,000 chars)
        content_500 = _make_large_content(500)
        registry = FakeRegistry(handlers={
            "search": lambda query, **kw: {"content": content_500},
        })

        tool_call = ToolCall(id="c1", name="search", arguments={"query": "test"})
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=small_budget,
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=registry),
            provider=FakeCompleter(responses=[
                ("", [tool_call]),
                ("Partial.", []),
            ]),
            response_normalizer=ResponseNormalizer(),
            token_counter=FakeTokenCounter(),
            context_budget=small_budget,
        )

        output = orchestrator.run(
            session={"messages": []},
            turn_input=TurnInput(user_message="Search"),
        )

        # Should be truncated (500 tokens > 100 token budget)
        result_content = output.tool_logs[0]["result"]["content"]
        assert "truncat" in result_content.lower()
