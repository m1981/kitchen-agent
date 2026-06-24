"""
tests/unit/test_tool_call_canonical.py
=======================================
Tests for ToolCall as the single canonical type across the codebase.

Observation: ToolCall was defined in 3 places:
  1. src/agent/tool_executor.py   — @dataclass ToolCall
  2. src/providers/normalizer.py  — @dataclass ToolCall (duplicate)
  3. src/message_format.py        — TypedDict ToolCallDict

After consolidation:
  - tool_executor.ToolCall is the single source of truth
  - normalizer.ToolCall re-exports from tool_executor (or is removed)
  - message_format uses tool_executor.ToolCall or keeps TypedDict for dict contexts

These tests verify:
  - All imports resolve to the same class (identity check)
  - Structural compatibility (instances work across module boundaries)
  - No duplicate class definitions exist
"""
from __future__ import annotations

import pytest


class TestToolCallCanonicalSource:
    """ToolCall must have a single canonical definition."""

    def test_tool_executor_is_source_of_truth(self):
        """tool_executor.ToolCall must exist and be a dataclass."""
        from src.agent.tool_executor import ToolCall
        from dataclasses import fields

        assert hasattr(ToolCall, "__dataclass_fields__")
        field_names = {f.name for f in fields(ToolCall)}
        assert field_names == {"id", "name", "arguments", "token_count"}

    def test_normalizer_reexports_same_class(self):
        """normalizer.ToolCall must be the SAME class as tool_executor.ToolCall."""
        from src.agent.tool_executor import ToolCall as Canonical
        from src.providers.normalizer import ToolCall as FromNormalizer

        assert Canonical is FromNormalizer, (
            "normalizer.ToolCall must be imported from tool_executor, "
            "not redefined. Got two different classes."
        )

    def test_normalized_response_uses_canonical_tool_call(self):
        """NormalizedResponse.tool_calls must contain tool_executor.ToolCall instances."""
        from src.agent.tool_executor import ToolCall as Canonical
        from src.providers.normalizer import NormalizedResponse

        tc = Canonical(id="1", name="test", arguments={"x": 1})
        resp = NormalizedResponse(text="hi", has_tool_calls=True, tool_calls=[tc])

        assert isinstance(resp.tool_calls[0], Canonical)

    def test_tool_executor_accepts_canonical_tool_call(self):
        """ToolExecutor must work with the canonical ToolCall."""
        from src.agent.tool_executor import ToolCall, ToolExecutor

        class FakeRegistry:
            def get_handler(self, name):
                return lambda **kw: {"ok": True}

        executor = ToolExecutor(registry=FakeRegistry())
        tc = ToolCall(id="1", name="test", arguments={})
        results = executor.execute_all([tc])

        assert len(results) == 1
        assert results[0].tool_call_id == "1"


class TestToolCallNotDuplicated:
    """Verify no duplicate class definitions exist in source."""

    def test_normalizer_module_has_no_class_def(self):
        """normalizer.py must NOT define its own ToolCall class — it re-exports."""
        import inspect
        import src.providers.normalizer as mod

        source = inspect.getsource(mod)

        # The source should import ToolCall, not define it
        assert "from src.agent.tool_executor import" in source or \
               "from src.agent.tool_executor.ToolCall" in source or \
               "import ToolCall" in source, (
            "normalizer.py must import ToolCall from tool_executor"
        )

        # Should NOT have a class definition for ToolCall
        # (Allow re-export via import, but not class definition)
        lines = source.split("\n")
        class_defs = [
            line for line in lines
            if line.strip().startswith("class ToolCall")
        ]
        assert len(class_defs) == 0, (
            f"normalizer.py still defines its own ToolCall class: {class_defs}"
        )


class TestMessageFormatToolCallDict:
    """message_format.ToolCallDict is a TypedDict for dict-based contexts."""

    def test_tool_call_dict_exists(self):
        """ToolCallDict must still exist for dict-based message formatting."""
        from src.message_format import ToolCallDict

        # Verify it's a TypedDict-like class (has annotations)
        assert hasattr(ToolCallDict, "__annotations__")

    def test_tool_call_dict_fields(self):
        """ToolCallDict must have id, name, arguments fields."""
        from src.message_format import ToolCallDict
        import typing

        hints = typing.get_type_hints(ToolCallDict)
        assert "id" in hints
        assert "name" in hints
        assert "arguments" in hints
