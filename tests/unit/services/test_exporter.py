"""
tests/test_exporter.py
======================
TDD suite for Markdown export of chat sessions.

Covers:
 - Pure rendering function (all branches)
 - DatabaseManager integration (export_session)
 - Unknown-role fallback rendering (line 50)
"""
import json
from pathlib import Path

import pytest

from src.export_service import ExportService
from src.exporter import export_session_to_markdown, _render_message
from src.repositories import SQLiteConnection, SQLiteSessionRepository


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------

def test_export_empty_session_has_title_only() -> None:
    result = export_session_to_markdown([], "Empty Chat")
    assert result.startswith("# Empty Chat")
    assert "## User" not in result
    assert "## Assistant" not in result


def test_export_single_user_turn() -> None:
    ui_messages = [{"role": "user", "content": "Hello there"}]
    result = export_session_to_markdown(ui_messages, "Greeting")
    assert "# Greeting" in result
    assert "## User" in result
    assert "Hello there" in result


def test_export_full_user_assistant_exchange() -> None:
    ui_messages = [
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "4", "tools": []},
    ]
    result = export_session_to_markdown(ui_messages, "Math")
    assert "## User" in result
    assert "What is 2+2?" in result
    assert "## Assistant" in result
    assert "\n4" in result


def test_export_renders_tool_calls_as_details_blocks() -> None:
    ui_messages = [
        {"role": "user", "content": "Read foo.md"},
        {
            "role": "assistant",
            "content": "Here is the file.",
            "tools": [
                {
                    "name": "read_file",
                    "args": {"filepath": "foo.md"},
                    "result": {"content": "# Foo"},
                }
            ],
        },
    ]
    result = export_session_to_markdown(ui_messages, "File Read")
    assert "<details>" in result
    assert "</details>" in result
    assert "read_file" in result
    assert "foo.md" in result
    assert "# Foo" in result


def test_export_preserves_turn_order() -> None:
    ui_messages = [
        {"role": "user", "content": "FIRST_USER_MSG"},
        {"role": "assistant", "content": "FIRST_ASSISTANT_MSG", "tools": []},
        {"role": "user", "content": "SECOND_USER_MSG"},
        {"role": "assistant", "content": "SECOND_ASSISTANT_MSG", "tools": []},
    ]
    result = export_session_to_markdown(ui_messages, "Ordered")
    positions = [
        result.index("FIRST_USER_MSG"),
        result.index("FIRST_ASSISTANT_MSG"),
        result.index("SECOND_USER_MSG"),
        result.index("SECOND_ASSISTANT_MSG"),
    ]
    assert positions == sorted(positions)


def test_export_special_markdown_chars_preserved() -> None:
    content = "Here is `code`, **bold**, and a [link](http://x.test)."
    ui_messages = [{"role": "user", "content": content}]
    result = export_session_to_markdown(ui_messages, "Markdown")
    assert content in result


def test_export_handles_missing_tools_key() -> None:
    ui_messages = [{"role": "assistant", "content": "No tools here"}]
    result = export_session_to_markdown(ui_messages, "Toolless")
    assert "## Assistant" in result
    assert "No tools here" in result
    assert "<details>" not in result


def test_export_falls_back_for_empty_title() -> None:
    result = export_session_to_markdown([], "   ")
    assert "# Untitled Session" in result


# ---------------------------------------------------------------------------
# Unknown role fallback
# ---------------------------------------------------------------------------

def test_render_message_unknown_role() -> None:
    """A message with an unrecognised role falls back to '## <Role>'."""
    msg = {"role": "system", "content": "You are a bot."}
    output = _render_message(msg)
    assert output.startswith("## System")
    assert "You are a bot." in output


# ---------------------------------------------------------------------------
# Repository integration tests
# ---------------------------------------------------------------------------

def _seed(repo: SQLiteSessionRepository) -> str:
    session_id = "exp-session-1"
    ui_messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi back", "tools": []},
    ]
    repo.save_session(
        session_id=session_id,
        title="Export Test",
        api_history_json="[]",
        ui_history_json=json.dumps(ui_messages),
    )
    return session_id


def test_db_export_session_returns_markdown(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    session_id = _seed(repo)
    svc = ExportService(repo)
    result = svc.export_markdown(session_id)
    assert isinstance(result, str)
    assert "# Export Test" in result
    assert "## User" in result
    assert "Hello" in result
    assert "## Assistant" in result
    assert "Hi back" in result


def test_db_export_nonexistent_session_raises(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    with pytest.raises(ValueError):
        ExportService(repo).export_markdown("does-not-exist")


def test_db_export_empty_session(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    repo.save_session(
        session_id="empty-1",
        title="Empty One",
        api_history_json="[]",
        ui_history_json="[]",
    )
    svc = ExportService(repo)
    result = svc.export_markdown("empty-1")
    assert "# Empty One" in result
