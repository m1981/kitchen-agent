"""
tests/unit/tools/test_search_improvements.py
==============================================
Regression tests for search_knowledge_base tool.

These tests verify correct regex behavior for LLM-driven searches.
The LLM is expected to use regex syntax (| for OR) as instructed
in the system prompt.
"""
import os
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Test 1: Pipe-separated OR queries work correctly
# ---------------------------------------------------------------------------

def test_or_query_with_pipe(tmp_kb):
    """Pipe-separated OR queries should match across all terms."""
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("Blum|szuflady|Tandembox", base_dir=str(tmp_kb))
    assert "error" not in result
    content = result["content"]
    # Should find matches in multiple files
    assert "blum_compendium.md" in content
    assert "standards.md" in content


# ---------------------------------------------------------------------------
# Test 2: Multi-word OR queries work correctly
# ---------------------------------------------------------------------------

def test_multi_word_or_query(tmp_kb):
    """Multiple terms with pipes should find all terms."""
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("Merivobox|Legrabox|Tandembox", base_dir=str(tmp_kb))
    assert "error" not in result
    content = result["content"]
    # All terms should be found
    assert "Merivobox" in content or "merivobox" in content.lower()
    assert "Legrabox" in content or "legrabox" in content.lower()


# ---------------------------------------------------------------------------
# Test 3: Exact phrases (quoted) work correctly
# ---------------------------------------------------------------------------

def test_quoted_phrase_search(tmp_kb):
    """Quoted phrases should find exact matches."""
    from src.tools.file_ops import search_knowledge_base

    # Quoted phrase should be kept intact
    result = search_knowledge_base('"Blum Merivobox"', base_dir=str(tmp_kb))
    assert "error" not in result
    content = result["content"]
    # Should find exact phrase
    assert "Blum Merivobox" in content


# ---------------------------------------------------------------------------
# Test 4: Single word queries work
# ---------------------------------------------------------------------------

def test_single_word_query(tmp_kb):
    """Single word queries should work unchanged."""
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("Blum", base_dir=str(tmp_kb))
    assert "error" not in result
    content = result["content"]
    assert "blum_compendium.md" in content
    assert "standards.md" in content


# ---------------------------------------------------------------------------
# Test 5: Regex special characters work
# ---------------------------------------------------------------------------

def test_regex_special_chars(tmp_kb):
    """Regex special characters should still work."""
    from src.tools.file_ops import search_knowledge_base

    # \d should match digits
    result = search_knowledge_base(r"\d{4}", base_dir=str(tmp_kb))
    assert "error" not in result
    content = result["content"]
    assert "2026" in content


# ---------------------------------------------------------------------------
# Test 6: "No matches" response is clear
# ---------------------------------------------------------------------------

def test_no_matches_response(tmp_kb):
    """When no matches found, response should be clear."""
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base("unicorn|dragon", base_dir=str(tmp_kb))
    assert "error" not in result
    content = result["content"]
    assert "No matches" in content


# ---------------------------------------------------------------------------
# Test 7: context_lines parameter works
# ---------------------------------------------------------------------------

def test_context_lines_works(tmp_kb):
    """context_lines should control how many lines around match are shown."""
    from src.tools.file_ops import search_knowledge_base

    result = search_knowledge_base(
        "Blum|szuflady|Tandembox", base_dir=str(tmp_kb), context_lines=3,
    )
    assert "error" not in result
    content = result["content"]
    # Should have context lines (>> markers)
    assert ">>" in content


# ---------------------------------------------------------------------------
# Test 8: Two-word phrase searches work (e.g., "37 mm")
# ---------------------------------------------------------------------------

def test_two_word_phrase_search(tmp_kb):
    """Two-word phrases should be searched as-is (not split)."""
    from src.tools.file_ops import search_knowledge_base

    # "Blum komplet" is a specific phrase in playbook.md
    result = search_knowledge_base("Blum komplet", base_dir=str(tmp_kb))
    assert "error" not in result
    content = result["content"]
    # Should find the exact phrase
    assert "Blum komplet" in content
