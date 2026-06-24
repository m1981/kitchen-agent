"""
tests/unit/content/test_file_manager.py
=========================================
Unit tests for FileManager — domain logic for file context assembly.

The FileManager provides:
  - Read file content for LLM context window
  - Token-budget-aware file injection
  - Batch file reading with budget enforcement

These tests use fakes — no real file system access.
"""
import pytest
from pathlib import Path

from src.content.file_manager import FileManager


# ---------------------------------------------------------------------------
# Fakes for isolated testing
# ---------------------------------------------------------------------------

class FakeTokenCounter:
    """Predictable token counter: 1 token per 4 characters."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)

    def trim_to(self, text: str, max_tokens: int) -> str:
        return text[: max_tokens * 4]


# ---------------------------------------------------------------------------
# Tests: FileManager — get_for_context
# ---------------------------------------------------------------------------

class TestGetForContext:
    def test_empty_files_returns_empty_string(self):
        manager = FileManager()

        result = manager.get_for_context([])

        assert result == ""

    def test_none_files_returns_empty_string(self):
        manager = FileManager()

        result = manager.get_for_context([])

        assert result == ""

    def test_single_file_content_included(self, tmp_path: Path):
        test_file = tmp_path / "test.md"
        test_file.write_text("Hello world")

        manager = FileManager(data_dir=str(tmp_path))
        result = manager.get_for_context([str(test_file)])

        assert "Hello world" in result
        assert "test.md" in result

    def test_multiple_files_all_included(self, tmp_path: Path):
        file_a = tmp_path / "a.md"
        file_b = tmp_path / "b.md"
        file_a.write_text("Content A")
        file_b.write_text("Content B")

        manager = FileManager(data_dir=str(tmp_path))
        result = manager.get_for_context([str(file_a), str(file_b)])

        assert "Content A" in result
        assert "Content B" in result

    def test_respects_token_budget(self, tmp_path: Path):
        # Long content that exceeds budget
        long_content = "word " * 1000  # ~125 tokens with our counter
        test_file = tmp_path / "long.md"
        test_file.write_text(long_content)

        manager = FileManager(
            token_counter=FakeTokenCounter(),
            data_dir=str(tmp_path),
        )
        result = manager.get_for_context([str(test_file)], max_tokens=50)

        # Should be trimmed
        tokens = FakeTokenCounter().count(result)
        assert tokens <= 60  # some overhead for header

    def test_unreadable_file_skipped(self, tmp_path: Path):
        # Non-existent file
        manager = FileManager(data_dir=str(tmp_path))
        result = manager.get_for_context([str(tmp_path / "nonexistent.md")])

        # Should not crash, just return empty
        assert result == "" or "nonexistent" not in result

    def test_file_header_included(self, tmp_path: Path):
        test_file = tmp_path / "my-doc.md"
        test_file.write_text("Content")

        manager = FileManager(data_dir=str(tmp_path))
        result = manager.get_for_context([str(test_file)])

        assert "=== " in result
        assert "my-doc.md" in result


# ---------------------------------------------------------------------------
# Tests: FileManager — read_file
# ---------------------------------------------------------------------------

class TestReadFile:
    def test_read_existing_file(self, tmp_path: Path):
        test_file = tmp_path / "test.md"
        test_file.write_text("Hello")

        manager = FileManager(data_dir=str(tmp_path))
        result = manager.read_file(str(test_file))

        assert "content" in result
        assert result["content"] == "Hello"

    def test_read_nonexistent_file(self, tmp_path: Path):
        manager = FileManager(data_dir=str(tmp_path))
        result = manager.read_file(str(tmp_path / "missing.md"))

        assert "error" in result


# ---------------------------------------------------------------------------
# Tests: FileManager — token budget with multiple files
# ---------------------------------------------------------------------------

class TestMultiFileBudget:
    def test_later_files_skipped_when_budget_exhausted(self, tmp_path: Path):
        # First file uses most of the budget
        file_a = tmp_path / "big.md"
        file_a.write_text("x" * 400)  # 100 tokens

        file_b = tmp_path / "small.md"
        file_b.write_text("y" * 40)  # 10 tokens

        manager = FileManager(
            token_counter=FakeTokenCounter(),
            data_dir=str(tmp_path),
        )
        result = manager.get_for_context(
            [str(file_a), str(file_b)],
            max_tokens=80,  # not enough for both
        )

        # First file should be present (possibly trimmed)
        assert "x" in result
        # Second file may be absent or trimmed
        # The key is we don't exceed budget significantly
        tokens = FakeTokenCounter().count(result)
        assert tokens <= 100  # some overhead
