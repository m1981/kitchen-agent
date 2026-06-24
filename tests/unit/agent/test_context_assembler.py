"""
tests/unit/agent/test_context_assembler.py
=============================================
Unit tests for ContextAssembler — explicit context window building.

The ContextAssembler makes context construction testable and observable:
  - System prompt resolution from PromptManager
  - History trimming when over token budget
  - Context slot observability (where are tokens being spent?)
  - Note and file attachment (future: Phase 5)

Phase 3 scope: system prompt building, history trimming, slot observability.
Context file and note attachment will be added in Phase 5.
"""
import pytest

from src.agent.context_assembler import (
    AssembledContext,
    ContextAssembler,
    ContextBudget,
    ContextSlot,
)


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


def make_assembler(
    total_tokens: int = 10_000,
    system_prompt: str = "You are a helpful assistant.",
) -> ContextAssembler:
    """Test factory — keeps tests clean."""
    return ContextAssembler(
        token_budget=ContextBudget(total=total_tokens),
        token_counter=FakeTokenCounter(),
        prompt_manager=FakePromptManager(prompt=system_prompt),
    )


def make_session(messages: list[dict] | None = None) -> dict:
    """Create a minimal session-like dict for testing."""
    return {"messages": messages or []}


# ---------------------------------------------------------------------------
# Tests: ContextBudget
# ---------------------------------------------------------------------------

class TestContextBudget:
    def test_default_total_is_128k(self):
        budget = ContextBudget()
        assert budget.total == 128_000

    def test_default_allocations_sum_to_one(self):
        budget = ContextBudget()
        total_allocation = sum(budget.allocations.values())
        assert abs(total_allocation - 1.0) < 0.01

    def test_tokens_for_returns_integer(self):
        budget = ContextBudget(total=100_000)
        for slot in ContextSlot:
            result = budget.tokens_for(slot)
            assert isinstance(result, int)

    def test_tokens_for_system_prompt_is_5_percent(self):
        budget = ContextBudget(total=100_000)
        assert budget.tokens_for(ContextSlot.SYSTEM_PROMPT) == 5_000

    def test_tokens_for_history_is_35_percent(self):
        budget = ContextBudget(total=100_000)
        assert budget.tokens_for(ContextSlot.CONVERSATION_HISTORY) == 35_000

    def test_custom_total(self):
        budget = ContextBudget(total=50_000)
        assert budget.tokens_for(ContextSlot.SYSTEM_PROMPT) == 2_500

    def test_custom_allocations(self):
        budget = ContextBudget(
            total=100_000,
            allocations={ContextSlot.SYSTEM_PROMPT: 0.10, ContextSlot.CONVERSATION_HISTORY: 0.90},
        )
        assert budget.tokens_for(ContextSlot.SYSTEM_PROMPT) == 10_000
        assert budget.tokens_for(ContextSlot.CONVERSATION_HISTORY) == 90_000


# ---------------------------------------------------------------------------
# Tests: AssembledContext dataclass
# ---------------------------------------------------------------------------

class TestAssembledContext:
    def test_fields(self):
        ctx = AssembledContext(
            system_prompt="test",
            messages=[{"role": "user", "content": "hello"}],
            total_tokens_estimated=100,
            slots_used={ContextSlot.SYSTEM_PROMPT: 20},
        )
        assert ctx.system_prompt == "test"
        assert len(ctx.messages) == 1
        assert ctx.total_tokens_estimated == 100

    def test_slots_used_observable(self):
        ctx = AssembledContext(
            system_prompt="",
            messages=[],
            total_tokens_estimated=0,
            slots_used={
                ContextSlot.SYSTEM_PROMPT: 20,
                ContextSlot.CONVERSATION_HISTORY: 80,
            },
        )
        assert ctx.slots_used[ContextSlot.SYSTEM_PROMPT] == 20
        assert ctx.slots_used[ContextSlot.CONVERSATION_HISTORY] == 80


# ---------------------------------------------------------------------------
# Tests: ContextAssembler — system prompt
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_assembled_context_contains_system_prompt(self):
        assembler = make_assembler()
        session = make_session()
        ctx = assembler.assemble(session, mode="default", user_message="hello")

        assert ctx.system_prompt == "You are a helpful assistant."

    def test_system_prompt_respects_budget(self):
        """System prompt longer than budget should be trimmed."""
        long_prompt = "A" * 10_000  # 2500 tokens with our counter
        assembler = make_assembler(total_tokens=100, system_prompt=long_prompt)
        session = make_session()
        ctx = assembler.assemble(session, mode="default", user_message="hi")

        # Budget for system prompt = 5% of 100 = 5 tokens
        assert ctx.slots_used[ContextSlot.SYSTEM_PROMPT] <= 5

    def test_system_prompt_slot_in_slots_used(self):
        assembler = make_assembler()
        session = make_session()
        ctx = assembler.assemble(session, mode="default", user_message="hello")

        assert ContextSlot.SYSTEM_PROMPT in ctx.slots_used


# ---------------------------------------------------------------------------
# Tests: ContextAssembler — history trimming
# ---------------------------------------------------------------------------

class TestHistoryTrimming:
    def test_short_history_passes_through(self):
        assembler = make_assembler(total_tokens=10_000)
        session = make_session(messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ])
        ctx = assembler.assemble(session, mode="default", user_message="next")

        # History messages should be present
        history_msgs = [m for m in ctx.messages if m.get("role") in ("user", "assistant") and m.get("content") != "next"]
        assert len(history_msgs) >= 2

    def test_history_trimmed_when_over_budget(self):
        """Long conversations must not exceed token budget."""
        assembler = make_assembler(total_tokens=200)
        # 100 messages × ~25 tokens each = ~2500 tokens — way over budget
        session = make_session(messages=[
            {"role": "user", "content": "This is a test message that is long enough to use tokens"}
            for _ in range(100)
        ])
        ctx = assembler.assemble(session, mode="default", user_message="new message")

        # History budget = 50% of 200 = 100 tokens
        # Should have trimmed significantly
        history_tokens = ctx.slots_used.get(ContextSlot.CONVERSATION_HISTORY, 0)
        assert history_tokens <= 100

    def test_empty_history_produces_empty_history_slot(self):
        assembler = make_assembler()
        session = make_session(messages=[])
        ctx = assembler.assemble(session, mode="default", user_message="hello")

        assert ctx.slots_used[ContextSlot.CONVERSATION_HISTORY] == 0


# ---------------------------------------------------------------------------
# Tests: ContextAssembler — user message inclusion
# ---------------------------------------------------------------------------

class TestUserMessage:
    def test_user_message_included_in_messages(self):
        assembler = make_assembler()
        session = make_session()
        ctx = assembler.assemble(session, mode="default", user_message="What is plywood?")

        assert any(
            m.get("content") == "What is plywood?" and m.get("role") == "user"
            for m in ctx.messages
        )

    def test_user_message_is_last(self):
        assembler = make_assembler()
        session = make_session()
        ctx = assembler.assemble(session, mode="default", user_message="question")

        assert ctx.messages[-1]["content"] == "question"
        assert ctx.messages[-1]["role"] == "user"


# ---------------------------------------------------------------------------
# Tests: ContextSlot enum
# ---------------------------------------------------------------------------

class TestContextSlot:
    def test_all_slots_defined(self):
        expected = {
            "SYSTEM_PROMPT", "CONVERSATION_HISTORY",
            "ATTACHED_NOTES", "ATTACHED_FILES",
            "SEARCH_RESULTS", "TOOL_RESULTS",
        }
        actual = {slot.name for slot in ContextSlot}
        assert actual == expected

    def test_slots_are_unique(self):
        values = [slot.value for slot in ContextSlot]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# Tests: total tokens estimated
# ---------------------------------------------------------------------------

class TestTotalTokens:
    def test_total_tokens_is_sum_of_slots(self):
        assembler = make_assembler()
        session = make_session()
        ctx = assembler.assemble(session, mode="default", user_message="hello")

        assert ctx.total_tokens_estimated == sum(ctx.slots_used.values())

    def test_total_tokens_positive(self):
        assembler = make_assembler()
        session = make_session()
        ctx = assembler.assemble(session, mode="default", user_message="hello")

        assert ctx.total_tokens_estimated > 0
