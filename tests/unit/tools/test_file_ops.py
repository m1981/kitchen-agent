"""
tests/test_file_ops.py
======================
Unit tests for the file-operation tool functions.

Covers:
 - read_file: success, file-not-found, OSError on read      (lines 38-44)
 - edit_file: success, search-not-found, file-not-found, OSError on read  (lines 59-60)
 - create_file: success, already-exists, OSError on write   (lines 88-89)
 - append_to_file: success, creates dirs, OSError           (lines 106-107)
 - search_knowledge_base: truncation at MAX_MATCHES         (lines 134-135, 141-142)
 - search_knowledge_base: OSError on unreadable file        (lines 134-135)
"""
import stat
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.tools.file_ops import (
    append_to_file,
    create_file,
    edit_file,
    read_file,
    search_knowledge_base,
)


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

def test_read_file_success(tmp_path: Path) -> None:
    f = tmp_path / "test.md"
    f.write_text("hello world", encoding="utf-8")
    result = read_file(str(f))
    assert result == {"content": "hello world"}


def test_read_file_not_found(tmp_path: Path) -> None:
    result = read_file(str(tmp_path / "ghost.md"))
    assert "error" in result
    assert "File not found" in result["error"]


def test_read_file_oserror(tmp_path: Path) -> None:
    """Simulates a permission error on read — covers the OSError branch (lines 43-44)."""
    f = tmp_path / "locked.md"
    f.write_text("secret", encoding="utf-8")
    with patch("src.tools.file_ops.Path.read_text", side_effect=OSError("permission denied")):
        result = read_file(str(f))
    assert "error" in result
    assert "permission denied" in result["error"]


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

def test_edit_file_success(tmp_path: Path) -> None:
    f = tmp_path / "hinges.md"
    f.write_text("We use standard hinges.", encoding="utf-8")
    result = edit_file(str(f), "standard hinges", "Blum soft-close hinges")
    assert "error" not in result
    assert "Successfully updated" in result["success"]
    assert f.read_text(encoding="utf-8") == "We use Blum soft-close hinges."


def test_edit_file_search_text_not_found(tmp_path: Path) -> None:
    f = tmp_path / "hinges.md"
    f.write_text("We use standard hinges.", encoding="utf-8")
    result = edit_file(str(f), "cheap hinges", "Blum hinges")
    assert "error" in result
    assert "Search text not found" in result["error"]
    assert f.read_text(encoding="utf-8") == "We use standard hinges."


def test_edit_file_not_found(tmp_path: Path) -> None:
    result = edit_file(str(tmp_path / "ghost.md"), "anything", "something")
    assert "error" in result
    assert "File not found" in result["error"]


def test_edit_file_oserror_on_read(tmp_path: Path) -> None:
    """Simulates an OSError when reading the file content (lines 59-60)."""
    f = tmp_path / "broken.md"
    f.write_text("content", encoding="utf-8")
    with patch("src.tools.file_ops.Path.read_text", side_effect=OSError("read error")):
        result = edit_file(str(f), "content", "new")
    assert "error" in result
    assert "read error" in result["error"]


# ---------------------------------------------------------------------------
# create_file
# ---------------------------------------------------------------------------

def test_create_file_success(tmp_path: Path) -> None:
    new_file = tmp_path / "03_Finishes" / "paint.md"
    result = create_file(str(new_file), "# Paint\nWe use water-based polyurethane.")
    assert "error" not in result
    assert "Successfully created" in result["success"]
    assert new_file.exists()
    assert new_file.read_text(encoding="utf-8") == "# Paint\nWe use water-based polyurethane."


def test_create_file_already_exists(tmp_path: Path) -> None:
    existing = tmp_path / "wood.md"
    existing.write_text("Old content", encoding="utf-8")
    result = create_file(str(existing), "New content")
    assert "error" in result
    assert "already exists" in result["error"]
    assert existing.read_text(encoding="utf-8") == "Old content"


def test_create_file_oserror(tmp_path: Path) -> None:
    """Simulates an OSError on write (lines 88-89)."""
    new_file = tmp_path / "fail.md"
    with patch("src.tools.file_ops.Path.write_text", side_effect=OSError("disk full")):
        result = create_file(str(new_file), "content")
    assert "error" in result
    assert "disk full" in result["error"]


# ---------------------------------------------------------------------------
# append_to_file
# ---------------------------------------------------------------------------

def test_append_to_existing_file(tmp_path: Path) -> None:
    f = tmp_path / "notes.md"
    f.write_text("# Notes\n\nInitial content.\n", encoding="utf-8")
    result = append_to_file(str(f), "## New Section\n\nAppended text.\n")
    assert "success" in result
    content = f.read_text(encoding="utf-8")
    assert "Initial content" in content
    assert "Appended text" in content


def test_append_creates_file_if_missing(tmp_path: Path) -> None:
    f = tmp_path / "newfile.md"
    assert not f.exists()
    result = append_to_file(str(f), "# Auto-created\n\nHello.\n")
    assert "success" in result
    assert f.exists()
    assert "Hello" in f.read_text(encoding="utf-8")


def test_append_creates_parent_dirs(tmp_path: Path) -> None:
    f = tmp_path / "subdir" / "deep" / "notes.md"
    result = append_to_file(str(f), "content")
    assert "success" in result
    assert f.exists()


def test_append_oserror(tmp_path: Path) -> None:
    """Simulates an OSError on open/write (lines 106-107)."""
    f = tmp_path / "locked.md"
    with patch("src.tools.file_ops.Path.open", side_effect=OSError("no space")):
        result = append_to_file(str(f), "data")
    assert "error" in result
    assert "no space" in result["error"]


# ---------------------------------------------------------------------------
# search_knowledge_base — truncation at MAX_MATCHES (lines 141-142)
# ---------------------------------------------------------------------------

def test_search_truncates_at_200_matches(tmp_path: Path) -> None:
    """Creates 201 matching lines; result must be truncated at 200 (lines 141-142)."""
    big_file = tmp_path / "big.md"
    # Each line matches "TARGET"; 201 lines → should truncate after 200
    big_file.write_text("\n".join(["TARGET"] * 201), encoding="utf-8")

    # Use context_lines=0 to get legacy single-line-per-match output
    # so we can count exactly 200 match lines + 1 truncation notice.
    result = search_knowledge_base("TARGET", base_dir=str(tmp_path), context_lines=0)
    assert "error" not in result
    content = result["content"]
    # Truncation notice must be present
    assert "truncated at 200" in content
    # Must not contain more than 200 match lines (plus header + notice)
    match_lines = [l for l in content.splitlines() if l.strip() and not l.startswith("===") and "truncated" not in l]
    assert len(match_lines) <= 200


# ---------------------------------------------------------------------------
# search_knowledge_base — unreadable file is skipped (lines 134-135)
# ---------------------------------------------------------------------------

def test_search_skips_unreadable_file(tmp_path: Path) -> None:
    """An OSError while reading a file must be silently skipped."""
    good = tmp_path / "good.md"
    good.write_text("MATCH here\n", encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text("MATCH here too\n", encoding="utf-8")

    original_read_text = Path.read_text

    def patched_read_text(self: Path, *args, **kwargs) -> str:
        if self.name == "bad.md":
            raise OSError("unreadable")
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", patched_read_text):
        result = search_knowledge_base("MATCH", base_dir=str(tmp_path))

    assert "error" not in result
    # Only the good file's match should appear
    assert "good.md" in result["content"]
    assert "bad.md" not in result["content"]
