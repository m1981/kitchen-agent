"""
tests/test_coverage_gaps.py
============================
Targeted tests that close remaining coverage gaps.

Coverage targets
----------------
src/logger.py            line 27  — setup_logging(is_local_dev=False) JSON path
src/main.py              lines 88, 176-182, 191-196  — _resolve_context_file_paths
                         lines 633-634, 643           — revert route exception paths
src/serializers.py       — dehydrate with turn_id on all item types
src/tools/file_ops.py    lines 132-133 — revert_backup backup-file unlink OSError (best-effort)
src/message_editor.py    — edit_message api sync, truncate validation
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from google.genai import types

from src.logger import setup_logging
from src.message_editor import EditError, MessageEditService
from src.repositories import SQLiteConnection, SQLiteSessionRepository
from src.serializers import dehydrate_history, hydrate_history
from src.tools.file_ops import _create_backup, revert_backup


# ===========================================================================
# 1. logger.py — JSON renderer path (is_local_dev=False)  [line 27]
# ===========================================================================

class TestSetupLoggingJsonPath:
    def test_setup_logging_json_mode_does_not_raise(self):
        """Calling setup_logging(is_local_dev=False) must not raise."""
        setup_logging(is_local_dev=False)

    def test_setup_logging_local_dev_does_not_raise(self):
        """Calling setup_logging(is_local_dev=True) must not raise."""
        setup_logging(is_local_dev=True)

    def test_setup_logging_sets_info_level(self):
        """Root logger level must be WARNING or lower after setup."""
        setup_logging(is_local_dev=True)
        assert logging.getLogger().level <= logging.WARNING


# ===========================================================================
# 3. main.py — _resolve_context_file_paths branches  [lines 176-196]
# ===========================================================================

class TestResolveContextFilePaths:
    """Test _resolve_context_file_paths via the public HTTP API."""

    @pytest.fixture(autouse=True)
    def _client(self, tmp_path):
        from src.main import app
        from src.dependencies import get_session_repo, get_prompt_manager
        from src.repositories import SQLiteConnection, SQLiteSessionRepository
        from src.prompt_manager import PromptManager

        db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
        repo = SQLiteSessionRepository(db)

        pm = MagicMock(spec=PromptManager)
        pm.get_system_instruction.return_value = "test instruction"

        app.dependency_overrides[get_session_repo] = lambda: repo
        app.dependency_overrides[get_prompt_manager] = lambda: pm
        self.client = TestClient(app)
        self.tmp_path = tmp_path
        yield
        app.dependency_overrides.clear()

    def test_none_context_files_returns_none(self):
        from src.api.chat import _resolve_context_file_paths
        assert _resolve_context_file_paths(None) is None

    def test_empty_list_returns_none(self):
        from src.api.chat import _resolve_context_file_paths
        assert _resolve_context_file_paths([]) is None

    def test_relative_path_resolved_to_data_dir(self, tmp_path):
        from src.api.chat import _resolve_context_file_paths
        from src import config as cfg_module

        original = cfg_module.settings.data_dir
        cfg_module.settings.data_dir = tmp_path
        try:
            (tmp_path / "file.md").write_text("hi")
            result = _resolve_context_file_paths(["file.md"])
            assert result is not None
            assert len(result) == 1
            assert result[0].endswith("file.md")
        finally:
            cfg_module.settings.data_dir = original

    def test_absolute_path_inside_data_dir_accepted(self, tmp_path):
        from src.api.chat import _resolve_context_file_paths
        from src import config as cfg_module

        original = cfg_module.settings.data_dir
        cfg_module.settings.data_dir = tmp_path
        try:
            fp = tmp_path / "abs.md"
            fp.write_text("content")
            result = _resolve_context_file_paths([str(fp)])
            assert result is not None
            assert str(fp) in result
        finally:
            cfg_module.settings.data_dir = original

    def test_absolute_path_outside_data_dir_dropped(self, tmp_path):
        from src.api.chat import _resolve_context_file_paths
        from src import config as cfg_module

        sub = tmp_path / "sub"
        sub.mkdir()
        original = cfg_module.settings.data_dir
        cfg_module.settings.data_dir = sub
        try:
            result = _resolve_context_file_paths([str(tmp_path)])
            assert result is None
        finally:
            cfg_module.settings.data_dir = original

    def test_relative_path_traversal_dropped(self, tmp_path):
        from src.api.chat import _resolve_context_file_paths
        from src import config as cfg_module

        sub = tmp_path / "sub"
        sub.mkdir()
        original = cfg_module.settings.data_dir
        cfg_module.settings.data_dir = sub
        try:
            result = _resolve_context_file_paths(["../escape.md"])
            assert result is None
        finally:
            cfg_module.settings.data_dir = original

    def test_mixed_valid_and_invalid_paths(self, tmp_path):
        from src.api.chat import _resolve_context_file_paths
        from src import config as cfg_module

        original = cfg_module.settings.data_dir
        cfg_module.settings.data_dir = tmp_path
        try:
            (tmp_path / "good.md").write_text("ok")
            result = _resolve_context_file_paths(["good.md", "../bad.md"])
            assert result is not None
            assert len(result) == 1
            assert result[0].endswith("good.md")
        finally:
            cfg_module.settings.data_dir = original


# ===========================================================================
# 4. main.py — revert route exception path  [lines 633-634, 643]
# ===========================================================================

class TestRevertRouteExceptionPath:
    @pytest.fixture
    def client(self, tmp_path):
        from src.main import app
        from src.dependencies import get_session_repo
        from src.repositories import SQLiteConnection, SQLiteSessionRepository

        db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
        repo = SQLiteSessionRepository(db)
        app.dependency_overrides[get_session_repo] = lambda: repo
        yield TestClient(app), tmp_path
        app.dependency_overrides.clear()

    def test_revert_with_missing_backup_returns_404(self, client):
        tc, tmp_path = client
        response = tc.post("/api/files/revert/nonexistent-uuid")
        assert response.status_code == 404
        assert "backup" in response.json()["detail"].lower() or "reverted" in response.json()["detail"].lower()

    def test_revert_path_traversal_returns_400(self, client):
        tc, tmp_path = client
        response = tc.post("/api/files/revert/../../../etc/passwd")
        assert response.status_code in (400, 404, 422)


# ===========================================================================
# 5. message_editor.py — delete_pair validation
# ===========================================================================

class TestDeletePairValidation:
    @pytest.fixture
    def repo(self, tmp_path):
        db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
        return SQLiteSessionRepository(db)

    def test_delete_pair_false_leaves_next_message(self, repo):
        """delete_pair=False must NOT remove the adjacent message."""
        session_id = "sess-no-pair"
        ui_messages = [
            {"role": "user", "content": "Q", "turn_id": "uid-u"},
            {"role": "assistant", "content": "A", "turn_id": "uid-a"},
        ]
        api_items = [
            {"role": "user", "type": "text", "data": "Q", "turn_id": "uid-u"},
            {"role": "model", "type": "text", "data": "A", "turn_id": "uid-a"},
        ]
        repo.save_session(
            session_id=session_id,
            title="No Pair",
            api_history_json=json.dumps(api_items),
            ui_history_json=json.dumps(ui_messages),
        )

        svc = MessageEditService(repo)
        svc.delete_message(session_id, turn_id="uid-u", delete_pair=False)

        _, ui_json, _ = repo.load_session(session_id)
        remaining_ui = json.loads(ui_json)
        assert len(remaining_ui) == 1
        assert remaining_ui[0]["turn_id"] == "uid-a"


# ===========================================================================
# 6. message_editor.py — truncate validation
# ===========================================================================

class TestTruncateValidation:
    @pytest.fixture
    def repo(self, tmp_path):
        db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
        return SQLiteSessionRepository(db)

    def test_truncate_n_exceeds_pairs_raises(self, repo):
        """n > available pairs must raise EditError."""
        session_id = "sess-too-many"
        ui_messages = [
            {"role": "user", "content": "Q", "turn_id": "u1"},
            {"role": "assistant", "content": "A", "turn_id": "a1"},
        ]
        repo.save_session(
            session_id=session_id,
            title="Too Many",
            api_history_json=json.dumps([]),
            ui_history_json=json.dumps(ui_messages),
        )
        svc = MessageEditService(repo)
        with pytest.raises(EditError, match="exceeds"):
            svc.truncate_turns(session_id, n=5)


# ===========================================================================
# 7. serializers.py — turn_id stamped on all item types
# ===========================================================================

class TestDehydrateWithTurnIds:
    """Verify turn_id is stored on every serialised item type."""

    def test_turn_id_on_text_item(self):
        history = [types.Content(role="user", parts=[types.Part(text="hello")])]
        result = json.loads(dehydrate_history(history, turn_ids=["tid-text"]))
        assert result[0]["turn_id"] == "tid-text"
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hello"

    def test_turn_id_on_function_call_item(self):
        fc = types.FunctionCall(name="read_file", args={"filepath": "x.md"}, id="c1")
        history = [types.Content(role="model", parts=[types.Part(function_call=fc)])]
        result = json.loads(dehydrate_history(history, turn_ids=["tid-fc"]))
        assert result[0]["turn_id"] == "tid-fc"
        assert result[0]["role"] == "assistant"
        assert result[0]["tool_calls"][0]["name"] == "read_file"

    def test_turn_id_on_function_response_item(self):
        fr = types.FunctionResponse(name="read_file", response={"content": "ok"}, id="c1")
        history = [types.Content(role="user", parts=[types.Part(function_response=fr)])]
        result = json.loads(dehydrate_history(history, turn_ids=["tid-fr"]))
        assert result[0]["turn_id"] == "tid-fr"
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "c1"

    def test_turn_id_generated_when_list_is_none(self):
        """Without turn_ids list, items get generated UUIDs."""
        history = [types.Content(role="user", parts=[types.Part(text="x")])]
        result = json.loads(dehydrate_history(history, turn_ids=None))
        assert "turn_id" in result[0]
        assert len(result[0]["turn_id"]) == 36

    def test_mixed_turn_ids_per_item(self):
        """Each item gets its own turn_id from the parallel list."""
        history = [
            types.Content(role="user", parts=[types.Part(text="u")]),
            types.Content(role="model", parts=[types.Part(text="a")]),
        ]
        result = json.loads(dehydrate_history(history, turn_ids=["uid", "aid"]))
        assert result[0]["turn_id"] == "uid"
        assert result[1]["turn_id"] == "aid"

    def test_round_trip_preserves_turn_id_in_api_items(self):
        """After dehydrate → re-parse, turn_id survives as a plain string field."""
        history = [types.Content(role="user", parts=[types.Part(text="hello")])]
        raw = dehydrate_history(history, turn_ids=["stable-id"])
        items = json.loads(raw)
        assert items[0]["turn_id"] == "stable-id"
        restored = hydrate_history(raw)
        assert len(restored) == 1
        assert restored[0]["role"] == "user"
        assert restored[0]["content"] == "hello"
        assert restored[0]["turn_id"] == "stable-id"


# ===========================================================================
# 8. tools/file_ops.py — revert_backup OSError cleanup best-effort  [lines 132-133]
# ===========================================================================

class TestRevertBackupCleanup:
    def test_cleanup_oserror_is_swallowed(self, tmp_path):
        """If backup_file.unlink() raises OSError during cleanup, the error must
        be silently swallowed and the function must still return success."""
        target = tmp_path / "file.md"
        target.write_text("original", encoding="utf-8")
        revert_id = _create_backup(target, backup_dir=tmp_path)

        backup_path = tmp_path / ".backups" / f"{revert_id}.json"

        original_unlink = Path.unlink

        call_count = [0]

        def _patched_unlink(self, missing_ok=False):
            call_count[0] += 1
            if self == backup_path and call_count[0] > 1:
                raise OSError("simulated cleanup failure")
            return original_unlink(self, missing_ok=missing_ok)

        with patch.object(Path, "unlink", _patched_unlink):
            result = revert_backup(revert_id, backup_dir=tmp_path)

        assert result.get("success") is True
        assert "Reverted" in result.get("message", "")

    def test_revert_backup_file_not_found_returns_error(self, tmp_path):
        """Unknown revert_id must return an error dict, not raise."""
        result = revert_backup("does-not-exist", backup_dir=tmp_path)
        assert "error" in result

    def test_revert_backup_restores_content(self, tmp_path):
        """revert_backup must write original content back to the target file."""
        target = tmp_path / "data.md"
        target.write_text("original content", encoding="utf-8")
        rid = _create_backup(target, backup_dir=tmp_path)

        target.write_text("mutated content", encoding="utf-8")

        result = revert_backup(rid, backup_dir=tmp_path)
        assert result.get("success") is True
        assert target.read_text() == "original content"

    def test_revert_backup_for_created_file_deletes_it(self, tmp_path):
        """When a file was created by the agent, revert must delete the file."""
        target = tmp_path / "new_file.md"
        rid = _create_backup(target, backup_dir=tmp_path)

        target.write_text("agent-created content", encoding="utf-8")
        assert target.exists()

        result = revert_backup(rid, backup_dir=tmp_path)
        assert result.get("success") is True
        assert not target.exists()

    def test_revert_backup_malformed_json_returns_error(self, tmp_path):
        """Malformed backup JSON must produce an error dict."""
        backup_folder = tmp_path / ".backups"
        backup_folder.mkdir(parents=True, exist_ok=True)
        bad_id = "malformed-uuid"
        (backup_folder / f"{bad_id}.json").write_text("NOT JSON", encoding="utf-8")
        result = revert_backup(bad_id, backup_dir=tmp_path)
        assert "error" in result


# ===========================================================================
# 9. Additional message_editor branches — edit_message api sync
# ===========================================================================

class TestEditMessageApiSync:
    @pytest.fixture
    def repo(self, tmp_path):
        db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
        return SQLiteSessionRepository(db)

    def test_edit_message_updates_api_text_item(self, repo):
        """edit_message must update the matching api text item's 'data' field."""
        session_id = "sess-edit-api"
        ui_messages = [{"role": "user", "content": "old", "turn_id": "t1"}]
        api_items = [{"role": "user", "type": "text", "data": "old", "turn_id": "t1"}]
        repo.save_session(
            session_id=session_id,
            title="Edit API",
            api_history_json=json.dumps(api_items),
            ui_history_json=json.dumps(ui_messages),
        )

        svc = MessageEditService(repo)
        svc.edit_message(session_id, turn_id="t1", new_content="new content")

        api_json, ui_json, _ = repo.load_session(session_id)
        api_after = json.loads(api_json)
        ui_after = json.loads(ui_json)

        assert api_after[0]["data"] == "new content"
        assert ui_after[0]["content"] == "new content"

    def test_edit_message_skips_non_text_api_items(self, repo):
        """edit_message must NOT modify function_call items, only text ones."""
        session_id = "sess-edit-fc"
        ui_messages = [{"role": "user", "content": "old text", "turn_id": "t-fc"}]
        api_items = [
            {"role": "model", "type": "function_call", "name": "read_file",
             "args": {}, "id": "c1", "turn_id": "t-fc"},
            {"role": "user", "type": "text", "data": "old text", "turn_id": "t-fc"},
        ]
        repo.save_session(
            session_id=session_id,
            title="FC Edit",
            api_history_json=json.dumps(api_items),
            ui_history_json=json.dumps(ui_messages),
        )

        svc = MessageEditService(repo)
        svc.edit_message(session_id, turn_id="t-fc", new_content="new text")

        api_json, _, _ = repo.load_session(session_id)
        api_after = json.loads(api_json)
        fc_item = next(i for i in api_after if i["type"] == "function_call")
        text_item = next(i for i in api_after if i["type"] == "text")

        assert fc_item["name"] == "read_file"   # unchanged
        assert text_item["data"] == "new text"  # updated

    def test_edit_message_empty_content_raises(self, repo):
        """Empty / blank new_content must raise EditError immediately."""
        session_id = "sess-blank"
        repo.save_session(
            session_id=session_id,
            title="Blank",
            api_history_json="[]",
            ui_history_json="[]",
        )
        svc = MessageEditService(repo)
        with pytest.raises(EditError, match="empty or blank"):
            svc.edit_message(session_id, turn_id="t1", new_content="   ")

    def test_edit_message_unknown_turn_id_raises(self, repo):
        """An unknown turn_id must raise EditError."""
        session_id = "sess-unknown"
        ui_messages = [{"role": "user", "content": "hi", "turn_id": "real-id"}]
        repo.save_session(
            session_id=session_id,
            title="Unknown",
            api_history_json="[]",
            ui_history_json=json.dumps(ui_messages),
        )
        svc = MessageEditService(repo)
        with pytest.raises(EditError, match="No message found"):
            svc.edit_message(session_id, turn_id="wrong-id", new_content="anything")


# ===========================================================================
# Logger configuration
# ===========================================================================

class TestLoggerConfiguration:
    def test_setup_logging_local_dev_does_not_raise(self):
        """setup_logging(is_local_dev=True) must not raise."""
        from src.logger import setup_logging
        setup_logging(is_local_dev=True)

    def test_setup_logging_production_does_not_raise(self):
        """setup_logging(is_local_dev=False) must not raise."""
        from src.logger import setup_logging
        setup_logging(is_local_dev=False)

    def test_bind_and_clear_request_context(self):
        """bind_request_context and clear_request_context must not raise."""
        from src.logger import bind_request_context, clear_request_context
        bind_request_context(session_id="test", provider="gemini")
        clear_request_context()

    def test_log_timing_context_manager(self):
        """log_timing context manager must measure duration."""
        import structlog
        from src.logger import log_timing

        log = structlog.get_logger("test")
        with log_timing(log, "test_event", extra_key="value") as timing:
            pass  # instant operation

        assert "duration_ms" in timing
        assert timing["extra_key"] == "value"
        assert timing["duration_ms"] >= 0

    def test_log_timing_records_actual_duration(self):
        """log_timing must record non-zero duration for slow operations."""
        import time
        import structlog
        from src.logger import log_timing

        log = structlog.get_logger("test")
        with log_timing(log, "slow_event") as timing:
            time.sleep(0.01)  # 10ms

        assert timing["duration_ms"] >= 5  # at least 5ms
