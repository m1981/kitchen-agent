#!/usr/bin/env python3
"""
scripts/run_golden_eval.py
===========================
CLI tool to run golden dataset evaluations.

Usage:
    # Run all cases
    .venv/bin/python scripts/run_golden_eval.py

    # Run specific case
    .venv/bin/python scripts/run_golden_eval.py --case eval-001

    # Run multiple cases
    .venv/bin/python scripts/run_golden_eval.py --case eval-001 --case eval-002

    # JSON output
    .venv/bin/python scripts/run_golden_eval.py --report json

    # Save report to file
    .venv/bin/python scripts/run_golden_eval.py --output report.json

    # Verbose output
    .venv/bin/python scripts/run_golden_eval.py -v

Requires:
    - LLM provider configured (GEMINI_API_KEY or ANTHROPIC_API_KEY)
    - Knowledge base in data/ directory
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.dependencies import (
    get_context_assembler,
    get_context_budget,
    get_llm_provider,
    get_prompt_manager,
    get_response_normalizer,
    get_token_counter,
    get_tool_executor,
    get_tool_registry,
)
from src.agent.turn_orchestrator import TurnOrchestrator
from src.eval.golden_eval import GoldenDatasetEval


def build_orchestrator() -> TurnOrchestrator:
    """Build a TurnOrchestrator with all dependencies."""
    provider_name = getattr(settings, "llm_provider", "gemini")

    return TurnOrchestrator(
        context_assembler=get_context_assembler(),
        tool_executor=get_tool_executor(),
        provider=get_llm_provider(),
        response_normalizer=get_response_normalizer(),
        provider_name=provider_name,
        tool_registry=get_tool_registry(),
        token_counter=get_token_counter(),
        context_budget=get_context_budget(),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Run golden dataset evaluation"
    )
    parser.add_argument(
        "--dataset", "-d",
        type=Path,
        default=Path("tests/eval/golden_dataset.yaml"),
        help="Path to golden dataset YAML file"
    )
    parser.add_argument(
        "--case", "-c",
        action="append",
        help="Run specific case ID(s). Can be repeated."
    )
    parser.add_argument(
        "--report", "-r",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Save report to file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output for each case"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Path to knowledge base data directory"
    )
    args = parser.parse_args()

    # Validate dataset exists
    if not args.dataset.exists():
        print(f"Error: Dataset not found: {args.dataset}", file=sys.stderr)
        sys.exit(1)

    # Build orchestrator
    print("Building orchestrator...", file=sys.stderr)
    try:
        orchestrator = build_orchestrator()
    except Exception as e:
        print(f"Error building orchestrator: {e}", file=sys.stderr)
        print("Make sure LLM provider is configured (GEMINI_API_KEY or ANTHROPIC_API_KEY)", file=sys.stderr)
        sys.exit(1)

    # Run evaluation
    print(f"Running evaluation from {args.dataset}...", file=sys.stderr)
    evaluator = GoldenDatasetEval(
        orchestrator=orchestrator,
        data_dir=args.data_dir,
    )

    try:
        run = evaluator.run(
            dataset_path=args.dataset,
            case_ids=args.case,
        )
    except Exception as e:
        print(f"Error during evaluation: {e}", file=sys.stderr)
        sys.exit(1)

    # Output
    if args.report == "json":
        output = json.dumps(run.to_dict(), indent=2, ensure_ascii=False)
    else:
        output = run.summary()

        # Add verbose details
        if args.verbose:
            output += "\n\nDETAILED RESULTS:\n"
            output += "=" * 60 + "\n"
            for result in run.results:
                output += f"\n--- {result.case.id}: {result.case.name} ---\n"
                output += f"Question: {result.case.question}\n"
                output += f"Tools: {', '.join(result.tool_calls) or 'none'}\n"
                output += f"Duration: {result.duration_ms:.0f}ms\n"
                output += f"Response ({len(result.response)} chars):\n"
                output += result.response[:500]
                if len(result.response) > 500:
                    output += "\n... (truncated)"
                output += "\n"

    # Write output
    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Report saved to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Exit code
    sys.exit(0 if run.failed_cases == 0 else 1)


if __name__ == "__main__":
    main()
