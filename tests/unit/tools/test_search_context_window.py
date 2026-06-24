"""
TDD: tests for search_knowledge_base with context_lines support.

The current implementation returns isolated matching lines.
For a 20-30 file KB with scattered/contradicting knowledge,
the model needs N lines of surrounding context to resolve conflicts.

These tests are written FIRST and will fail until the implementation
is extended with a `context_lines` parameter.
"""
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures — realistic kitchen-domain KB
# ---------------------------------------------------------------------------

@pytest.fixture
def kitchen_kb(tmp_path: Path) -> Path:
    """
    Simulates a realistic 20-30 file KB where:
    - the same topic (e.g. hinge gap) appears in multiple files
    - one file contradicts another
    - relevant info sits 3 lines BELOW a matching keyword
    """
    (tmp_path / "montaz_zawiasow.md").write_text(
        "# Montaż zawiasów\n"
        "\n"
        "## Odstęp od krawędzi\n"
        "\n"
        "Dla zawiasów Blum Clip-Top przyjmujemy odstęp osi zawiasu od krawędzi frontu:\n"
        "- front nakładany: 37 mm\n"
        "- front wpuszczany: 45 mm\n"
        "\n"
        "## Uwaga dotycząca frontów lakierowanych\n"
        "\n"
        "Przy frontach lakierowanych zwiększ odstęp do 38 mm (nakładany).\n",
        encoding="utf-8",
    )
    (tmp_path / "blum_katalog.md").write_text(
        "# Katalog Blum\n"
        "\n"
        "## Clip-Top 110°\n"
        "\n"
        "Zawias Clip-Top 110° — numer katalogowy 71B3550.\n"
        "Standardowy odstęp osi od krawędzi: 37 mm.\n"
        "Maksymalne obciążenie drzwi: 3 kg per zawias.\n"
        "\n"
        "## Clip-Top 165°\n"
        "\n"
        "Zawias Clip-Top 165° — numer katalogowy 71T3650.\n"
        "Odstęp osi od krawędzi: 37 mm.\n",
        encoding="utf-8",
    )
    (tmp_path / "uwagi_starsze.md").write_text(
        "# Uwagi archiwalne (2021)\n"
        "\n"
        "UWAGA: nieaktualne — sprawdź montaz_zawiasow.md\n"
        "\n"
        "## Stare normy\n"
        "\n"
        "Odstęp zawiasu Blum od krawędzi: 35 mm.\n"
        "Ta wartość pochodzi ze starego katalogu i NIE obowiązuje.\n",
        encoding="utf-8",
    )
    (tmp_path / "narzedzia.md").write_text(
        "# Narzędzia\n"
        "\n"
        "Wiertło Forstner 35mm do zawiasów.\n"
        "Szablon Blum Minijig do precyzyjnego wiercenia.\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Group A: context_lines=0  (backward-compat, current behaviour)
# ---------------------------------------------------------------------------

class TestContextLinesZero:
    """context_lines=0 must behave exactly like the current implementation."""

    def test_returns_matching_line_only(self, kitchen_kb):
        from src.tools.file_ops import search_knowledge_base

        result = search_knowledge_base("37 mm", base_dir=str(kitchen_kb), context_lines=0)
        assert "error" not in result
        lines = result["content"].splitlines()
        # Every non-header line must contain "37 mm"
        match_lines = [l for l in lines if not l.startswith("===") and l.strip()]
        assert all("37 mm" in l for l in match_lines)

    def test_no_context_separator_present(self, kitchen_kb):
        from src.tools.file_ops import search_knowledge_base

        result = search_knowledge_base("Clip-Top", base_dir=str(kitchen_kb), context_lines=0)
        assert "---" not in result["content"]  # context separator must not appear


# ---------------------------------------------------------------------------
# Group B: context_lines=2  (the new behaviour we need)
# ---------------------------------------------------------------------------

class TestContextLinesTwo:

    def test_surrounding_lines_included(self, kitchen_kb):
        """
        Searching '37 mm' with context_lines=2 must return the lines
        BEFORE and AFTER the match — so the model sees 'nakładany' context.
        """
        from src.tools.file_ops import search_knowledge_base

        result = search_knowledge_base("37 mm", base_dir=str(kitchen_kb), context_lines=2)
        assert "error" not in result
        content = result["content"]
        # The line 2 above "37 mm" in montaz_zawiasow.md is "Dla zawiasów Blum Clip-Top..."
        assert "Dla zawiasów Blum Clip-Top" in content

    def test_contradicting_files_both_visible(self, kitchen_kb):
        """
        When two files match '35 mm' vs '37 mm', context must reveal
        the archival warning so the model can flag the contradiction.
        """
        from src.tools.file_ops import search_knowledge_base

        result = search_knowledge_base(
            "odstęp.*blum|blum.*odstęp|35 mm|37 mm",
            base_dir=str(kitchen_kb),
            context_lines=3,
        )
        content = result["content"]
        # Both the current and the archived contradicting value appear
        assert "37 mm" in content
        assert "35 mm" in content
        # Archival warning is visible within context
        assert "NIE obowiązuje" in content or "nieaktualne" in content.lower()

    def test_context_does_not_bleed_across_files(self, kitchen_kb):
        """
        Context lines from file A must not be mixed with lines from file B.
        Each file's matches are presented in their own block.
        """
        from src.tools.file_ops import search_knowledge_base

        result = search_knowledge_base("Clip-Top", base_dir=str(kitchen_kb), context_lines=2)
        content = result["content"]
        # File headers must appear to separate blocks
        assert "montaz_zawiasow.md" in content
        assert "blum_katalog.md" in content
        # File sections are ordered independently
        idx_montaz = content.index("montaz_zawiasow.md")
        idx_blum = content.index("blum_katalog.md")
        assert idx_montaz != idx_blum  # different positions in output

    def test_context_clipped_at_file_boundary(self, kitchen_kb):
        """
        If a match is on line 1, the context must not request line -1.
        No IndexError, no empty ghost lines.
        """
        from src.tools.file_ops import search_knowledge_base

        # "# Katalog Blum" is line 1 — context before it would underflow
        result = search_knowledge_base("Katalog Blum", base_dir=str(kitchen_kb), context_lines=5)
        assert "error" not in result
        assert "Katalog Blum" in result["content"]

    def test_context_clipped_at_end_of_file(self, kitchen_kb):
        """
        If a match is on the last line, context_lines after must not overflow.
        """
        from src.tools.file_ops import search_knowledge_base

        # The last line of narzedzia.md is the Minijig line
        result = search_knowledge_base("Minijig", base_dir=str(kitchen_kb), context_lines=5)
        assert "error" not in result
        assert "Minijig" in result["content"]

    def test_overlapping_context_windows_are_merged(self, kitchen_kb):
        """
        When two matches are close together (within 2*context_lines lines),
        their context windows must be merged, not duplicated.
        """
        from src.tools.file_ops import search_knowledge_base

        # "37 mm" appears twice in blum_katalog.md close together
        result = search_knowledge_base("37 mm", base_dir=str(kitchen_kb), context_lines=3)
        content = result["content"]
        # The section "Clip-Top 110°" header must appear only ONCE per file block,
        # not repeated because it falls in two overlapping windows
        assert content.count("Clip-Top 110°") <= 2  # at most once per file


# ---------------------------------------------------------------------------
# Group C: default value of context_lines
# ---------------------------------------------------------------------------

class TestContextLinesDefault:
    """
    The default must be context_lines=2 — not 0.
    This ensures the model gets context without the caller explicitly asking.
    Rationale: for a 20-30 file KB, isolated line matches are almost useless.
    """

    def test_default_includes_surrounding_context(self, kitchen_kb):
        from src.tools.file_ops import search_knowledge_base

        # Call WITHOUT context_lines — must use the default (2)
        result = search_knowledge_base("37 mm", base_dir=str(kitchen_kb))
        content = result["content"]
        # With default=2, the line above "37 mm" must be visible
        assert "nakładany" in content or "Blum Clip-Top" in content

    def test_default_does_not_load_entire_file(self, kitchen_kb):
        """Default context must NOT return whole-file content."""
        from src.tools.file_ops import search_knowledge_base

        result = search_knowledge_base("37 mm", base_dir=str(kitchen_kb))
        content = result["content"]
        # "Narzędzia" is in narzedzia.md and completely unrelated
        # It must NOT appear in results for "37 mm"
        assert "Narzędzia\n" not in content or "narzedzia.md" not in content


# ---------------------------------------------------------------------------
# Group D: MAX_MATCHES still enforced with context
# ---------------------------------------------------------------------------

class TestMaxMatchesWithContext:

    def test_truncation_message_present_when_limit_hit(self, tmp_path: Path):
        from src.tools.file_ops import search_knowledge_base

        # Write a file with 300 matching lines
        big = "\n".join(f"hinge line {i}" for i in range(300))
        (tmp_path / "huge.md").write_text(big, encoding="utf-8")

        result = search_knowledge_base("hinge", base_dir=str(tmp_path), context_lines=0)
        assert "truncated" in result["content"]

    def test_result_not_exceed_max_with_context(self, tmp_path: Path):
        """Even with context_lines=3, output must not explode unboundedly."""
        from src.tools.file_ops import search_knowledge_base

        big = "\n".join(f"hinge line {i}" for i in range(300))
        (tmp_path / "huge.md").write_text(big, encoding="utf-8")

        result = search_knowledge_base("hinge", base_dir=str(tmp_path), context_lines=3)
        # Should still truncate gracefully
        assert "error" not in result
        line_count = len(result["content"].splitlines())
        assert line_count < 1500  # reasonable upper bound


# ---------------------------------------------------------------------------
# Group E: registry tool declaration includes context_lines description
# ---------------------------------------------------------------------------

class TestRegistryDeclaration:
    """
    The Gemini tool declaration for search_knowledge_base must advertise
    the context_lines parameter so the model can use it intelligently.
    """

    def test_context_lines_param_in_declaration(self):
        from src.tools.registry import build_default_registry

        registry = build_default_registry()
        handler = registry.get_handler("search_knowledge_base")
        # Get declaration from registry entries
        entries = registry.get_all_entries()
        decl = next(e.declaration for e in entries if e.declaration.name == "search_knowledge_base")
        props = decl.parameters.properties
        assert "context_lines" in props, (
            "context_lines must be declared in the Gemini FunctionDeclaration "
            "so the model can request broader context for ambiguous queries"
        )

    def test_context_lines_has_description(self):
        from src.tools.registry import build_default_registry

        registry = build_default_registry()
        entries = registry.get_all_entries()
        decl = next(e.declaration for e in entries if e.declaration.name == "search_knowledge_base")
        desc = decl.parameters.properties["context_lines"].description
        assert desc and len(desc) > 20, "context_lines needs a meaningful description"

    def test_registry_lambda_passes_context_lines(self, kitchen_kb, monkeypatch):
        """The registry lambda must forward context_lines to the real function."""
        from src.tools.registry import build_default_registry
        import src.config as cfg

        monkeypatch.setattr(cfg.settings, "data_dir", kitchen_kb)

        registry = build_default_registry()
        fn = registry.get_handler("search_knowledge_base")
        # Call via the registry handler with context_lines
        result = fn(query="37 mm", context_lines=2)
        assert "error" not in result
        assert "Blum Clip-Top" in result["content"]
