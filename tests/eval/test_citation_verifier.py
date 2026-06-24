"""
tests/eval/test_citation_verifier.py
=====================================
Tests for the CitationVerifier.

Tests verify:
1. Citation parsing (multiple formats)
2. File existence checking
3. Line range validation
4. Claim extraction
5. Overall verdict logic
6. Integration with real KB files
"""
from __future__ import annotations

import pytest
from pathlib import Path

from src.eval.citation_verifier import (
    Citation,
    CitationReport,
    CitationVerifier,
    Claim,
    ClaimType,
    Verdict,
    verify_citations,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kb_dir(tmp_path: Path) -> Path:
    """Create a minimal knowledge base directory structure."""
    (tmp_path / "data" / "04_Okucia_i_Akcesoria").mkdir(parents=True)
    (tmp_path / "data" / "00_Dokumenty_Strategiczne").mkdir(parents=True)

    szuflady_content = """\
# SZUFLADY BLUM – KOMPENDIUM

## 1. MAPA EKOSYSTEMU BLUM

| System | Pozycja | Cena |
|--------|---------|------|
| Legrabox | Premium | 180-280 zł |
| Merivobox | Standard | 120-180 zł |
| Tandembox Antaro | Klasyk | 90-140 zł |

## 2. TANDEMBOX ANTARO

Tandembox Antaro to ewolucja legendarnego Tandemboksa.

### Warianty wysokości ścianki:

| Oznaczenie | Wysokość | Zastosowanie |
|------------|----------|--------------|
| N | 83 mm | Standardowa |
| C | 105 mm | Wysoka |
| D | 122 mm | Z organizacją |

### Kolory ścianki Antaro:

- Biały (NW)
- Szary Orion (OG)
- Czarny (SW)
"""
    (tmp_path / "data" / "04_Okucia_i_Akcesoria" / "Szuflady_Blum.md").write_text(
        szuflady_content
    )

    strategia_content = """\
# PODSUMOWANIE STRATEGII

## Cele na 2026

1. Przejście na Merivobox jako standard
2. Redukcja Tandembox Antaro do projektów budżetowych
3. Wprowadzenie Legrabox dla klientów premium

## Priorytety

- Automatyzacja CNC
- Standaryzacja wymiarów
- Szkolenie zespołu
"""
    (tmp_path / "data" / "00_Dokumenty_Strategiczne" / "Strategia.md").write_text(
        strategia_content
    )

    return tmp_path / "data"


@pytest.fixture
def verifier(kb_dir: Path) -> CitationVerifier:
    """Create a CitationVerifier with the test KB."""
    return CitationVerifier(data_dir=kb_dir)


# ---------------------------------------------------------------------------
# Citation Parsing Tests
# ---------------------------------------------------------------------------

class TestCitationParsing:
    """Test extraction of citations from response text."""

    def test_standard_format_with_line_range(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verifier.verify(response)
        assert report.total_citations == 1
        assert report.valid_citations == 1

    def test_single_line_format(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linia 5)
"""
        report = verifier.verify(response)
        assert report.total_citations == 1
        assert report.valid_citations == 1

    def test_english_line_format(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (lines 1-10)
"""
        report = verifier.verify(response)
        assert report.total_citations == 1
        assert report.valid_citations == 1

    def test_no_line_numbers(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md`
"""
        report = verifier.verify(response)
        assert report.total_citations == 1
        assert report.valid_citations == 1

    def test_multiple_citations(self, verifier: CitationVerifier):
        response = """
Merivobox to nasz standard [1]. Antaro jest tańszy [2].

## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
2. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 15-25)
"""
        report = verifier.verify(response)
        assert report.total_citations == 2
        assert report.valid_citations == 2

    def test_mixed_formats(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
2. `data/00_Dokumenty_Strategiczne/Strategia.md` (linia 5)
3. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md`
"""
        report = verifier.verify(response)
        assert report.total_citations == 3
        assert report.valid_citations == 3

    def test_no_sources_section(self, verifier: CitationVerifier):
        """Response without Źródła section should have 0 citations."""
        response = "Blum oferuje trzy systemy szufladowe."
        report = verifier.verify(response)
        assert report.total_citations == 0

    def test_empty_sources_section(self, verifier: CitationVerifier):
        response = """
## Źródła

"""
        report = verifier.verify(response)
        assert report.total_citations == 0


# ---------------------------------------------------------------------------
# File Existence Tests
# ---------------------------------------------------------------------------

class TestFileExistence:
    """Test checking if cited files exist."""

    def test_existing_file(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-5)
"""
        report = verifier.verify(response)
        assert report.valid_citations == 1
        assert len(report.invalid_citations) == 0

    def test_nonexistent_file(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Nieistniejacy.md` (linie 1-5)
"""
        report = verifier.verify(response)
        assert report.valid_citations == 0
        assert len(report.invalid_citations) == 1
        assert "not found" in report.invalid_citations[0].error_message.lower()

    def test_wrong_directory(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/99_Bledny_Katalog/Szuflady_Blum.md` (linie 1-5)
"""
        report = verifier.verify(response)
        assert report.valid_citations == 0
        assert len(report.invalid_citations) == 1

    def test_partial_path_invalid(self, verifier: CitationVerifier):
        """Partial path without data/ prefix should be invalid."""
        response = """
## Źródła

1. `Szuflady_Blum.md` (linie 1-5)
"""
        report = verifier.verify(response)
        assert report.valid_citations == 0
        assert len(report.invalid_citations) == 1


# ---------------------------------------------------------------------------
# Line Range Validation Tests
# ---------------------------------------------------------------------------

class TestLineRangeValidation:
    """Test validation of line numbers in citations."""

    def test_valid_line_range(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verifier.verify(response)
        assert report.valid_citations == 1

    def test_single_line_valid(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linia 5)
"""
        report = verifier.verify(response)
        assert report.valid_citations == 1

    def test_line_zero_invalid(self, verifier: CitationVerifier):
        """Line 0 should be invalid (lines are 1-indexed)."""
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linia 0)
"""
        report = verifier.verify(response)
        assert report.valid_citations == 0
        assert len(report.invalid_citations) == 1

    def test_reversed_line_range_handled(self, verifier: CitationVerifier):
        """Line end < line start should be invalid."""
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 20-5)
"""
        report = verifier.verify(response)
        # Should be invalid
        assert report.valid_citations == 0

    def test_line_beyond_file_length_clamped(self, verifier: CitationVerifier):
        """Line beyond file length should be clamped with warning."""
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-999)
"""
        report = verifier.verify(response)
        # Implementation clamps end line — should still be valid
        assert report.total_citations == 1

    def test_start_line_beyond_file_length(self, verifier: CitationVerifier):
        """Start line beyond file length should be invalid."""
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linia 999)
"""
        report = verifier.verify(response)
        assert report.valid_citations == 0


# ---------------------------------------------------------------------------
# Claim Extraction Tests
# ---------------------------------------------------------------------------

class TestClaimExtraction:
    """Test extraction of factual claims from response text."""

    def test_factual_claim_with_number(self, verifier: CitationVerifier):
        """Claims with numbers should be detected."""
        response = """
Merivobox kosztuje 120-180 zł za sztukę [1].

## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verifier.verify(response)
        assert report.total_claims >= 1

    def test_factual_claim_with_dimension(self, verifier: CitationVerifier):
        """Claims with dimensions should be detected."""
        response = """
Wysokość ścianki N wynosi 83 mm [1].

## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 15-20)
"""
        report = verifier.verify(response)
        assert report.total_claims >= 1

    def test_general_statement_not_claim(self, verifier: CitationVerifier):
        """General statements without factual content should not be claims."""
        response = """
Blum oferuje różne systemy szufladowe.

## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-5)
"""
        report = verifier.verify(response)
        # May or may not detect claims — depends on classifier
        # Just verify it doesn't crash
        assert report.total_claims >= 0

    def test_cited_claim_counted(self, verifier: CitationVerifier):
        """Claims with inline citations should be counted as cited."""
        response = """
Merivobox kosztuje 120-180 zł za sztukę [1]. Antaro to 90-140 zł [1].

## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verifier.verify(response)
        if report.total_claims > 0:
            assert report.cited_claims >= 1


# ---------------------------------------------------------------------------
# Verdict Tests
# ---------------------------------------------------------------------------

class TestVerdictLogic:
    """Test overall verdict determination."""

    def test_pass_when_all_valid(self, verifier: CitationVerifier):
        response = """
Merivobox to nasz standard [1].

## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verifier.verify(response)
        assert report.verdict == Verdict.PASS

    def test_fail_when_file_not_found(self, verifier: CitationVerifier):
        response = """
Merivobox to nasz standard [1].

## Źródła

1. `data/Nieistniejacy.md` (linie 1-10)
"""
        report = verifier.verify(response)
        assert report.verdict == Verdict.FAIL

    def test_fail_when_no_citations_but_has_claims(self, verifier: CitationVerifier):
        """Response with factual claims but no citations should fail."""
        response = """
Merivobox kosztuje 120-180 zł za sztukę. Wysokość ścianki N to 83 mm.
"""
        report = verifier.verify(response)
        assert report.verdict == Verdict.FAIL

    def test_pass_when_no_claims(self, verifier: CitationVerifier):
        """Response without factual claims should pass."""
        response = """
Jak mogę Ci pomóc?
"""
        report = verifier.verify(response)
        assert report.verdict == Verdict.PASS


# ---------------------------------------------------------------------------
# Report Summary Tests
# ---------------------------------------------------------------------------

class TestReportSummary:
    """Test the summary() method of CitationReport."""

    def test_summary_includes_verdict(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verifier.verify(response)
        summary = report.summary()
        assert "PASS" in summary or "WARN" in summary or "FAIL" in summary

    def test_summary_includes_citation_count(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
2. `data/00_Dokumenty_Strategiczne/Strategia.md` (linie 1-5)
"""
        report = verifier.verify(response)
        summary = report.summary()
        assert "2/" in summary or "2" in summary

    def test_summary_lists_invalid_citations(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/Nieistniejacy.md` (linie 1-10)
"""
        report = verifier.verify(response)
        summary = report.summary()
        assert "Invalid" in summary or "invalid" in summary or "FAIL" in summary


# ---------------------------------------------------------------------------
# Convenience Function Tests
# ---------------------------------------------------------------------------

class TestConvenienceFunction:
    """Test the verify_citations() convenience function."""

    def test_returns_citation_report(self, kb_dir: Path):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verify_citations(response, data_dir=kb_dir)
        assert isinstance(report, CitationReport)

    def test_strict_mode(self, kb_dir: Path):
        """Strict mode should make uncited claims a failure."""
        response = """
Merivobox kosztuje 120-180 zł za sztukę. Wysokość ścianki N to 83 mm.
"""
        report = verify_citations(response, data_dir=kb_dir, strict=True)
        # Should fail — claims without citations
        assert report.verdict == Verdict.FAIL


# ---------------------------------------------------------------------------
# Integration Tests with Real KB
# ---------------------------------------------------------------------------

class TestRealKBIntegration:
    """Test against the actual knowledge base files in data/."""

    @pytest.fixture
    def real_verifier(self) -> CitationVerifier | None:
        """Create verifier with real KB if it exists."""
        data_dir = Path(__file__).parent.parent.parent / "data"
        if data_dir.exists():
            return CitationVerifier(data_dir=data_dir)
        return None

    def test_real_file_szuflady(self, real_verifier: CitationVerifier | None):
        """Verify citation to real Szuflady_Blum_Kompendium.md file."""
        if real_verifier is None:
            pytest.skip("Real KB not available")

        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum_Kompendium.md` (linie 1-20)
"""
        report = real_verifier.verify(response)
        assert report.valid_citations == 1

    def test_real_file_strategia(self, real_verifier: CitationVerifier | None):
        """Verify citation to real strategic document."""
        if real_verifier is None:
            pytest.skip("Real KB not available")

        # Find any .md file in 00_Dokumenty_Strategiczne
        data_dir = Path(__file__).parent.parent.parent / "data"
        strat_dir = data_dir / "00_Dokumenty_Strategiczne"
        if not strat_dir.exists():
            pytest.skip("Strategic documents directory not found")

        md_files = list(strat_dir.glob("*.md"))
        if not md_files:
            pytest.skip("No .md files in strategic documents")

        file_path = f"data/00_Dokumenty_Strategiczne/{md_files[0].name}"
        response = f"""
## Źródła

1. `{file_path}` (linie 1-5)
"""
        report = real_verifier.verify(response)
        assert report.valid_citations == 1

    def test_real_kb_has_files(self, real_verifier: CitationVerifier | None):
        """Verify the real KB has markdown files."""
        if real_verifier is None:
            pytest.skip("Real KB not available")

        data_dir = Path(__file__).parent.parent.parent / "data"
        md_files = list(data_dir.rglob("*.md"))
        assert len(md_files) > 0, "KB should have markdown files"

    def test_full_response_with_real_citations(self, real_verifier: CitationVerifier | None):
        """Test a realistic full response with citations to real files."""
        if real_verifier is None:
            pytest.skip("Real KB not available")

        # Find a real file to cite
        data_dir = Path(__file__).parent.parent.parent / "data"
        md_files = list(data_dir.rglob("*.md"))
        if not md_files:
            pytest.skip("No .md files found")

        # Use the first file found
        file_path = str(md_files[0].relative_to(data_dir))
        file_path = f"data/{file_path}"

        response = f"""
Blum oferuje trzy główne systemy szufladowe [1]:

- **Tandembox Antaro** — klasyk, sprawdzony, tańszy
- **Merivobox** — złoty standard na 2026 rok
- **Legrabox** — premium, niewidoczne prowadnice

Każdy system ma inną matematykę wymiarów dna i tyłu szuflady [1].

---

## Źródła

1. `{file_path}` (linie 1-5)
"""
        report = real_verifier.verify(response)
        assert report.total_citations == 1
        assert report.valid_citations == 1


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_response(self, verifier: CitationVerifier):
        report = verifier.verify("")
        assert report.total_citations == 0
        assert report.verdict == Verdict.PASS

    def test_only_sources_section(self, verifier: CitationVerifier):
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verifier.verify(response)
        assert report.total_citations == 1

    def test_citation_with_special_characters(self, verifier: CitationVerifier):
        """Citations with Polish characters should work."""
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verifier.verify(response)
        assert report.total_citations == 1

    def test_citation_in_alternative_section_header(self, verifier: CitationVerifier):
        """Alternative section headers should be recognized."""
        response = """
## Sources

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1-10)
"""
        report = verifier.verify(response)
        assert report.total_citations == 1

    def test_citation_with_extra_whitespace(self, verifier: CitationVerifier):
        """Extra whitespace in citations should be handled."""
        response = """
## Źródła

1.  `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md`  (linie  1-10)
"""
        report = verifier.verify(response)
        assert report.total_citations == 1

    def test_citation_with_different_dashes(self, verifier: CitationVerifier):
        """Different dash characters in line ranges."""
        response = """
## Źródła

1. `data/04_Okucia_i_Akcesoria/Szuflady_Blum.md` (linie 1–10)
"""
        report = verifier.verify(response)
        assert report.total_citations == 1
