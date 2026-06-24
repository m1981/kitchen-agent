#!/usr/bin/env python3
"""
scripts/verify_citations.py
============================
CLI tool to verify citations in agent responses.

Usage:
    # Verify a response from stdin
    echo "Response text..." | python scripts/verify_citations.py

    # Verify a response from a file
    python scripts/verify_citations.py --file response.md

    # Verify with custom data directory
    python scripts/verify_citations.py --data-dir /path/to/data --file response.md

    # Verify and show JSON output
    python scripts/verify_citations.py --json --file response.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.eval.citation_verifier import CitationVerifier, Verdict


def main():
    parser = argparse.ArgumentParser(
        description="Verify citations in LLM agent responses"
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="File containing the agent response"
    )
    parser.add_argument(
        "--data-dir", "-d",
        type=Path,
        default=Path("data"),
        help="Path to the knowledge base data directory (default: data/)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--strict", "-s",
        action="store_true",
        help="Strict mode: uncited claims are failures"
    )
    args = parser.parse_args()

    # Read response
    if args.file:
        response = args.file.read_text(encoding="utf-8")
    else:
        response = sys.stdin.read()

    if not response.strip():
        print("Error: Empty response", file=sys.stderr)
        sys.exit(1)

    # Verify
    verifier = CitationVerifier(
        data_dir=args.data_dir,
        strict=args.strict,
    )
    report = verifier.verify(response)

    # Output
    if args.json:
        # Convert to JSON-serializable format
        output = {
            "verdict": report.verdict.name,
            "citations": {
                "total": report.total_citations,
                "valid": report.valid_citations,
                "invalid": [
                    {
                        "filepath": check.citation.filepath,
                        "error": check.error_message,
                        "raw": check.citation.raw_text,
                    }
                    for check in report.invalid_citations
                ],
            },
            "claims": {
                "total": report.total_claims,
                "cited": report.cited_claims,
                "uncited": [
                    {
                        "text": claim.text[:100],
                        "type": claim.claim_type.name,
                    }
                    for claim in report.uncited_claims
                ],
            },
            "issues": report.issues,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(report.summary())

    # Exit code
    sys.exit(0 if report.verdict == Verdict.PASS else 1)


if __name__ == "__main__":
    main()
