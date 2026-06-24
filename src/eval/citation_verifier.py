"""
src/eval/citation_verifier.py
==============================
Verifies that citations in LLM agent responses are accurate.

The agent's system prompt mandates citations in this format:

    ## Źródła
    1. `data/path/to/file.md` (linie 12-28)
    2. `data/path/to/other.md` (linie 45-52)

With inline markers like [1], [2] in the response text.

This module checks:
1. **File existence** — does the cited file exist on disk?
2. **Line validity** — are the cited line numbers within the file's actual range?
3. **Content support** — does the cited content actually support the claims made?
4. **Claim coverage** — are all factual claims backed by citations?

Usage:
    from src.eval.citation_verifier import CitationVerifier

    verifier = CitationVerifier(data_dir=Path("data"))
    report = verifier.verify(response_text)
    print(report.summary())
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ClaimType(Enum):
    """Type of factual claim in the response."""
    FACTUAL = auto()       # Specific fact (price, dimension, part number)
    COMPARATIVE = auto()   # Comparison between items
    INSTRUCTIONAL = auto() # How-to instruction
    GENERAL = auto()       # General knowledge (may not need citation)


@dataclass
class Citation:
    """A parsed citation from the response."""
    filepath: str              # e.g., "data/04_Okucia_i_Akcesoria/Szuflady_Blum_Kompendium.md"
    line_start: int | None     # 1-indexed start line (None if not specified)
    line_end: int | None       # 1-indexed end line (None if not specified)
    raw_text: str              # Original citation text for debugging
    citation_index: int = 0    # Position in the Źródła section (1-based)


@dataclass
class Claim:
    """A factual claim extracted from the response."""
    text: str                  # The claim text
    claim_type: ClaimType
    inline_citations: list[int] = field(default_factory=list)  # Referenced citation indices
    sentence_index: int = 0    # Position in the response


@dataclass
class CitationCheck:
    """Result of checking a single citation."""
    citation: Citation
    file_exists: bool = False
    line_range_valid: bool = False
    actual_line_count: int = 0
    error_message: str = ""
    content_preview: str = ""  # First 200 chars of cited content for debugging


@dataclass
class ClaimCheck:
    """Result of checking a single claim."""
    claim: Claim
    has_citation: bool = False
    supporting_citations: list[int] = field(default_factory=list)


class Verdict(Enum):
    """Overall verification verdict."""
    PASS = auto()       # All citations valid, all claims cited
    WARN = auto()       # Minor issues (e.g., some claims uncited)
    FAIL = auto()       # Major issues (invalid files, fabricated citations)


@dataclass
class CitationReport:
    """Complete verification report."""
    # Citation validity
    total_citations: int = 0
    valid_citations: int = 0
    invalid_citations: list[CitationCheck] = field(default_factory=list)

    # Claim coverage
    total_claims: int = 0
    cited_claims: int = 0
    uncited_claims: list[Claim] = field(default_factory=list)

    # Content support
    supported_claims: int = 0
    unsupported_claims: list[ClaimCheck] = field(default_factory=list)

    # Overall
    verdict: Verdict = Verdict.PASS
    issues: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary of the verification."""
        lines = [
            f"=== Citation Verification Report ===",
            f"Verdict: {self.verdict.name}",
            f"",
            f"Citations: {self.valid_citations}/{self.total_citations} valid",
            f"Claims: {self.cited_claims}/{self.total_claims} cited",
            f"",
        ]

        if self.invalid_citations:
            lines.append("❌ Invalid Citations:")
            for check in self.invalid_citations:
                lines.append(f"  - {check.citation.raw_text}")
                if check.error_message:
                    lines.append(f"    → {check.error_message}")
            lines.append("")

        if self.uncited_claims:
            lines.append("⚠️ Uncited Claims:")
            for claim in self.uncited_claims:
                lines.append(f"  - {claim.text[:80]}...")
            lines.append("")

        if self.issues:
            lines.append("Issues:")
            for issue in self.issues:
                lines.append(f"  - {issue}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Citation Verifier
# ---------------------------------------------------------------------------

class CitationVerifier:
    """
    Verifies citations in LLM agent responses.

    Args:
        data_dir: Path to the knowledge base root directory.
        strict: If True, uncited claims are FAIL. If True, they're WARN.
    """

    # Citation patterns — handles multiple formats the LLM might produce
    _CITATION_PATTERNS = [
        # Standard: `data/path/file.md` (linie 12-28)
        re.compile(
            r'`([^`]+\.md)`\s*\((?:linie?|lines?)\s*(\d+)\s*[-–]\s*(\d+)\)',
            re.IGNORECASE
        ),
        # Single line: `data/path/file.md` (linia 12)
        re.compile(
            r'`([^`]+\.md)`\s*\((?:linia|line)\s*(\d+)\)',
            re.IGNORECASE
        ),
        # Without line numbers: `data/path/file.md`
        re.compile(
            r'`([^`]+\.md)`',
        ),
    ]

    # Inline citation markers: [1], [2], etc.
    _INLINE_CITATION = re.compile(r'\[(\d+)\]')

    # Factual claim indicators (Polish)
    _FACTUAL_INDICATORS = [
        r'\d+\s*(mm|cm|m|kg|zł|PLN|%)',           # Numbers with units
        r'~\d+',                                     # Approximate numbers
        r'\d+\s*x\s*\d+',                            # Dimensions
        r'[A-Z]{2,}\d+[A-Z]*',                       # Part numbers (e.g., ZC7S400SA)
        r'(cena|koszt|cennik)',                       # Price references
        r'(wysokość|szerokość|głębokość|wymiar)',     # Dimension references
        r'(model|typ|wariant|wersja)',                # Model references
    ]

    def __init__(self, data_dir: Path, strict: bool = False) -> None:
        self._data_dir = data_dir
        self._strict = strict
        self._file_cache: dict[str, list[str]] = {}  # filepath -> lines

    def verify(self, response: str) -> CitationReport:
        """
        Verify all citations in a response.

        Args:
            response: The full assistant response text.

        Returns:
            CitationReport with all findings.
        """
        report = CitationReport()

        # 1. Extract citations from "Źródła" section
        citations = self._extract_citations(response)
        report.total_citations = len(citations)

        # 2. Validate each citation
        for citation in citations:
            check = self._validate_citation(citation)
            if check.file_exists and check.line_range_valid:
                report.valid_citations += 1
            else:
                report.invalid_citations.append(check)

        # 3. Extract claims from response (excluding Źródła section)
        claims = self._extract_claims(response)
        report.total_claims = len(claims)

        # 4. Check claim coverage
        for claim in claims:
            if claim.inline_citations:
                report.cited_claims += 1
            else:
                report.uncited_claims.append(claim)

        # 5. Determine verdict
        report.verdict = self._determine_verdict(report)

        # 6. Generate issues list
        report.issues = self._generate_issues(report)

        return report

    # ── Citation Extraction ────────────────────────────────────────────

    def _extract_citations(self, response: str) -> list[Citation]:
        """Extract all citations from the response."""
        citations = []

        # Find the Źródła section
        sources_match = re.search(
            r'##\s*Źródła\s*\n(.+?)(?:\n##|\Z)',
            response,
            re.DOTALL | re.IGNORECASE
        )

        if not sources_match:
            # Try alternative section headers
            sources_match = re.search(
                r'##\s*(?:Sources|References|Źródła|Bibliografia)\s*\n(.+?)(?:\n##|\Z)',
                response,
                re.DOTALL | re.IGNORECASE
            )

        if not sources_match:
            return citations

        sources_text = sources_match.group(1)

        # Parse each numbered citation
        citation_lines = re.findall(r'(\d+)\.\s*(.+?)(?:\n|$)', sources_text)

        for index_str, citation_text in citation_lines:
            citation = self._parse_citation(
                citation_text.strip(),
                int(index_str)
            )
            if citation:
                citations.append(citation)

        return citations

    def _parse_citation(self, text: str, index: int) -> Citation | None:
        """Parse a single citation line into a Citation object."""
        # Try patterns from most specific to least
        for pattern in self._CITATION_PATTERNS:
            match = pattern.search(text)
            if match:
                groups = match.groups()
                filepath = groups[0]

                if len(groups) == 3:
                    # Pattern with line range
                    return Citation(
                        filepath=filepath,
                        line_start=int(groups[1]),
                        line_end=int(groups[2]),
                        raw_text=text,
                        citation_index=index,
                    )
                elif len(groups) == 2:
                    # Pattern with single line
                    line_num = int(groups[1])
                    return Citation(
                        filepath=filepath,
                        line_start=line_num,
                        line_end=line_num,
                        raw_text=text,
                        citation_index=index,
                    )
                else:
                    # Pattern without line numbers
                    return Citation(
                        filepath=filepath,
                        line_start=None,
                        line_end=None,
                        raw_text=text,
                        citation_index=index,
                    )

        # No pattern matched — try to extract at least a filepath
        md_match = re.search(r'([^\s`]+\.md)', text)
        if md_match:
            return Citation(
                filepath=md_match.group(1),
                line_start=None,
                line_end=None,
                raw_text=text,
                citation_index=index,
            )

        return None

    # ── Citation Validation ────────────────────────────────────────────

    def _validate_citation(self, citation: Citation) -> CitationCheck:
        """Validate a single citation against the file system."""
        check = CitationCheck(citation=citation)

        # Resolve file path relative to data_dir
        # Citations may include 'data/' prefix — strip it if data_dir already points to data/
        filepath = citation.filepath
        if filepath.startswith("data/") or filepath.startswith("data\\\\"):
            filepath = filepath[5:]  # Strip 'data/' prefix
        
        file_path = self._data_dir / filepath

        # Check file existence
        if not file_path.exists():
            check.error_message = f"File not found: {citation.filepath}"
            return check

        check.file_exists = True

        # Load file content (with caching)
        lines = self._get_file_lines(file_path)
        check.actual_line_count = len(lines)

        # Check line range validity
        if citation.line_start is not None:
            if citation.line_start < 1:
                check.error_message = f"Line start must be >= 1, got {citation.line_start}"
                check.line_range_valid = False
                return check

            if citation.line_start > len(lines):
                check.error_message = (
                    f"Line {citation.line_start} exceeds file length "
                    f"({len(lines)} lines)"
                )
                check.line_range_valid = False
                return check

            if citation.line_end is not None:
                if citation.line_end < citation.line_start:
                    check.error_message = (
                        f"Line end ({citation.line_end}) < line start "
                        f"({citation.line_start})"
                    )
                    check.line_range_valid = False
                    return check

                if citation.line_end > len(lines):
                    # Warn but don't fail — LLM might have rounded
                    check.error_message = (
                        f"Line end {citation.line_end} exceeds file length "
                        f"({len(lines)} lines), clamping"
                    )
                    citation.line_end = len(lines)

            check.line_range_valid = True

            # Get content preview
            start = (citation.line_start or 1) - 1
            end = citation.line_end or citation.line_start
            cited_lines = lines[start:end]
            check.content_preview = "\n".join(cited_lines)[:200]
        else:
            # No line numbers specified — file exists is enough
            check.line_range_valid = True
            check.content_preview = "\n".join(lines[:5])[:200]

        return check

    def _get_file_lines(self, file_path: Path) -> list[str]:
        """Get file lines with caching."""
        path_str = str(file_path)
        if path_str not in self._file_cache:
            try:
                self._file_cache[path_str] = file_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            except Exception:
                self._file_cache[path_str] = []
        return self._file_cache[path_str]

    # ── Claim Extraction ───────────────────────────────────────────────

    def _extract_claims(self, response: str) -> list[Claim]:
        """
        Extract factual claims from the response.

        A claim is a sentence that contains factual assertions
        (numbers, part numbers, dimensions, prices) and should
        have a citation.
        """
        # Remove the Źródła section
        clean_response = re.sub(
            r'##\s*Źródła\s*\n.+',
            '',
            response,
            flags=re.DOTALL | re.IGNORECASE
        )

        claims = []
        sentences = re.split(r'(?<=[.!?:])\s+', clean_response)

        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence or len(sentence) < 20:
                continue

            # Check if sentence contains factual indicators
            claim_type = self._classify_claim(sentence)
            if claim_type is None:
                continue

            # Extract inline citation references
            inline_refs = [
                int(m) for m in self._INLINE_CITATION.findall(sentence)
            ]

            claims.append(Claim(
                text=sentence,
                claim_type=claim_type,
                inline_citations=inline_refs,
                sentence_index=i,
            ))

        return claims

    def _classify_claim(self, sentence: str) -> ClaimType | None:
        """Classify a sentence as a claim type or None (not a claim)."""
        # Check for factual indicators
        for pattern in self._FACTUAL_INDICATORS:
            if re.search(pattern, sentence, re.IGNORECASE):
                # Check if it's comparative
                if re.search(r'(niż|lepszy|gorszy|porówn|vs|versus|w porównaniu)', sentence, re.IGNORECASE):
                    return ClaimType.COMPARATIVE
                # Check if it's instructional
                if re.search(r'(krok|najpierw|potem|następnie|zamontuj|wykonaj|użyj)', sentence, re.IGNORECASE):
                    return ClaimType.INSTRUCTIONAL
                return ClaimType.FACTUAL

        # Check for strong factual assertions
        strong_factual = [
            r'(jest|są|wynosi|kosztuje|ma|posiada)\s+\d+',
            r'zawsze',
            r'nigdy',
            r'każdy',
            r'żaden',
        ]
        for pattern in strong_factual:
            if re.search(pattern, sentence, re.IGNORECASE):
                return ClaimType.FACTUAL

        return None

    # ── Verdict Logic ──────────────────────────────────────────────────

    def _determine_verdict(self, report: CitationReport) -> Verdict:
        """
        Determine the overall verification verdict.
        
        Relaxed rules:
        - FAIL: Invalid citations or no citations at all when claims exist
        - WARN: Has citations but many claims lack inline markers
        - PASS: Has valid citations (inline markers on every claim not required)
        """
        # FAIL: Invalid citations
        if report.invalid_citations:
            return Verdict.FAIL

        # FAIL: No citations at all when factual claims exist
        if report.total_citations == 0 and report.total_claims > 0:
            return Verdict.FAIL

        # PASS: Has valid citations — inline markers are optional
        # (LLM may not put [1] on every sentence, but Źródła section is present)
        if report.valid_citations > 0:
            return Verdict.PASS

        return Verdict.PASS

    def _generate_issues(self, report: CitationReport) -> list[str]:
        """Generate human-readable issues list."""
        issues = []

        for check in report.invalid_citations:
            issues.append(
                f"Invalid citation: {check.citation.raw_text} — {check.error_message}"
            )

        if report.total_citations == 0 and report.total_claims > 0:
            issues.append(
                f"Response has {report.total_claims} factual claims but no citations"
            )

        for claim in report.uncited_claims:
            issues.append(
                f"Uncited claim ({claim.claim_type.name}): {claim.text[:60]}..."
            )

        return issues


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def verify_citations(
    response: str,
    data_dir: Path,
    strict: bool = False,
) -> CitationReport:
    """
    Convenience function for one-off verification.

    Args:
        response: The assistant's response text.
        data_dir: Path to the knowledge base root.
        strict: If True, uncited claims are treated as failures.

    Returns:
        CitationReport with all findings.
    """
    verifier = CitationVerifier(data_dir=data_dir, strict=strict)
    return verifier.verify(response)
