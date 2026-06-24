"""
tests/contract/test_orchestrator_tools.py
==========================================
Contract B7: Orchestrator ↔ ToolExecutor

Rule: Use REAL ToolExecutor, REAL build_default_registry().
Mock only the LLM API and filesystem operations.

This test verifies that:
1. ToolRegistry handlers are correctly dispatched by ToolExecutor
2. ToolResult content is properly feedable to the orchestrator
3. Error handling works across the registry → executor boundary
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.agent.tool_executor import ToolCall, ToolExecutor, ToolResult
from src.tools.registry import build_default_registry


class TestToolExecutorWithRealRegistry:
    """
    Contract: ToolExecutor must correctly dispatch to real ToolRegistry handlers.
    Uses REAL build_default_registry() — no mocked registry.
    """

    @pytest.fixture
    def executor(self):
        """ToolExecutor with real registry (no search coordinator)."""
        registry = build_default_registry(search_coordinator=None)
        return ToolExecutor(registry=registry)

    def test_read_file_returns_content(self, executor, tmp_path):
        """read_file handler must return dict with 'content' key."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello from file!")

        results = executor.execute_all([
            ToolCall(id="1", name="read_file", arguments={"filepath": str(test_file)})
        ])

        assert len(results) == 1
        assert results[0].is_error is False
        assert "Hello from file!" in results[0].content

    def test_read_file_missing_file_returns_error(self, executor):
        """read_file with nonexistent file → returns error dict (not crash)."""
        results = executor.execute_all([
            ToolCall(id="1", name="read_file", arguments={"filepath": "/nonexistent/file.txt"})
        ])

        assert len(results) == 1
        # The handler returns an error dict but doesn't raise,
        # so is_error=False but content contains error info.
        assert "error" in results[0].content.lower() or "not found" in results[0].content.lower()

    def test_unknown_tool_returns_error(self, executor):
        """Unknown tool name → error result, not exception."""
        results = executor.execute_all([
            ToolCall(id="1", name="totally_nonexistent_tool", arguments={})
        ])

        assert len(results) == 1
        assert results[0].is_error is True

    def test_tool_result_id_preserved(self, executor, tmp_path):
        """ToolResult.tool_call_id must match ToolCall.id."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        results = executor.execute_all([
            ToolCall(id="my_unique_id", name="read_file", arguments={"filepath": str(test_file)})
        ])

        assert results[0].tool_call_id == "my_unique_id"

    def test_tool_result_name_preserved(self, executor, tmp_path):
        """ToolResult.name must match ToolCall.name."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        results = executor.execute_all([
            ToolCall(id="1", name="read_file", arguments={"filepath": str(test_file)})
        ])

        assert results[0].name == "read_file"

    def test_multiple_tools_executed(self, executor, tmp_path):
        """Multiple tool calls → all executed independently."""
        file_a = tmp_path / "a.txt"
        file_a.write_text("content A")
        file_b = tmp_path / "b.txt"
        file_b.write_text("content B")

        results = executor.execute_all([
            ToolCall(id="1", name="read_file", arguments={"filepath": str(file_a)}),
            ToolCall(id="2", name="read_file", arguments={"filepath": str(file_b)}),
        ])

        assert len(results) == 2
        assert all(r.is_error is False for r in results)
        assert "content A" in results[0].content
        assert "content B" in results[1].content


class TestToolResultFeedableToOrchestrator:
    """
    Contract: ToolResult from ToolExecutor must be passable to
    TurnOrchestrator's tool loop (fed back to provider.complete_with_tools).
    """

    def test_tool_result_is_string_content(self):
        """ToolResult.content must be a string (not dict, not bytes)."""
        registry = build_default_registry(search_coordinator=None)
        executor = ToolExecutor(registry=registry)

        results = executor.execute_all([
            ToolCall(id="1", name="read_file", arguments={"filepath": __file__})
        ])

        assert isinstance(results[0].content, str)

    def test_tool_result_content_serializable(self):
        """ToolResult.content must be serializable (for logging and persistence)."""
        registry = build_default_registry(search_coordinator=None)
        executor = ToolExecutor(registry=registry)

        results = executor.execute_all([
            ToolCall(id="1", name="read_file", arguments={"filepath": __file__})
        ])

        # Must be JSON-serializable or at least str-representable
        assert len(results[0].content) > 0
        # Should not raise
        json.dumps({"content": results[0].content})
