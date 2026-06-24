"""
tests/test_backup_file_ops.py
==============================
Unit tests for the backup/snapshot helpers added to file_ops.py.

TDD — Written BEFORE the implementation.

Covers:
  _create_backup():
    - creates .backups/ dir inside backup_dir
    - records filepath, existed=True, and original content for existing file
    - records filepath, existed=False, content=None for a new (non-existent) file
    - returns a valid UUID string each call
    - each call produces a unique revert_id

  revert_backup():
    - restores content of an existing file that was edited
    - deletes a file that was created (existed=False before the edit)
    - deletes the backup JSON after a successful revert (no double-revert)
    - returns {"success": True, "message": ...} on success
    - returns {"error": ...} when revert_id not found (no such .json)
    - returns {"error": ...} when backup JSON is malformed / invalid
    - does NOT delete the backup file on error (preserves recovery data)

  edit_file() with backup:
    - returns "revert_id" key in success result
    - revert_id is a valid non-empty string
    - backup JSON captures correct original content

  create_file() with backup:
    - returns "revert_id" key in success result
    - backup JSON records existed=False

  append_to_file() with backup:
    - returns "revert_id" key in success result
    - backup JSON records existed=True when file pre-existed
    - backup JSON records existed=False when file did not exist (auto-create)
"""

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from src.tools.file_ops import (
    _create_backup,
    revert_backup,
    edit_file,
    create_file,
    append_to_file,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _read_backup(backup_dir: Path, revert_id: str) -> dict:
    backup_file = backup_dir / ".backups" / f"{revert_id}.json"
    return json.loads(backup_file.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────────────────────────────────────
# _create_backup — unit tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCreateBackup:

    def test_creates_backups_dir(self, tmp_path: Path) -> None:
        """The hidden .backups/ directory must be created automatically."""
        target = tmp_path / "notes.md"
        target.write_text("original", encoding="utf-8")

        _create_backup(target_path=target, backup_dir=tmp_path)

        assert (tmp_path / ".backups").is_dir()

    def test_returns_valid_uuid_string(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.md"
        target.write_text("original", encoding="utf-8")

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)

        assert isinstance(revert_id, str)
        assert _is_valid_uuid(revert_id)

    def test_each_call_returns_unique_id(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.md"
        target.write_text("content", encoding="utf-8")

        id1 = _create_backup(target_path=target, backup_dir=tmp_path)
        id2 = _create_backup(target_path=target, backup_dir=tmp_path)

        assert id1 != id2

    def test_backup_records_existing_file_content(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.md"
        original = "# Kitchen Notes\n\nUse 18mm plywood.\n"
        target.write_text(original, encoding="utf-8")

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)
        state = _read_backup(tmp_path, revert_id)

        assert state["existed"] is True
        assert state["content"] == original

    def test_backup_records_filepath(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.md"
        target.write_text("content", encoding="utf-8")

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)
        state = _read_backup(tmp_path, revert_id)

        # Stored path must be a posix string — platform-independent
        assert isinstance(state["filepath"], str)
        assert "notes.md" in state["filepath"]

    def test_backup_for_non_existent_file(self, tmp_path: Path) -> None:
        """When backing up a file that does not yet exist (create_file scenario)."""
        target = tmp_path / "brand_new.md"
        assert not target.exists()

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)
        state = _read_backup(tmp_path, revert_id)

        assert state["existed"] is False
        assert state["content"] is None

    def test_backup_json_file_is_named_by_revert_id(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.md"
        target.write_text("x", encoding="utf-8")

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)

        expected_file = tmp_path / ".backups" / f"{revert_id}.json"
        assert expected_file.exists()


# ──────────────────────────────────────────────────────────────────────────────
# revert_backup — unit tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRevertBackup:

    def test_restores_original_content(self, tmp_path: Path) -> None:
        """Reverting an edit_file operation must restore the original text."""
        target = tmp_path / "notes.md"
        original = "# Original\n\nBlum hinges.\n"
        target.write_text(original, encoding="utf-8")

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)

        # Simulate the edit that happened after backup
        target.write_text("# Modified\n\nCheap hinges.\n", encoding="utf-8")

        result = revert_backup(revert_id=revert_id, backup_dir=tmp_path)

        assert result.get("success") is True
        assert target.read_text(encoding="utf-8") == original

    def test_deletes_created_file_on_revert(self, tmp_path: Path) -> None:
        """If the file did not exist before, reverting must delete it."""
        target = tmp_path / "new_file.md"
        assert not target.exists()

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)

        # Simulate the create_file that happened after backup
        target.write_text("# New file content", encoding="utf-8")

        result = revert_backup(revert_id=revert_id, backup_dir=tmp_path)

        assert result.get("success") is True
        assert not target.exists()

    def test_deletes_backup_file_after_successful_revert(self, tmp_path: Path) -> None:
        """Backup JSON must be cleaned up so double-revert is impossible."""
        target = tmp_path / "notes.md"
        target.write_text("original", encoding="utf-8")

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)
        target.write_text("modified", encoding="utf-8")

        revert_backup(revert_id=revert_id, backup_dir=tmp_path)

        backup_file = tmp_path / ".backups" / f"{revert_id}.json"
        assert not backup_file.exists()

    def test_double_revert_returns_error(self, tmp_path: Path) -> None:
        """After a successful revert, calling revert again must return an error."""
        target = tmp_path / "notes.md"
        target.write_text("original", encoding="utf-8")

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)
        target.write_text("modified", encoding="utf-8")
        revert_backup(revert_id=revert_id, backup_dir=tmp_path)

        # Second call — backup JSON is gone
        result = revert_backup(revert_id=revert_id, backup_dir=tmp_path)

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_returns_error_for_unknown_revert_id(self, tmp_path: Path) -> None:
        """A completely unknown revert_id must return a clear error dict."""
        result = revert_backup(revert_id="nonexistent-id", backup_dir=tmp_path)

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_returns_error_for_malformed_backup_json(self, tmp_path: Path) -> None:
        """Corrupt backup JSON must return an error, not raise an exception."""
        backup_dir = tmp_path / ".backups"
        backup_dir.mkdir(parents=True)
        bad_id = str(uuid.uuid4())
        (backup_dir / f"{bad_id}.json").write_text("NOT_JSON{{{{", encoding="utf-8")

        result = revert_backup(revert_id=bad_id, backup_dir=tmp_path)

        assert "error" in result

    def test_backup_preserved_on_error(self, tmp_path: Path) -> None:
        """When revert fails (e.g. OSError on write), the backup must NOT be deleted."""
        target = tmp_path / "notes.md"
        target.write_text("original", encoding="utf-8")

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)
        target.write_text("modified", encoding="utf-8")

        backup_file = tmp_path / ".backups" / f"{revert_id}.json"
        assert backup_file.exists()

        with patch("src.tools.file_ops.Path.write_text", side_effect=OSError("disk full")):
            result = revert_backup(revert_id=revert_id, backup_dir=tmp_path)

        assert "error" in result
        # Backup file must still be there so user can retry
        assert backup_file.exists()

    def test_revert_success_message_mentions_file(self, tmp_path: Path) -> None:
        """The success message must contain the filename so the UI can display it."""
        target = tmp_path / "materials.md"
        target.write_text("old content", encoding="utf-8")

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)
        target.write_text("new content", encoding="utf-8")

        result = revert_backup(revert_id=revert_id, backup_dir=tmp_path)

        assert result.get("success") is True
        assert "materials.md" in result.get("message", "")

    def test_revert_when_file_was_created_but_already_deleted(self, tmp_path: Path) -> None:
        """
        Edge case: file didn't exist before, was created, then manually deleted.
        Reverting should still succeed (nothing to delete = idempotent success).
        """
        target = tmp_path / "phantom.md"
        assert not target.exists()

        revert_id = _create_backup(target_path=target, backup_dir=tmp_path)
        # The agent created the file...
        target.write_text("content", encoding="utf-8")
        # ...but then it was deleted externally before revert
        target.unlink()

        # Reverting a non-existent "created" file should succeed silently
        result = revert_backup(revert_id=revert_id, backup_dir=tmp_path)

        assert result.get("success") is True


# ──────────────────────────────────────────────────────────────────────────────
# edit_file() — integration with backup
# ──────────────────────────────────────────────────────────────────────────────

class TestEditFileWithBackup:

    def test_edit_file_returns_revert_id(self, tmp_path: Path) -> None:
        """Successful edit_file must include a revert_id in the response."""
        target = tmp_path / "hardware.md"
        target.write_text("standard hinges", encoding="utf-8")

        result = edit_file(
            filepath=str(target),
            search_text="standard hinges",
            replace_text="Blum soft-close hinges",
            backup_dir=tmp_path,
        )

        assert "error" not in result
        assert "revert_id" in result
        assert _is_valid_uuid(result["revert_id"])

    def test_edit_file_revert_id_is_non_empty(self, tmp_path: Path) -> None:
        target = tmp_path / "hardware.md"
        target.write_text("old text", encoding="utf-8")

        result = edit_file(
            filepath=str(target),
            search_text="old text",
            replace_text="new text",
            backup_dir=tmp_path,
        )

        assert result["revert_id"]  # not empty string

    def test_edit_file_backup_captures_original_content(self, tmp_path: Path) -> None:
        """The backup must snapshot the BEFORE state, not the AFTER state."""
        target = tmp_path / "hardware.md"
        original = "Use standard hinges for cabinets."
        target.write_text(original, encoding="utf-8")

        result = edit_file(
            filepath=str(target),
            search_text="standard hinges",
            replace_text="Blum soft-close hinges",
            backup_dir=tmp_path,
        )

        state = _read_backup(tmp_path, result["revert_id"])
        assert state["content"] == original

    def test_edit_file_no_revert_id_on_error(self, tmp_path: Path) -> None:
        """When search_text is not found, no backup is created and no revert_id returned."""
        target = tmp_path / "hardware.md"
        target.write_text("real content", encoding="utf-8")

        result = edit_file(
            filepath=str(target),
            search_text="not present",
            replace_text="whatever",
            backup_dir=tmp_path,
        )

        assert "error" in result
        assert "revert_id" not in result

    def test_edit_file_backward_compatible_no_backup_dir(self, tmp_path: Path) -> None:
        """
        When backup_dir is None (default), edit_file still works but does NOT
        produce a revert_id — preserves backward compatibility with existing tests.
        """
        target = tmp_path / "hardware.md"
        target.write_text("old text", encoding="utf-8")

        result = edit_file(
            filepath=str(target),
            search_text="old text",
            replace_text="new text",
        )

        assert "error" not in result
        assert "success" in result
        # No revert_id when backup_dir is not provided
        assert "revert_id" not in result


# ──────────────────────────────────────────────────────────────────────────────
# create_file() — integration with backup
# ──────────────────────────────────────────────────────────────────────────────

class TestCreateFileWithBackup:

    def test_create_file_returns_revert_id(self, tmp_path: Path) -> None:
        target = tmp_path / "new_materials.md"

        result = create_file(
            filepath=str(target),
            content="# New Materials\n\nMDF 18mm.",
            backup_dir=tmp_path,
        )

        assert "error" not in result
        assert "revert_id" in result
        assert _is_valid_uuid(result["revert_id"])

    def test_create_file_backup_records_not_existed(self, tmp_path: Path) -> None:
        """Backup for a new file must record existed=False so revert deletes it."""
        target = tmp_path / "new_file.md"

        result = create_file(
            filepath=str(target),
            content="content",
            backup_dir=tmp_path,
        )

        state = _read_backup(tmp_path, result["revert_id"])
        assert state["existed"] is False
        assert state["content"] is None

    def test_create_file_no_revert_id_when_file_exists(self, tmp_path: Path) -> None:
        """When create_file is rejected (file already exists), no revert_id is returned."""
        target = tmp_path / "existing.md"
        target.write_text("already here", encoding="utf-8")

        result = create_file(
            filepath=str(target),
            content="content",
            backup_dir=tmp_path,
        )

        assert "error" in result
        assert "revert_id" not in result

    def test_create_file_backward_compatible_no_backup_dir(self, tmp_path: Path) -> None:
        target = tmp_path / "new_file.md"

        result = create_file(
            filepath=str(target),
            content="content",
        )

        assert "error" not in result
        assert "revert_id" not in result


# ──────────────────────────────────────────────────────────────────────────────
# append_to_file() — integration with backup
# ──────────────────────────────────────────────────────────────────────────────

class TestAppendToFileWithBackup:

    def test_append_returns_revert_id(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")

        result = append_to_file(
            filepath=str(target),
            content="## Appended",
            backup_dir=tmp_path,
        )

        assert "error" not in result
        assert "revert_id" in result
        assert _is_valid_uuid(result["revert_id"])

    def test_append_backup_records_existed_true(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.md"
        original = "# Notes\n\nOriginal line.\n"
        target.write_text(original, encoding="utf-8")

        result = append_to_file(
            filepath=str(target),
            content="appended text",
            backup_dir=tmp_path,
        )

        state = _read_backup(tmp_path, result["revert_id"])
        assert state["existed"] is True
        assert state["content"] == original

    def test_append_backup_records_existed_false_for_new_file(self, tmp_path: Path) -> None:
        """append_to_file auto-creates files; backup must record that fact."""
        target = tmp_path / "new_notes.md"
        assert not target.exists()

        result = append_to_file(
            filepath=str(target),
            content="first line",
            backup_dir=tmp_path,
        )

        state = _read_backup(tmp_path, result["revert_id"])
        assert state["existed"] is False

    def test_append_backward_compatible_no_backup_dir(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")

        result = append_to_file(
            filepath=str(target),
            content="new line",
        )

        assert "error" not in result
        assert "revert_id" not in result
