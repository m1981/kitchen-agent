"""
tests/test_prompt_logger.py
============================
TDD suite for the enriched prompt / activity log.

The log is the user's "work diary" — a human-readable Markdown file they can
open on Friday morning to recall what they asked, which files the LLM changed,
and exactly what was added or removed.

Coverage matrix
---------------
UNIT — log_turn()
  1.  Creates file + parent dirs when absent
  2.  Appends without overwriting (chronological order preserved)
  3.  Ignores empty / whitespace-only messages
  4.  Each entry has a ## timestamp heading (HH:MM, not seconds)
  5.  Entries are grouped under a ### date banner (one per calendar day)
  6.  Date banner NOT duplicated on same-day subsequent entries
  7.  Session context line is written (session_id + title)
  8.  User message block is written verbatim
  9.  Tool section absent when no tools used (clean chat turn)
  10. Tool section present when tools used — tool name + path appear
  11. edit_file: diff lines (+added / -removed) are rendered
  12. create_file: full content lines are shown with + prefix
  13. read_file: filepath shown as "📖 Read" (no diff — read-only)
  14. search_knowledge_base: query shown as "🔍 Searched"
  15. get_repo_map: shown as "🗺 Repo map scanned" (no args)
  16. Unknown tool: still recorded with raw result snippet
  17. Multiple tool calls in one turn all appear
  18. Diff truncated when content exceeds MAX_DIFF_LINES
  19. log_turn falls back to settings.prompt_log_path when log_path omitted
  20. Backward-compat: log_prompt() still works (delegates to log_turn)

INTEGRATION — log survives real chat_service wiring
  21. ChatService calls log_turn with tool data (monkeypatching agent)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.prompt_logger import log_prompt, log_turn, MAX_DIFF_LINES
from tests.helpers import FakeOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _make_log(tmp_path: Path) -> Path:
    return tmp_path / "prompt_log.md"


# ---------------------------------------------------------------------------
# 1. File creation
# ---------------------------------------------------------------------------

class TestFileCreation:
    def test_creates_file_if_missing(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("Hello", log_path=log_path)
        assert log_path.exists()

    def test_creates_nested_parent_dirs(self, tmp_path: Path) -> None:
        log_path = tmp_path / "deep" / "nested" / "prompt_log.md"
        log_turn("Hello", log_path=log_path)
        assert log_path.exists()


# ---------------------------------------------------------------------------
# 2. Append semantics
# ---------------------------------------------------------------------------

class TestAppendSemantics:
    def test_second_entry_appended_not_overwritten(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("FIRST_PROMPT", log_path=log_path)
        log_turn("SECOND_PROMPT", log_path=log_path)
        content = _read(log_path)
        assert "FIRST_PROMPT" in content
        assert "SECOND_PROMPT" in content
        assert content.index("FIRST_PROMPT") < content.index("SECOND_PROMPT")

    def test_many_entries_remain_chronological(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        prompts = [f"MSG_{i}" for i in range(5)]
        for p in prompts:
            log_turn(p, log_path=log_path)
        content = _read(log_path)
        positions = [content.index(p) for p in prompts]
        assert positions == sorted(positions)


# ---------------------------------------------------------------------------
# 3. Empty / blank message ignored
# ---------------------------------------------------------------------------

class TestIgnoresEmptyPrompts:
    def test_empty_string_not_logged(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("", log_path=log_path)
        assert not log_path.exists()

    def test_whitespace_only_not_logged(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("   \n\t  ", log_path=log_path)
        assert not log_path.exists()

    def test_none_treated_as_empty(self, tmp_path: Path) -> None:
        """None message (type: ignore) should be silently skipped."""
        log_path = _make_log(tmp_path)
        log_turn(None, log_path=log_path)  # type: ignore[arg-type]
        assert not log_path.exists()


# ---------------------------------------------------------------------------
# 4. Timestamp heading format
# ---------------------------------------------------------------------------

class TestTimestampHeading:
    def test_heading_starts_with_double_hash(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("Check heading", log_path=log_path)
        content = _read(log_path)
        # First non-whitespace structural line should be a date banner (###)
        # then the turn heading (##)
        assert "## " in content

    def test_heading_contains_time_hhmm(self, tmp_path: Path) -> None:
        """Heading shows HH:MM — granular enough for "Friday recall" without second noise."""
        log_path = _make_log(tmp_path)
        now = datetime(2026, 5, 30, 14, 7, 42)
        with patch("src.prompt_logger.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.strftime = datetime.strftime
            log_turn("Time test", log_path=log_path)
        content = _read(log_path)
        assert "14:07" in content

    def test_heading_does_NOT_include_seconds(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        now = datetime(2026, 5, 30, 14, 7, 42)
        with patch("src.prompt_logger.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.strftime = datetime.strftime
            log_turn("Time test", log_path=log_path)
        content = _read(log_path)
        assert ":42" not in content


# ---------------------------------------------------------------------------
# 5 & 6. Date banner grouping
# ---------------------------------------------------------------------------

class TestDateBanner:
    def test_date_banner_written_once_per_day(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        same_day = datetime(2026, 5, 30, 10, 0, 0)
        with patch("src.prompt_logger.datetime") as mock_dt:
            mock_dt.now.return_value = same_day
            mock_dt.strftime = datetime.strftime
            log_turn("Morning prompt", log_path=log_path)
            log_turn("Afternoon prompt", log_path=log_path)
        content = _read(log_path)
        # Banner for "2026-05-30" must appear exactly once
        assert content.count("# 2026-05-30") == 1

    def test_date_banner_written_for_each_new_day(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        day1 = datetime(2026, 5, 29, 10, 0, 0)
        day2 = datetime(2026, 5, 30, 10, 0, 0)
        with patch("src.prompt_logger.datetime") as mock_dt:
            mock_dt.now.return_value = day1
            mock_dt.strftime = datetime.strftime
            log_turn("Friday prompt", log_path=log_path)
        with patch("src.prompt_logger.datetime") as mock_dt:
            mock_dt.now.return_value = day2
            mock_dt.strftime = datetime.strftime
            log_turn("Saturday prompt", log_path=log_path)
        content = _read(log_path)
        assert "# 2026-05-29" in content
        assert "# 2026-05-30" in content


# ---------------------------------------------------------------------------
# 7. Session context line
# ---------------------------------------------------------------------------

class TestSessionContext:
    def test_session_id_appears_when_provided(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("Hello", session_id="abc-123", log_path=log_path)
        assert "abc-123" in _read(log_path)

    def test_session_title_appears_when_provided(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("Hello", session_title="Moje zawiasy", log_path=log_path)
        assert "Moje zawiasy" in _read(log_path)

    def test_session_context_absent_when_not_provided(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("Hello", log_path=log_path)
        content = _read(log_path)
        # Should not contain the session label at all
        assert "Session:" not in content

    def test_session_id_truncated_to_8_chars(self, tmp_path: Path) -> None:
        """Long UUIDs are shown as first-8 chars to keep the log readable."""
        log_path = _make_log(tmp_path)
        full_uuid = "abcdef12-5678-0000-0000-000000000000"
        log_turn("Hello", session_id=full_uuid, log_path=log_path)
        content = _read(log_path)
        assert "abcdef12" in content
        # The full UUID should NOT appear verbatim
        assert full_uuid not in content


# ---------------------------------------------------------------------------
# 8. User message block
# ---------------------------------------------------------------------------

class TestUserMessageBlock:
    def test_user_message_appears_verbatim(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        msg = "Jakie zawiasy Blum są najlepsze do szafek górnych?"
        log_turn(msg, log_path=log_path)
        assert msg in _read(log_path)

    def test_multiline_message_fully_preserved(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        msg = "Line one\nLine two\nLine three"
        log_turn(msg, log_path=log_path)
        assert "Line one" in _read(log_path)
        assert "Line three" in _read(log_path)


# ---------------------------------------------------------------------------
# 9. No tools → no tool section
# ---------------------------------------------------------------------------

class TestNoToolSection:
    def test_no_tools_section_when_tools_empty(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("Just a question", tool_logs=[], log_path=log_path)
        content = _read(log_path)
        assert "🛠" not in content
        assert "Tool" not in content

    def test_no_tools_section_when_tools_none(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_turn("Just a question", tool_logs=None, log_path=log_path)
        content = _read(log_path)
        assert "🛠" not in content


# ---------------------------------------------------------------------------
# 10. Tool section present when tools used
# ---------------------------------------------------------------------------

class TestToolSectionPresent:
    def test_tool_section_header_appears(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{"name": "read_file", "args": {"filepath": "data/notes.md"}, "result": {"content": "...some content..."}}]
        log_turn("Read something", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "🛠" in content

    def test_tool_name_appears(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{"name": "edit_file", "args": {"filepath": "data/hinges.md", "search_text": "old", "replace_text": "new"}, "result": {"success": "ok"}}]
        log_turn("Edit something", tool_logs=tool_logs, log_path=log_path)
        assert "edit_file" in _read(log_path)

    def test_file_path_appears_in_tool_output(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{"name": "read_file", "args": {"filepath": "data/hinges.md"}, "result": {"content": "text"}}]
        log_turn("Read hinges", tool_logs=tool_logs, log_path=log_path)
        assert "data/hinges.md" in _read(log_path)


# ---------------------------------------------------------------------------
# 11. edit_file → diff rendering
# ---------------------------------------------------------------------------

class TestEditFileDiff:
    def test_removed_lines_shown_with_minus(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "edit_file",
            "args": {
                "filepath": "data/hinges.md",
                "search_text": "Zawiasy standardowe",
                "replace_text": "Zawiasy Blum Clip Top",
            },
            "result": {"success": "Updated"},
        }]
        log_turn("Update hinges", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "- Zawiasy standardowe" in content

    def test_added_lines_shown_with_plus(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "edit_file",
            "args": {
                "filepath": "data/hinges.md",
                "search_text": "Zawiasy standardowe",
                "replace_text": "Zawiasy Blum Clip Top",
            },
            "result": {"success": "Updated"},
        }]
        log_turn("Update hinges", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "+ Zawiasy Blum Clip Top" in content

    def test_multiline_diff_each_line_prefixed(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "edit_file",
            "args": {
                "filepath": "data/notes.md",
                "search_text": "old line A\nold line B",
                "replace_text": "new line A\nnew line B",
            },
            "result": {"success": "Updated"},
        }]
        log_turn("Multi-line edit", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "- old line A" in content
        assert "- old line B" in content
        assert "+ new line A" in content
        assert "+ new line B" in content

    def test_edit_error_result_shown(self, tmp_path: Path) -> None:
        """When edit fails, the error is shown — not a diff."""
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "edit_file",
            "args": {
                "filepath": "data/notes.md",
                "search_text": "missing text",
                "replace_text": "whatever",
            },
            "result": {"error": "Search text not found in file."},
        }]
        log_turn("Failed edit", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "Search text not found" in content


# ---------------------------------------------------------------------------
# 12. create_file → content shown with + prefix
# ---------------------------------------------------------------------------

class TestCreateFileDiff:
    def test_created_file_lines_have_plus_prefix(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "create_file",
            "args": {
                "filepath": "data/new_topic.md",
                "content": "# New Topic\n\nSome content here.",
            },
            "result": {"success": "Created"},
        }]
        log_turn("Create file", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "data/new_topic.md" in content
        assert "+ # New Topic" in content
        assert "+ Some content here." in content

    def test_create_file_error_shown(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "create_file",
            "args": {"filepath": "data/existing.md", "content": "x"},
            "result": {"error": "File already exists at data/existing.md. Use edit_file instead."},
        }]
        log_turn("Create existing", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "File already exists" in content


# ---------------------------------------------------------------------------
# 13. read_file → 📖 Read, no diff
# ---------------------------------------------------------------------------

class TestReadFileTool:
    def test_read_file_shows_read_emoji(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "read_file",
            "args": {"filepath": "data/hinges.md"},
            "result": {"content": "lots of content"},
        }]
        log_turn("Read hinges", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "📖" in content

    def test_read_file_does_not_dump_content(self, tmp_path: Path) -> None:
        """File content body must NOT appear — only the path."""
        log_path = _make_log(tmp_path)
        secret_content = "SECRET_INTERNAL_CONTENT_XYZ"
        tool_logs = [{
            "name": "read_file",
            "args": {"filepath": "data/notes.md"},
            "result": {"content": secret_content},
        }]
        log_turn("Read notes", tool_logs=tool_logs, log_path=log_path)
        assert secret_content not in _read(log_path)


# ---------------------------------------------------------------------------
# 14. search_knowledge_base → 🔍 Searched
# ---------------------------------------------------------------------------

class TestSearchTool:
    def test_search_shows_magnifier_emoji(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "search_knowledge_base",
            "args": {"query": "Blum|hinge"},
            "result": {"content": "found 5 lines"},
        }]
        log_turn("Search for blum", tool_logs=tool_logs, log_path=log_path)
        assert "🔍" in _read(log_path)

    def test_search_query_appears(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "search_knowledge_base",
            "args": {"query": "Blum|hinge"},
            "result": {"content": "found 5 lines"},
        }]
        log_turn("Search for blum", tool_logs=tool_logs, log_path=log_path)
        assert "Blum|hinge" in _read(log_path)


# ---------------------------------------------------------------------------
# 15. get_repo_map → 🗺 Repo map scanned
# ---------------------------------------------------------------------------

class TestRepoMapTool:
    def test_repo_map_shows_map_emoji(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "get_repo_map",
            "args": {},
            "result": {"content": "## file1.md\n- header"},
        }]
        log_turn("What files do we have?", tool_logs=tool_logs, log_path=log_path)
        assert "🗺" in _read(log_path)

    def test_repo_map_no_args_dumped(self, tmp_path: Path) -> None:
        """get_repo_map takes no args — nothing verbose should appear."""
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "get_repo_map",
            "args": {},
            "result": {"content": "map content"},
        }]
        log_turn("List files", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "map content" not in content  # result body not dumped


# ---------------------------------------------------------------------------
# 16. Unknown tool → raw result snippet
# ---------------------------------------------------------------------------

class TestUnknownTool:
    def test_unknown_tool_recorded(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "some_future_tool",
            "args": {"key": "value"},
            "result": {"data": "something"},
        }]
        log_turn("Use unknown tool", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "some_future_tool" in content

    def test_unknown_tool_shows_result_snippet(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [{
            "name": "magic_tool",
            "args": {},
            "result": {"data": "unique_result_xyz"},
        }]
        log_turn("Magic", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "unique_result_xyz" in content


# ---------------------------------------------------------------------------
# 17. Multiple tool calls in one turn
# ---------------------------------------------------------------------------

class TestMultipleTools:
    def test_all_tools_appear_when_multiple_calls(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [
            {"name": "get_repo_map", "args": {}, "result": {"content": "map"}},
            {"name": "read_file", "args": {"filepath": "data/a.md"}, "result": {"content": "abc"}},
            {
                "name": "edit_file",
                "args": {"filepath": "data/a.md", "search_text": "old", "replace_text": "new"},
                "result": {"success": "ok"},
            },
        ]
        log_turn("Three tools", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "🗺" in content
        assert "📖" in content
        assert "data/a.md" in content
        assert "- old" in content
        assert "+ new" in content

    def test_tools_appear_in_call_order(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        tool_logs = [
            {"name": "get_repo_map", "args": {}, "result": {"content": "map"}},
            {"name": "read_file", "args": {"filepath": "data/first.md"}, "result": {"content": "x"}},
        ]
        log_turn("Order test", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert content.index("🗺") < content.index("data/first.md")


# ---------------------------------------------------------------------------
# 18. Diff truncation
# ---------------------------------------------------------------------------

class TestDiffTruncation:
    def test_long_create_content_truncated(self, tmp_path: Path) -> None:
        """Content with more than MAX_DIFF_LINES lines gets a truncation notice."""
        log_path = _make_log(tmp_path)
        many_lines = "\n".join(f"line {i}" for i in range(MAX_DIFF_LINES + 10))
        tool_logs = [{
            "name": "create_file",
            "args": {"filepath": "data/big.md", "content": many_lines},
            "result": {"success": "Created"},
        }]
        log_turn("Big file", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "truncated" in content.lower() or "…" in content

    def test_long_edit_diff_truncated(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        big_old = "\n".join(f"old line {i}" for i in range(MAX_DIFF_LINES + 5))
        big_new = "\n".join(f"new line {i}" for i in range(MAX_DIFF_LINES + 5))
        tool_logs = [{
            "name": "edit_file",
            "args": {"filepath": "data/big.md", "search_text": big_old, "replace_text": big_new},
            "result": {"success": "ok"},
        }]
        log_turn("Big edit", tool_logs=tool_logs, log_path=log_path)
        content = _read(log_path)
        assert "truncated" in content.lower() or "…" in content


# ---------------------------------------------------------------------------
# 19. Default log path from settings
# ---------------------------------------------------------------------------

class TestDefaultLogPath:
    def test_uses_settings_prompt_log_path_when_no_override(self, tmp_path: Path, monkeypatch) -> None:
        """
        When log_path=None, falls back to settings.prompt_log_path.

        prompt_log_path is a @property derived from data_dir, so we patch
        data_dir on the settings singleton to redirect the default path into
        tmp_path without needing a property setter.
        """
        from src import prompt_logger
        monkeypatch.setattr(prompt_logger.settings, "data_dir", tmp_path)
        log_turn("Default path test")
        expected = tmp_path / "prompt_log.md"
        assert expected.exists()
        assert "Default path test" in expected.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 20. Backward-compat: log_prompt() still works
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_log_prompt_delegates_to_log_turn(self, tmp_path: Path) -> None:
        """log_prompt(prompt) must still write a valid entry."""
        log_path = _make_log(tmp_path)
        log_prompt("Legacy prompt text", log_path=log_path)
        content = _read(log_path)
        assert "Legacy prompt text" in content

    def test_log_prompt_ignores_empty(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_prompt("  ", log_path=log_path)
        assert not log_path.exists()

    def test_log_prompt_creates_file(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_prompt("Hello legacy", log_path=log_path)
        assert log_path.exists()

    def test_log_prompt_appends(self, tmp_path: Path) -> None:
        log_path = _make_log(tmp_path)
        log_prompt("ONE", log_path=log_path)
        log_prompt("TWO", log_path=log_path)
        content = _read(log_path)
        assert "ONE" in content and "TWO" in content


# ---------------------------------------------------------------------------
# 21. Integration — ChatService wires log_turn with tool data
# ---------------------------------------------------------------------------

class TestChatServiceIntegration:
    """
    Verifies that ChatService calls log_turn (not bare log_prompt) and that
    the tool_logs produced by the agent are forwarded into it.
    """

    def test_chat_service_calls_log_turn_with_tool_logs(self, tmp_path: Path) -> None:
        from src.chat_service import ChatService
        from src.agent.turn_orchestrator import TurnInput
        from src.repositories import SQLiteConnection, SQLiteSessionRepository
        from src.agent.turn_orchestrator import ToolCallDetail

        conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
        repo = SQLiteSessionRepository(conn)

        fake_tool_details = [
            ToolCallDetail(
                id="call_1",
                name="edit_file",
                arguments={
                    "filepath": "data/hinges.md",
                    "search_text": "old text",
                    "replace_text": "new text",
                },
                result_content="{'success': 'Updated data/hinges.md.'}",
                is_error=False,
            )
        ]
        orchestrator = FakeOrchestrator(
            text="Agent reply",
            tool_details=fake_tool_details,
        )
        service = ChatService(
            session_repo=repo,
            turn_orchestrator=orchestrator,
        )

        with patch("src.chat_service.log_turn") as mock_log:
            service.handle_turn(TurnInput(
                session_id="session-xyz",
                user_message="Popraw zawiasy",
            ))

            assert mock_log.called
            call_kwargs = mock_log.call_args
            # Either positional or keyword
            args, kwargs = call_kwargs
            passed_tool_logs = kwargs.get("tool_logs") or (args[1] if len(args) > 1 else None)
            assert len(passed_tool_logs) == 1
            assert passed_tool_logs[0]["name"] == "edit_file"

    def test_chat_service_passes_session_id_to_log_turn(self, tmp_path: Path) -> None:
        from src.chat_service import ChatService
        from src.agent.turn_orchestrator import TurnInput
        from src.repositories import SQLiteConnection, SQLiteSessionRepository

        conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
        repo = SQLiteSessionRepository(conn)
        orchestrator = FakeOrchestrator(text="Reply")
        service = ChatService(
            session_repo=repo,
            turn_orchestrator=orchestrator,
        )

        with patch("src.chat_service.log_turn") as mock_log:
            service.handle_turn(TurnInput(
                session_id="my-special-session",
                user_message="What materials?",
            ))

            args, kwargs = mock_log.call_args
            sid = kwargs.get("session_id") or (args[2] if len(args) > 2 else None)
            assert sid == "my-special-session"
