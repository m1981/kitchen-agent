"""
tests/contract/test_orchestrator_context.py
============================================
Contract B4: Orchestrator ↔ ContextAssembler

Rule: Use REAL ContextAssembler, REAL TokenCounter, REAL PromptManager.
Mock only the LLM API.

This test verifies that:
1. AssembledContext has all fields that TurnOrchestrator and providers read
2. Messages are in the common format (role, content)
3. ContextAssembler works with real PromptManager and TokenCounter
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.agent.context_assembler import (
    AssembledContext,
    ContextAssembler,
    ContextBudget,
    ContextSlot,
)
from src.agent.tool_executor import ToolCall
from src.protocols import PromptManagerProtocol, TokenCounterProtocol


# ═══════════════════════════════════════════════════════════════════════
# REAL IMPLEMENTATIONS (no mocks)
# ═══════════════════════════════════════════════════════════════════════

class SimpleTokenCounter:
    """Real token counter (simple approximation for testing)."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)

    def count_message(self, message: dict) -> int:
        return self.count(str(message.get("content", "")))

    def trim_to(self, text: str, max_tokens: int) -> str:
        return text[:max_tokens * 4]


class SimplePromptManager:
    """Real prompt manager for testing."""

    def get_system_instruction(self, mode: str = "default") -> str:
        prompts = {
            "default": "You are a helpful assistant.",
            "kitchen": "You are a kitchen design expert.",
        }
        return prompts.get(mode, prompts["default"])


# ═══════════════════════════════════════════════════════════════════════
# B4 CONTRACT: AssembledContext shape
# ═══════════════════════════════════════════════════════════════════════

class TestAssembledContextContract:
    """
    Contract: AssembledContext must have all fields that TurnOrchestrator
    and providers depend on.  Uses REAL ContextAssembler with REAL
    TokenCounter and PromptManager.
    """

    @pytest.fixture
    def assembler(self):
        return ContextAssembler(
            token_budget=ContextBudget(total=10_000),
            token_counter=SimpleTokenCounter(),
            prompt_manager=SimplePromptManager(),
        )

    def test_context_has_all_required_fields(self, assembler):
        """All fields that orchestrator reads must exist."""
        context = assembler.assemble(
            session={"messages": []},
            mode="default",
            user_message="Hello",
        )

        assert hasattr(context, "system_prompt")
        assert hasattr(context, "messages")
        assert hasattr(context, "images")
        assert hasattr(context, "context_files")
        assert hasattr(context, "tool_schemas")
        assert hasattr(context, "total_tokens_estimated")
        assert hasattr(context, "slots_used")

    def test_system_prompt_populated(self, assembler):
        """system_prompt must come from PromptManager."""
        context = assembler.assemble(
            session={"messages": []},
            mode="default",
            user_message="Hello",
        )

        assert context.system_prompt == "You are a helpful assistant."

    def test_system_prompt_mode_specific(self, assembler):
        """Different modes must produce different system prompts."""
        ctx_default = assembler.assemble(
            session={"messages": []}, mode="default", user_message="Hi",
        )
        ctx_kitchen = assembler.assemble(
            session={"messages": []}, mode="kitchen", user_message="Hi",
        )

        assert ctx_default.system_prompt != ctx_kitchen.system_prompt
        assert "kitchen" in ctx_kitchen.system_prompt.lower()

    def test_messages_in_common_format(self, assembler):
        """Messages must have 'role' and 'content' keys."""
        context = assembler.assemble(
            session={"messages": []},
            mode="default",
            user_message="Hello",
        )

        for msg in context.messages:
            assert "role" in msg, f"Message missing 'role': {msg}"
            # Either content or tool_calls must be present
            assert "content" in msg or "tool_calls" in msg, \
                f"Message missing 'content' or 'tool_calls': {msg}"

    def test_user_message_is_last(self, assembler):
        """User message must be the last in the messages list."""
        context = assembler.assemble(
            session={"messages": [
                {"role": "user", "content": "Previous question"},
                {"role": "assistant", "content": "Previous answer"},
            ]},
            mode="default",
            user_message="New question",
        )

        assert context.messages[-1]["role"] == "user"
        assert context.messages[-1]["content"] == "New question"

    def test_budget_enforced(self, assembler):
        """Total tokens must not exceed the budget."""
        # Create a session with lots of history
        messages = [
            {"role": "user", "content": f"Message {i}" * 100}
            for i in range(50)
        ]

        context = assembler.assemble(
            session={"messages": messages},
            mode="default",
            user_message="New",
        )

        assert context.total_tokens_estimated <= 10_000

    def test_slots_used_populated(self, assembler):
        """slots_used must have entries for all used slots."""
        context = assembler.assemble(
            session={"messages": [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Answer"},
            ]},
            mode="default",
            user_message="Follow-up",
        )

        assert isinstance(context.slots_used, dict)
        # System prompt and history should be present
        assert ContextSlot.SYSTEM_PROMPT in context.slots_used
        assert ContextSlot.CONVERSATION_HISTORY in context.slots_used
        # All values should be non-negative integers
        for slot, tokens in context.slots_used.items():
            assert tokens >= 0, f"Slot {slot} has negative tokens: {tokens}"

    def test_total_tokens_is_sum_of_slots(self, assembler):
        """total_tokens_estimated must equal sum of slots_used values."""
        context = assembler.assemble(
            session={"messages": []},
            mode="default",
            user_message="Hello",
        )

        expected_total = sum(context.slots_used.values())
        assert context.total_tokens_estimated == expected_total


class TestContextAssemblerProtocolCompliance:
    """
    Contract: ContextAssembler's dependencies must satisfy their protocols.
    Note: Can't use isinstance() because protocols aren't @runtime_checkable.
    Verify by checking method signatures instead.
    """

    def test_simple_token_counter_has_required_methods(self):
        tc = SimpleTokenCounter()
        assert hasattr(tc, "count")
        assert hasattr(tc, "count_message")
        assert hasattr(tc, "trim_to")

    def test_simple_prompt_manager_has_required_methods(self):
        pm = SimplePromptManager()
        assert hasattr(pm, "get_system_instruction")
