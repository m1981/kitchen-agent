"""
Tests for search_knowledge_base and append_to_file tools.
"""
import os
import pytest
from pathlib import Path


@pytest.fixture
def tmp_kb(tmp_path: Path):
    """Creates a tiny temporary knowledge base."""
    (tmp_path / "materials.md").write_text(
        "# Materials\n\n18mm Birch Plywood for carcasses.\nBlum hinges are standard.\n",
        encoding="utf-8",
    )
    (tmp_path / "hardware.md").write_text(
        "# Hardware\n\nBlum Clip-Top 110° hinge, order code 71B3550.\nKings runners 45kg.\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# search_knowledge_base
# ---------------------------------------------------------------------------

def test_search_single_keyword(tmp_kb, monkeypatch):
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("Blum", base_dir=str(tmp_kb))
    assert "error" not in result
    content = result["content"]
    assert "materials.md" in content
    assert "hardware.md" in content
    assert "Blum" in content


def test_search_or_pattern(tmp_kb, monkeypatch):
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("plywood|runner", base_dir=str(tmp_kb))
    content = result["content"]
    assert "Plywood" in content or "plywood" in content
    assert "runner" in content.lower()


def test_search_no_matches(tmp_kb):
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("unicorn", base_dir=str(tmp_kb))
    assert "error" not in result
    assert "No matches found" in result["content"]


def test_search_invalid_regex(tmp_kb):
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("[invalid", base_dir=str(tmp_kb))
    assert "error" in result
    assert "Invalid regex" in result["error"]


def test_search_missing_dir():
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("anything", base_dir="/nonexistent/path")
    assert "error" in result


def test_search_case_insensitive(tmp_kb):
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("BIRCH", base_dir=str(tmp_kb))
    assert "Birch" in result["content"] or "birch" in result["content"].lower()


