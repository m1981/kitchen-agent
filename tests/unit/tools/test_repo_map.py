"""
tests/test_repo_map.py
======================
Unit tests for get_repo_map.

Covers:
 - Full posix path regression test (existing)
 - Missing base_dir returns error        (line 23)
 - No .md files → 'No markdown files'   (line 40)
 - Unreadable file is skipped gracefully (lines 36-37)
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from src.tools.repo_map import get_repo_map


def test_get_repo_map_returns_full_posix_paths(tmp_path: Path) -> None:
    """
    Repo map must include the full POSIX path so the LLM can pass it
    directly to read_file without guessing the prefix.
    """
    md_dir = tmp_path / "01_Materials"
    md_dir.mkdir()
    md_file = md_dir / "wood.md"
    md_file.write_text("# Wood Types\nSome text.", encoding="utf-8")

    result = get_repo_map(base_dir=str(tmp_path))

    assert "error" not in result
    assert md_file.as_posix() in result["content"]
    assert "# Wood Types" in result["content"]


def test_get_repo_map_missing_dir() -> None:
    """A non-existent base_dir must return an error dict (line 23)."""
    result = get_repo_map(base_dir="/nonexistent/path/xyz")
    assert "error" in result
    assert "Directory not found" in result["error"]


def test_get_repo_map_empty_directory(tmp_path: Path) -> None:
    """A directory with no .md files returns the 'No markdown files' message (line 40)."""
    result = get_repo_map(base_dir=str(tmp_path))
    assert "error" not in result
    assert "No markdown files found" in result["content"]


def test_get_repo_map_unreadable_file(tmp_path: Path) -> None:
    """An OSError while reading a file appends '(unreadable)' and continues (lines 36-37)."""
    md_file = tmp_path / "good.md"
    md_file.write_text("# Good\n", encoding="utf-8")
    bad_file = tmp_path / "bad.md"
    bad_file.write_text("# Bad\n", encoding="utf-8")

    original_read_text = Path.read_text

    def patched(self: Path, *args, **kwargs) -> str:
        if self.name == "bad.md":
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", patched):
        result = get_repo_map(base_dir=str(tmp_path))

    assert "error" not in result
    assert "(unreadable)" in result["content"]
    # The good file's heading must still appear
    assert "# Good" in result["content"]


def test_get_repo_map_extracts_headings(tmp_path: Path) -> None:
    """Only lines starting with '#' are extracted from each file."""
    f = tmp_path / "materials.md"
    f.write_text(
        "# Materials\n\nSome prose.\n\n## Subsection\n\nMore prose.\n",
        encoding="utf-8",
    )
    result = get_repo_map(base_dir=str(tmp_path))
    content = result["content"]
    assert "# Materials" in content
    assert "## Subsection" in content
    assert "Some prose" not in content
    assert "More prose" not in content
