#!/usr/bin/env python3
"""
scripts/test_citation_compliance.py
=====================================
Tests how well the LLM follows citation instructions.

Runs a single question through the agent multiple times and
measures citation compliance rate.

Usage:
    .venv/bin/python scripts/test_citation_compliance.py
    .venv/bin/python scripts/test_citation_compliance.py --runs 5
    .venv/bin/python scripts/test_citation_compliance.py --question "Jakie są ceny Blum?"
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dependencies import get_turn_orchestrator
from src.agent.turn_orchestrator import TurnInput
from src.eval.citation_verifier import CitationVerifier


def run_test(question: str, mode: str, runs: int, data_dir: Path) -> None:
    """Run citation compliance test."""
    orchestrator = get_turn_orchestrator()
    verifier = CitationVerifier(data_dir=data_dir)

    results = []
    for i in range(runs):
        print(f"\nRun {i+1}/{runs}...", end=" ", flush=True)

        session = {"session_id": f"cite-test-{i}", "messages": [], "system_prompt": None}
        turn_input = TurnInput(user_message=question, mode=mode, use_tools=True)

        start = time.time()
        try:
            output = orchestrator.run(session, turn_input)
            duration = time.time() - start

            # Check citations
            has_section = "## źródła" in output.assistant_message.lower()
            has_inline = "[1]" in output.assistant_message
            report = verifier.verify(output.assistant_message)

            results.append({
                "run": i + 1,
                "success": True,
                "has_citation_section": has_section,
                "has_inline_markers": has_inline,
                "citation_count": report.total_citations,
                "valid_citations": report.valid_citations,
                "verdict": report.verdict.name,
                "response_len": len(output.assistant_message),
                "tool_calls": len(output.tool_calls_made),
                "duration": duration,
            })

            status = "✅" if has_section and has_inline else "⚠️" if has_section or has_inline else "❌"
            print(f"{status} citations={report.total_citations} tools={len(output.tool_calls_made)} ({duration:.1f}s)")

        except Exception as e:
            duration = time.time() - start
            results.append({
                "run": i + 1,
                "success": False,
                "error": str(e)[:100],
                "duration": duration,
            })
            print(f"❌ Error: {str(e)[:60]}")

    # Summary
    print("\n" + "=" * 60)
    print("CITATION COMPLIANCE REPORT")
    print("=" * 60)
    print(f"Question: {question}")
    print(f"Mode: {mode}")
    print(f"Runs: {runs}")

    successful = [r for r in results if r.get("success")]
    if not successful:
        print("\n❌ All runs failed!")
        return

    with_section = sum(1 for r in successful if r.get("has_citation_section"))
    with_inline = sum(1 for r in successful if r.get("has_inline_markers"))
    with_both = sum(1 for r in successful if r.get("has_citation_section") and r.get("has_inline_markers"))

    print(f"\nSuccessful runs: {len(successful)}/{runs}")
    print(f"\nCitation compliance:")
    print(f"  Has ## Źródła section:  {with_section}/{len(successful)} ({with_section/len(successful)*100:.0f}%)")
    print(f"  Has inline [1] markers: {with_inline}/{len(successful)} ({with_inline/len(successful)*100:.0f}%)")
    print(f"  Has both (ideal):       {with_both}/{len(successful)} ({with_both/len(successful)*100:.0f}%)")

    avg_citations = sum(r.get("citation_count", 0) for r in successful) / len(successful)
    avg_tools = sum(r.get("tool_calls", 0) for r in successful) / len(successful)
    avg_duration = sum(r.get("duration", 0) for r in successful) / len(successful)

    print(f"\nAverages:")
    print(f"  Citations per response: {avg_citations:.1f}")
    print(f"  Tool calls per turn:    {avg_tools:.1f}")
    print(f"  Duration per turn:      {avg_duration:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Test citation compliance")
    parser.add_argument(
        "--question", "-q",
        default="Jakie są ceny systemów szufladowych Blum?",
        help="Question to ask"
    )
    parser.add_argument(
        "--mode", "-m",
        default="general",
        help="Prompt mode (general, design, assembly)"
    )
    parser.add_argument(
        "--runs", "-r",
        type=int,
        default=3,
        help="Number of runs"
    )
    parser.add_argument(
        "--data-dir", "-d",
        type=Path,
        default=Path("data"),
        help="Knowledge base directory"
    )
    args = parser.parse_args()

    run_test(
        question=args.question,
        mode=args.mode,
        runs=args.runs,
        data_dir=args.data_dir,
    )


if __name__ == "__main__":
    main()
