"""
tests/unit/agent/test_turn_orchestrator.py
============================================
Unit tests for TurnOrchestrator — manages one complete chat turn lifecycle.

The TurnOrchestrator composes ContextAssembler + ToolExecutor + LLM provider
to execute a single conversational turn.  It owns the agentic tool loop and
delegates to the extracted components for context building, tool execution,
and response normalization.

These tests use fakes for all dependencies — no real LLM calls, no real tools,
no real token counting.  Each test exercises one specific behavior of the
orchestrator.

Phase 4 scope: simple LLM responses, tool loops, error propagation,
max iteration guard.
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
    MaxToolIterationsError,
    TurnInput,
    TurnOrchestrator,
    TurnOutput,
)
from src.providers.base import LLMProvider
from src.providers.normalizer import NormalizedResponse, ResponseNormalizer


# ---------------------------------------------------------------------------
# Gemini mock response helpers
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
# Fakes for isolated testing
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
            "read_file": lambda filepath: f"content of {filepath}",
            "echo": lambda text: f"echoed: {text}",
        }

    def get_handler(self, name: str):
        if name not in self._handlers:
            raise ValueError(f"Unknown tool: {name!r}")
        return self._handlers[name]


class FakeCompleter:
    """
    Controllable LLM provider implementing LLMProvider protocol.

    Returns mock Gemini SDK responses that ResponseNormalizer can parse.

    Supports:
    - Single response (text only)
    - Single response (tool call only)
    - Sequence of responses (tool call → text)
    - Always-tool-call mode (for testing max iterations)
    - Error mode
    """

    def __init__(
        self,
        text: str = "Default fake response.",
        tool_calls: list[ToolCall] | None = None,
        responses: list[tuple[str, list[ToolCall]]] | None = None,
        always_returns_tool_call: bool = False,
        raises: Exception | None = None,
    ) -> None:
        self._raises = raises
        self._always_tool_call = always_returns_tool_call
        self._call_count = 0
        self.complete_call_count = 0
        self.last_context: AssembledContext | None = None
        self.all_contexts: list[AssembledContext] = []

        if responses:
            self._responses = responses
        elif tool_calls:
            self._responses = [("", tool_calls)]
        else:
            self._responses = [(text, [])]

    def complete(self, context: AssembledContext) -> MagicMock:
        self.complete_call_count += 1
        self.last_context = context
        self.all_contexts.append(context)

        if self._raises:
            raise self._raises

        if self._always_tool_call:
            return _gemini_tool_call_response([
                ToolCall(
                    id=str(self._call_count),
                    name="read_file",
                    arguments={"filepath": "/loop"},
                )
            ])

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


def make_orchestrator(
    text: str = "Default fake response.",
    tool_calls: list[ToolCall] | None = None,
    responses: list[tuple[str, list[ToolCall]]] | None = None,
    always_returns_tool_call: bool = False,
    raises: Exception | None = None,
    total_tokens: int = 10_000,
    max_tool_iterations: int = 10,
    token_counter: FakeTokenCounter | None = None,
) -> TurnOrchestrator:
    """Test factory — keeps tests clean."""
    tc = token_counter or FakeTokenCounter()
    return TurnOrchestrator(
        context_assembler=ContextAssembler(
            token_budget=ContextBudget(total=total_tokens),
            token_counter=tc,
            prompt_manager=FakePromptManager(),
        ),
        tool_executor=ToolExecutor(registry=FakeRegistry(), token_counter=tc),
        provider=FakeCompleter(
            text=text,
            tool_calls=tool_calls,
            responses=responses,
            always_returns_tool_call=always_returns_tool_call,
            raises=raises,
        ),
        response_normalizer=ResponseNormalizer(),
        max_tool_iterations=max_tool_iterations,
        token_counter=tc,
    )


def make_session(messages: list[dict] | None = None) -> dict:
    """Create a minimal session-like dict for testing."""
    return {"messages": messages or []}


# ---------------------------------------------------------------------------
# Tests: simple text response (no tools)
# ---------------------------------------------------------------------------

class TestSimpleTextResponse:
    def test_returns_assistant_message(self):
        orchestrator = make_orchestrator(text="Hello back!")
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello"),
        )
        assert output.assistant_message == "Hello back!"

    def test_tool_calls_made_empty(self):
        orchestrator = make_orchestrator(text="Simple answer.")
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Question"),
        )
        assert output.tool_calls_made == []

    def test_tokens_used_populated(self):
        orchestrator = make_orchestrator(text="Response.")
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Question"),
        )
        assert "input" in output.tokens_used
        assert "output" in output.tokens_used
        assert "total" in output.tokens_used

    def test_context_slots_populated(self):
        orchestrator = make_orchestrator(text="Response.")
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Question"),
        )
        assert ContextSlot.SYSTEM_PROMPT in output.context_slots
        assert ContextSlot.CONVERSATION_HISTORY in output.context_slots


# ---------------------------------------------------------------------------
# Tests: single tool call
# ---------------------------------------------------------------------------

class TestSingleToolCall:
    def test_tool_call_executed_and_result_returned(self):
        """LLM calls a tool, gets result, responds with text."""
        tool_call = ToolCall(
            id="call_1", name="read_file", arguments={"filepath": "/test.md"}
        )
        orchestrator = make_orchestrator(
            responses=[
                ("", [tool_call]),           # first: tool call
                ("Here is the file.", []),   # second: text answer
            ]
        )

        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Read /test.md"),
        )

        assert output.assistant_message == "Here is the file."
        assert any(tc.name == "read_file" for tc in output.tool_calls_made)

    def test_tool_call_name_recorded(self):
        tool_call = ToolCall(
            id="c1", name="echo", arguments={"text": "hi"}
        )
        orchestrator = make_orchestrator(
            responses=[
                ("", [tool_call]),
                ("Done.", []),
            ]
        )

        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Echo hi"),
        )

        assert any(tc.name == "echo" for tc in output.tool_calls_made)

    def test_provider_called_twice_for_tool_loop(self):
        tool_call = ToolCall(
            id="c1", name="read_file", arguments={"filepath": "/x.md"}
        )
        orchestrator = make_orchestrator(
            responses=[
                ("", [tool_call]),
                ("Answer.", []),
            ]
        )
        provider = orchestrator._provider

        orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Read"),
        )

        assert provider.complete_call_count == 2


# ---------------------------------------------------------------------------
# Tests: multiple tool calls in one turn
# ---------------------------------------------------------------------------

class TestMultipleToolCalls:
    def test_multiple_tool_calls_in_single_iteration(self):
        """LLM requests multiple tools at once — all executed."""
        tool_calls = [
            ToolCall(id="c1", name="read_file", arguments={"filepath": "/a.md"}),
            ToolCall(id="c2", name="echo", arguments={"text": "hello"}),
        ]
        orchestrator = make_orchestrator(
            responses=[
                ("", tool_calls),
                ("All done.", []),
            ]
        )

        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Read and echo"),
        )

        assert any(tc.name == "read_file" for tc in output.tool_calls_made)
        assert any(tc.name == "echo" for tc in output.tool_calls_made)
        assert len(output.tool_calls_made) == 2

    def test_sequential_tool_iterations(self):
        """LLM calls tool, gets result, calls another tool, then responds."""
        first_tool = ToolCall(id="c1", name="read_file", arguments={"filepath": "/a.md"})
        second_tool = ToolCall(id="c2", name="echo", arguments={"text": "processed"})

        orchestrator = make_orchestrator(
            responses=[
                ("", [first_tool]),
                ("", [second_tool]),
                ("Final answer.", []),
            ]
        )

        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Multi-step"),
        )

        assert output.assistant_message == "Final answer."
        assert len(output.tool_calls_made) == 2
        assert output.tool_calls_made[0].name == "read_file"
        assert output.tool_calls_made[1].name == "echo"


# ---------------------------------------------------------------------------
# Tests: max tool iterations guard
# ---------------------------------------------------------------------------

class TestMaxToolIterations:
    def test_raises_when_exceeded(self):
        """Infinite tool loop must be caught and raised."""
        orchestrator = make_orchestrator(
            always_returns_tool_call=True,
            max_tool_iterations=3,
        )

        with pytest.raises(MaxToolIterationsError) as exc_info:
            orchestrator.run(
                session=make_session(),
                turn_input=TurnInput(user_message="Loop forever"),
            )

        assert exc_info.value.max_iterations == 3

    def test_error_message_includes_limit(self):
        orchestrator = make_orchestrator(
            always_returns_tool_call=True,
            max_tool_iterations=5,
        )

        with pytest.raises(MaxToolIterationsError, match="5"):
            orchestrator.run(
                session=make_session(),
                turn_input=TurnInput(user_message="Loop"),
            )

    def test_exactly_at_limit_succeeds(self):
        """If tool calls stop exactly at the limit, it should succeed."""
        # Create exactly max_iterations tool-call responses, then a text response
        tool_call = ToolCall(id="c1", name="read_file", arguments={"filepath": "/x"})
        responses = [("", [tool_call]) for _ in range(3)]
        responses.append(("Done.", []))

        orchestrator = make_orchestrator(
            responses=responses,
            max_tool_iterations=3,
        )

        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Exactly at limit"),
        )

        assert output.assistant_message == "Done."


# ---------------------------------------------------------------------------
# Tests: provider error propagation
# ---------------------------------------------------------------------------

class TestProviderErrors:
    def test_provider_exception_propagates(self):
        """If the LLM raises, the error must propagate to the caller."""
        orchestrator = make_orchestrator(
            raises=RuntimeError("Rate limit exceeded"),
        )

        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            orchestrator.run(
                session=make_session(),
                turn_input=TurnInput(user_message="Hello"),
            )


# ---------------------------------------------------------------------------
# Tests: context assembly integration
# ---------------------------------------------------------------------------

class TestContextAssembly:
    def test_context_assembler_receives_user_message(self):
        orchestrator = make_orchestrator(text="Response.")
        provider = orchestrator._provider

        orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="What is plywood?"),
        )

        ctx = provider.last_context
        assert any(
            m.get("content") == "What is plywood?" and m.get("role") == "user"
            for m in ctx.messages
        )

    def test_context_assembler_receives_mode(self):
        orchestrator = make_orchestrator(text="Response.")
        provider = orchestrator._provider

        orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello", mode="kitchen"),
        )

        ctx = provider.last_context
        # The system prompt should be present (from FakePromptManager)
        assert ctx.system_prompt == "You are a helpful assistant."

    def test_context_assembler_receives_session_history(self):
        session = make_session(messages=[
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ])
        orchestrator = make_orchestrator(text="Response.")
        provider = orchestrator._provider

        orchestrator.run(
            session=session,
            turn_input=TurnInput(user_message="Follow-up"),
        )

        ctx = provider.last_context
        # History messages should be present
        history_msgs = [
            m for m in ctx.messages
            if m.get("content") in ("Previous question", "Previous answer")
        ]
        assert len(history_msgs) == 2

    def test_context_slots_observed(self):
        orchestrator = make_orchestrator(text="Response.")

        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello"),
        )

        assert isinstance(output.context_slots, dict)
        assert all(isinstance(v, int) for v in output.context_slots.values())


# ---------------------------------------------------------------------------
# Tests: TurnInput dataclass
# ---------------------------------------------------------------------------

class TestTurnInput:
    def test_defaults(self):
        ti = TurnInput(user_message="hello")
        assert ti.user_message == "hello"
        assert ti.mode == "default"
        assert ti.note_ids == []
        assert ti.file_ids == []

    def test_with_all_fields(self):
        ti = TurnInput(
            user_message="question",
            mode="kitchen",
            note_ids=["n1", "n2"],
            file_ids=["f1"],
        )
        assert ti.mode == "kitchen"
        assert ti.note_ids == ["n1", "n2"]
        assert ti.file_ids == ["f1"]


# ---------------------------------------------------------------------------
# Tests: TurnOutput dataclass
# ---------------------------------------------------------------------------

class TestTurnOutput:
    def test_fields(self):
        output = TurnOutput(
            assistant_message="Answer.",
            user_turn_id="u1",
            assistant_turn_id="a1",
            tool_calls_made=[ToolCall(id="c1", name="read_file", arguments={})],
            tool_details=[],
            tool_logs=[{"name": "read_file", "args": {}, "result": {}}],
            tokens_used={"input": 10, "output": 5, "total": 15},
            context_slots={ContextSlot.SYSTEM_PROMPT: 20},
        )
        assert output.assistant_message == "Answer."
        assert any(tc.name == "read_file" for tc in output.tool_calls_made)
        assert output.tokens_used["total"] == 15


# ---------------------------------------------------------------------------
# Tests: MaxToolIterationsError
# ---------------------------------------------------------------------------

class TestMaxToolIterationsError:
    def test_is_exception(self):
        err = MaxToolIterationsError(10)
        assert isinstance(err, Exception)

    def test_stores_max_iterations(self):
        err = MaxToolIterationsError(5)
        assert err.max_iterations == 5

    def test_message_includes_limit(self):
        err = MaxToolIterationsError(7)
        assert "7" in str(err)


# ---------------------------------------------------------------------------
# Tests: tool executor error in loop
# ---------------------------------------------------------------------------

class TestToolErrorInLoop:
    def test_tool_error_still_continues_to_llm(self):
        """Even if a tool fails, the error is fed back to the LLM."""
        failing_tool = ToolCall(
            id="c1", name="nonexistent", arguments={}
        )
        orchestrator = make_orchestrator(
            responses=[
                ("", [failing_tool]),
                ("I couldn't read the file.", []),
            ]
        )

        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Read something"),
        )

        # The error was fed to the LLM and it responded
        assert output.assistant_message == "I couldn't read the file."
        assert any(tc.name == "nonexistent" for tc in output.tool_calls_made)


# ---------------------------------------------------------------------------
# Tests: integration with real ContextAssembler
# ---------------------------------------------------------------------------

class TestRealContextAssemblerIntegration:
    def test_history_budget_enforced(self):
        """TurnOrchestrator respects ContextAssembler's token budget."""
        # Create a session with many messages
        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(100)
        ]
        session = make_session(messages=messages)

        # Small budget to force trimming
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=200),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=FakeCompleter(text="Response."),
            response_normalizer=ResponseNormalizer(),
        )
        provider = orchestrator._provider

        orchestrator.run(
            session=session,
            turn_input=TurnInput(user_message="New message"),
        )

        ctx = provider.last_context
        # Total tokens should be within budget
        assert ctx.total_tokens_estimated <= 200


# ---------------------------------------------------------------------------
# Tests: LLMProvider protocol compliance
# ---------------------------------------------------------------------------

class TestLLMProviderProtocol:
    def test_fake_completer_satisfies_protocol(self):
        """FakeCompleter must satisfy the LLMProvider protocol."""
        completer = FakeCompleter(text="test")
        # This is a structural check — if FakeCompleter has the right
        # methods, it satisfies the protocol without explicit inheritance.
        assert hasattr(completer, "complete")
        assert hasattr(completer, "complete_with_tools")

    def test_complete_returns_normalized_response(self):
        """complete() must return something normalize() can handle."""
        completer = FakeCompleter(text="Hello")
        ctx = AssembledContext(
            system_prompt="test",
            messages=[{"role": "user", "content": "hi"}],
            total_tokens_estimated=10,
            slots_used={},
        )
        # Should not raise
        result = completer.complete(ctx)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: provider routing
# ---------------------------------------------------------------------------

class TestProviderRouting:
    def test_default_provider_used_when_no_override(self):
        """When TurnInput.provider is None, the default provider is used."""
        default_provider = FakeCompleter(text="default response")
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
            session=make_session(),
            turn_input=TurnInput(user_message="Hello"),
        )

        assert output.assistant_message == "default response"
        assert default_provider.complete_call_count == 1

    def test_provider_override_creates_new_provider(self, monkeypatch):
        """When TurnInput.provider is set, a new provider should be created."""
        from src.providers.base import get_provider

        default_provider = FakeCompleter(text="default response")
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

        # Track calls to get_provider
        created_providers = []
        original_get_provider = get_provider

        def tracking_get_provider(provider_name=None, model_override=None):
            provider = original_get_provider(provider_name=provider_name, model_override=model_override)
            created_providers.append((provider_name, model_override))
            return provider

        monkeypatch.setattr("src.providers.base.get_provider", tracking_get_provider)

        # Mock the actual provider to avoid real API calls
        mock_provider = FakeCompleter(text="override response")
        monkeypatch.setattr("src.providers.base.get_provider",
            lambda provider_name=None, model_override=None: mock_provider)

        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello", provider="anthropic", model="claude-sonnet"),
        )

        # The mock provider should have been called, not the default
        assert mock_provider.complete_call_count == 1
        assert default_provider.complete_call_count == 0

    def test_provider_name_used_for_tool_schemas(self):
        """When provider is overridden, tool schemas should use the new provider name."""
        schema_calls = []

        class TrackingRegistry:
            def schemas_for_provider(self, provider):
                schema_calls.append(provider)
                return []

        registry = TrackingRegistry()
        orchestrator = TurnOrchestrator(
            context_assembler=ContextAssembler(
                token_budget=ContextBudget(total=10_000),
                token_counter=FakeTokenCounter(),
                prompt_manager=FakePromptManager(),
            ),
            tool_executor=ToolExecutor(registry=FakeRegistry()),
            provider=FakeCompleter(text="response"),
            response_normalizer=ResponseNormalizer(),
            provider_name="gemini",
            tool_registry=registry,
        )

        # With override
        orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello", provider="anthropic", use_tools=True),
        )
        assert schema_calls[-1] == "anthropic"

        # Without override
        orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello", use_tools=True),
        )
        assert schema_calls[-1] == "gemini"


# ---------------------------------------------------------------------------
# Tests: token_breakdown in TurnOutput
# ---------------------------------------------------------------------------

class TestTokenBreakdown:
    """TurnOutput.token_breakdown should be populated correctly."""

    def test_text_only_has_user_and_assistant_tokens(self):
        orchestrator = make_orchestrator(text="Hello back!")
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello"),
        )
        assert output.token_breakdown.user_message_tokens > 0
        assert output.token_breakdown.assistant_tokens > 0
        assert output.token_breakdown.tool_calls_tokens == 0
        assert output.token_breakdown.tool_results_tokens == 0
        assert output.token_breakdown.turn_total > 0

    def test_turn_total_sums_all_components(self):
        orchestrator = make_orchestrator(text="Response.")
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello"),
        )
        expected = (
            output.token_breakdown.user_message_tokens
            + output.token_breakdown.tool_calls_tokens
            + output.token_breakdown.tool_results_tokens
            + output.token_breakdown.assistant_tokens
        )
        assert output.token_breakdown.turn_total == expected

    def test_tool_calls_have_tokens(self):
        tool_call = ToolCall(id="c1", name="echo", arguments={"text": "hi"})
        orchestrator = make_orchestrator(
            responses=[
                ("", [tool_call]),
                ("Done.", []),
            ]
        )
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Echo hi"),
        )
        assert output.token_breakdown.tool_calls_tokens > 0
        assert output.token_breakdown.tool_results_tokens > 0

    def test_conversation_total_not_set_by_orchestrator(self):
        """conversation_total is now ChatService's responsibility — orchestrator leaves it at 0."""
        session = make_session(messages=[
            {"role": "user", "content": "Previous question", "token_count": 5},
            {"role": "assistant", "content": "Previous answer", "token_count": 4},
        ])
        orchestrator = make_orchestrator(text="New response.")
        output = orchestrator.run(
            session=session,
            turn_input=TurnInput(user_message="New question"),
        )
        # Orchestrator returns raw facts — conversation_total is 0
        assert output.token_breakdown.conversation_total == 0
        # But turn_total is still calculated (this turn only)
        assert output.token_breakdown.turn_total > 0

    def test_user_message_token_count_matches_counter(self):
        counter = FakeTokenCounter()
        orchestrator = make_orchestrator(text="Ok.")
        orchestrator._token_counter = counter
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Test message"),
        )
        expected = counter.count("Test message")
        assert output.token_breakdown.user_message_tokens == expected

    def test_assistant_tokens_match_counter(self):
        counter = FakeTokenCounter()
        orchestrator = make_orchestrator(text="Hello back!")
        orchestrator._token_counter = counter
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello"),
        )
        expected = counter.count("Hello back!")
        assert output.token_breakdown.assistant_tokens == expected

    def test_tool_details_populated_from_orchestrator(self):
        """TurnOutput.tool_details should be populated (raw facts for history building)."""
        orchestrator = make_orchestrator(text="Response.")
        output = orchestrator.run(
            session=make_session(),
            turn_input=TurnInput(user_message="Hello"),
        )
        # No tools used — tool_details should be empty
        assert output.tool_details == []
        # Token breakdown should still be populated
        assert output.token_breakdown.user_message_tokens > 0
        assert output.token_breakdown.assistant_tokens > 0
