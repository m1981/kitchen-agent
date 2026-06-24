"""
src/eval/golden_eval.py
========================
Golden dataset evaluation runner.

Runs the agent against a curated set of questions and checks
whether responses meet expected criteria.

Usage:
    from src.eval.golden_eval import GoldenDatasetEval

    eval = GoldenDatasetEval(orchestrator=orchestrator, data_dir=Path("data"))
    results = eval.run(Path("tests/eval/golden_dataset.yaml"))
    print(results.summary())
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

import structlog
import yaml

from src.agent.turn_orchestrator import TurnInput, TurnOrchestrator, TurnOutput
from src.eval.citation_verifier import CitationVerifier, Verdict as CitationVerdict

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class CheckStatus(Enum):
    PASS = auto()
    FAIL = auto()
    SKIP = auto()


@dataclass
class Check:
    """Result of a single check."""
    name: str
    status: CheckStatus
    message: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class EvalCase:
    """A single evaluation case from the dataset."""
    id: str
    name: str
    question: str
    mode: str
    expected: dict
    context_files: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    """Result of running one evaluation case."""
    case: EvalCase
    response: str
    tool_calls: list[str]
    checks: list[Check]
    duration_ms: float
    citation_report: Any = None  # CitationReport or None

    @property
    def passed(self) -> bool:
        return all(c.status == CheckStatus.PASS for c in self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)


@dataclass
class EvalRun:
    """Complete evaluation run with all results."""
    results: list[EvalResult]
    total_duration_ms: float
    prompts: dict[str, str] = field(default_factory=dict)  # mode -> prompt content

    @property
    def total_cases(self) -> int:
        return len(self.results)

    @property
    def passed_cases(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_cases(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return self.passed_cases / self.total_cases

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            "=" * 60,
            "GOLDEN DATASET EVALUATION REPORT",
            "=" * 60,
            f"Total cases: {self.total_cases}",
            f"Passed:      {self.passed_cases} ({self.pass_rate:.0%})",
            f"Failed:      {self.failed_cases}",
            f"Duration:    {self.total_duration_ms:.0f}ms",
            "",
        ]

        # Group by status
        passed = [r for r in self.results if r.passed]
        failed = [r for r in self.results if not r.passed]

        if failed:
            lines.append("FAILED CASES:")
            lines.append("-" * 40)
            for result in failed:
                lines.append(f"  ❌ {result.case.id}: {result.case.name}")
                lines.append(f"     Question: {result.case.question[:60]}...")
                for check in result.checks:
                    if check.status == CheckStatus.FAIL:
                        lines.append(f"     ✗ {check.name}: {check.message}")
                lines.append("")

        if passed:
            lines.append("PASSED CASES:")
            lines.append("-" * 40)
            for result in passed:
                lines.append(f"  ✅ {result.case.id}: {result.case.name}")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        result = {
            "summary": {
                "total_cases": self.total_cases,
                "passed_cases": self.passed_cases,
                "failed_cases": self.failed_cases,
                "pass_rate": round(self.pass_rate, 3),
                "total_duration_ms": round(self.total_duration_ms),
            },
            "results": [
                {
                    "id": r.case.id,
                    "name": r.case.name,
                    "question": r.case.question,
                    "passed": r.passed,
                    "checks": [
                        {
                            "name": c.name,
                            "status": c.status.name,
                            "message": c.message,
                        }
                        for c in r.checks
                    ],
                    "response_preview": r.response[:200],
                    "tool_calls": r.tool_calls,
                    "duration_ms": round(r.duration_ms),
                }
                for r in self.results
            ],
        }
        if self.prompts:
            result["prompts"] = self.prompts
        return result


# ---------------------------------------------------------------------------
# Trajectory rules
# ---------------------------------------------------------------------------

TRAJECTORY_RULES = {
    "read_before_edit": lambda tools: (
        "edit_file" not in tools or
        (tools.index("read_file") < tools.index("edit_file")
         if "read_file" in tools else False)
    ),
    "map_before_unknown_file": lambda tools: (
        "get_repo_map" in tools or "read_file" not in tools
    ),
    "search_before_answer": lambda tools: "search_knowledge_base" in tools,
    "no_repeated_search": lambda tools: (
        sum(1 for t in tools if t == "search_knowledge_base") <= 2
    ),
}


# ---------------------------------------------------------------------------
# Golden Dataset Evaluator
# ---------------------------------------------------------------------------

class GoldenDatasetEval:
    """
    Runs the agent against a golden dataset and evaluates responses.

    Args:
        orchestrator: TurnOrchestrator instance to run the agent.
        data_dir: Path to the knowledge base for citation verification.
    """

    def __init__(
        self,
        orchestrator: TurnOrchestrator,
        data_dir: Path | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._data_dir = data_dir
        self._citation_verifier = (
            CitationVerifier(data_dir=data_dir) if data_dir else None
        )

    def run(
        self,
        dataset_path: Path,
        case_ids: list[str] | None = None,
    ) -> EvalRun:
        """
        Run evaluation on the golden dataset.

        Args:
            dataset_path: Path to the YAML dataset file.
            case_ids: Optional list of specific case IDs to run.
                      If None, runs all cases.

        Returns:
            EvalRun with all results.
        """
        start_time = time.time()
        cases = self._load_dataset(dataset_path)

        if case_ids:
            cases = [c for c in cases if c.id in case_ids]

        # Capture prompts used in this evaluation run
        prompts = self._capture_prompts(cases)

        results = []
        for case in cases:
            log.info("eval_running_case", case_id=case.id, question=case.question[:50])
            result = self._run_case(case)
            results.append(result)
            log.info(
                "eval_case_complete",
                case_id=case.id,
                passed=result.passed,
                checks=f"{result.pass_count}/{len(result.checks)}",
            )

        total_duration = (time.time() - start_time) * 1000
        return EvalRun(results=results, total_duration_ms=total_duration, prompts=prompts)

    def _load_dataset(self, path: Path) -> list[EvalCase]:
        """Load and parse the YAML dataset."""
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        cases = []
        for item in raw:
            cases.append(EvalCase(
                id=item["id"],
                name=item.get("name", item["id"]),
                question=item["question"],
                mode=item.get("mode", "general"),
                expected=item.get("expected", {}),
                context_files=item.get("context_files", []),
            ))

        return cases

    def _capture_prompts(self, cases: list[EvalCase]) -> dict[str, str]:
        """
        Capture the prompts used in this evaluation run.
        
        Returns dict mapping mode_id -> prompt content.
        """
        prompts = {}
        
        # Get unique modes from cases
        modes = set(c.mode for c in cases)
        
        # Access prompt manager through orchestrator's context assembler
        # Guard against mock objects in tests
        ctx = getattr(self._orchestrator, '_ctx', None)
        if ctx is None:
            return prompts
        
        prompt_manager = getattr(ctx, '_prompts', None)
        if prompt_manager is None:
            return prompts
        
        for mode in modes:
            try:
                prompt_content = prompt_manager.get_system_instruction(mode)
                prompts[mode] = prompt_content
            except Exception as e:
                log.warning("prompt_capture_failed", mode=mode, error=str(e))
                prompts[mode] = f"[Error capturing prompt: {e}]"
        
        return prompts

    def _run_case(self, case: EvalCase) -> EvalResult:
        """Run a single evaluation case."""
        start_time = time.time()

        # Build turn input
        turn_input = TurnInput(
            user_message=case.question,
            mode=case.mode,
            context_files=case.context_files,
            use_tools=True,
        )

        # Create empty session
        session = {
            "session_id": f"eval-{case.id}",
            "messages": [],
            "system_prompt": None,
        }

        # Run the agent
        try:
            output = self._orchestrator.run(session, turn_input)
            response = output.assistant_message
            tool_calls = [tc.name for tc in output.tool_calls_made]
        except Exception as e:
            # Agent errored — record as failure
            duration = (time.time() - start_time) * 1000
            return EvalResult(
                case=case,
                response=f"ERROR: {e}",
                tool_calls=[],
                checks=[Check(
                    name="agent_execution",
                    status=CheckStatus.FAIL,
                    message=f"Agent error: {e}",
                )],
                duration_ms=duration,
            )

        duration = (time.time() - start_time) * 1000

        # Run checks
        checks = self._check_response(case, response, tool_calls)

        # Run citation verification if available
        citation_report = None
        if self._citation_verifier and case.expected.get("must_cite"):
            citation_report = self._citation_verifier.verify(response)
            checks.extend(self._check_citations(case, citation_report))

        return EvalResult(
            case=case,
            response=response,
            tool_calls=tool_calls,
            checks=checks,
            duration_ms=duration,
            citation_report=citation_report,
        )

    def _check_response(
        self,
        case: EvalCase,
        response: str,
        tool_calls: list[str],
    ) -> list[Check]:
        """Run all checks on the response."""
        checks = []
        expected = case.expected
        response_lower = response.lower()

        # Check must_mention
        for term in expected.get("must_mention", []):
            checks.append(Check(
                name=f"mentions_{term}",
                status=(
                    CheckStatus.PASS if term.lower() in response_lower
                    else CheckStatus.FAIL
                ),
                message=f"Response must mention '{term}'",
            ))

        # Check forbidden terms
        for term in expected.get("forbidden", []):
            checks.append(Check(
                name=f"forbidden_{term}",
                status=(
                    CheckStatus.PASS if term.lower() not in response_lower
                    else CheckStatus.FAIL
                ),
                message=f"Response must NOT contain '{term}'",
            ))

        # Check must_search
        if expected.get("must_search"):
            searched = "search_knowledge_base" in tool_calls
            checks.append(Check(
                name="searched_kb",
                status=CheckStatus.PASS if searched else CheckStatus.FAIL,
                message="Agent must search knowledge base",
            ))

        # Check must_not_search
        if expected.get("must_not_search"):
            searched = "search_knowledge_base" in tool_calls
            checks.append(Check(
                name="did_not_search",
                status=CheckStatus.PASS if not searched else CheckStatus.FAIL,
                message="Agent should not search for this out-of-scope question",
            ))

        # Check must_use_tools
        for tool_name in expected.get("must_use_tools", []):
            used = tool_name in tool_calls
            checks.append(Check(
                name=f"used_{tool_name}",
                status=CheckStatus.PASS if used else CheckStatus.FAIL,
                message=f"Agent must use {tool_name}",
            ))

        # Check must_cite
        if expected.get("must_cite"):
            has_citation = (
                "## źródła" in response_lower or
                "## źródła" in response_lower or
                "[1]" in response or
                "[2]" in response
            )
            checks.append(Check(
                name="has_citations",
                status=CheckStatus.PASS if has_citation else CheckStatus.FAIL,
                message="Response must include citations",
            ))

        # Check trajectory rules
        for rule_name in expected.get("trajectory_rules", []):
            rule_fn = TRAJECTORY_RULES.get(rule_name)
            if rule_fn:
                passed = rule_fn(tool_calls)
                checks.append(Check(
                    name=f"trajectory_{rule_name}",
                    status=CheckStatus.PASS if passed else CheckStatus.FAIL,
                    message=f"Trajectory rule: {rule_name}",
                ))

        return checks

    def _check_citations(
        self,
        case: EvalCase,
        citation_report: Any,
    ) -> list[Check]:
        """Run citation-specific checks."""
        checks = []
        expected = case.expected

        # Check citation count
        min_citations = expected.get("min_citations", 0)
        if min_citations > 0:
            checks.append(Check(
                name="min_citations",
                status=(
                    CheckStatus.PASS
                    if citation_report.total_citations >= min_citations
                    else CheckStatus.FAIL
                ),
                message=(
                    f"Need at least {min_citations} citations, "
                    f"got {citation_report.total_citations}"
                ),
            ))

        # Check citation validity
        if expected.get("citation_must_exist"):
            all_valid = citation_report.valid_citations == citation_report.total_citations
            checks.append(Check(
                name="citations_valid",
                status=CheckStatus.PASS if all_valid else CheckStatus.FAIL,
                message=(
                    "All citations must point to real files"
                    if all_valid
                    else f"{len(citation_report.invalid_citations)} invalid citations"
                ),
            ))

        # Check citation verdict
        if citation_report.verdict == CitationVerdict.FAIL:
            checks.append(Check(
                name="citation_verdict",
                status=CheckStatus.FAIL,
                message=f"Citation verification failed: {citation_report.issues[:2]}",
            ))

        return checks
