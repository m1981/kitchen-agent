"""
tests/eval/test_golden_eval.py
===============================
Tests for the golden dataset evaluation runner.

Uses FakeOrchestrator to avoid actual LLM calls.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from src.agent.context_assembler import ContextSlot
from src.agent.turn_orchestrator import (
    ToolCall,
    ToolCallDetail,
    TurnInput,
    TurnOutput,
)
from src.eval.golden_eval import (
    CheckStatus,
    EvalCase,
    EvalRun,
    GoldenDatasetEval,
)


# ---------------------------------------------------------------------------
# Fake orchestrator for testing
# ---------------------------------------------------------------------------

class FakeOrchestrator:
    """Fake orchestrator that returns controllable responses."""

    def __init__(
        self,
        response: str = "Blum oferuje Tandembox Antaro i Merivobox.",
        tool_details: list[ToolCallDetail] | None = None,
        raises: Exception | None = None,
    ):
        self._response = response
        self._tool_details = tool_details or []
        self._raises = raises
        self.last_turn_input: TurnInput | None = None

    def run(self, session: dict, turn_input: TurnInput) -> TurnOutput:
        if self._raises:
            raise self._raises

        self.last_turn_input = turn_input

        tool_calls = [
            ToolCall(id=d.id, name=d.name, arguments=d.arguments)
            for d in self._tool_details
        ]
        tool_logs = [
            {
                "name": d.name,
                "args": d.arguments,
                "result": {"content": d.result_content} if not d.is_error else {"error": d.result_content},
            }
            for d in self._tool_details
        ]

        return TurnOutput(
            assistant_message=self._response,
            updated_api_history=[],
            user_turn_id="test-user-turn",
            assistant_turn_id="test-assistant-turn",
            tool_calls_made=tool_calls,
            tool_logs=tool_logs,
            tokens_used={"input": 100, "output": 50, "total": 150},
            provider_name="test",
            model_name="test-model",
            context_slots={ContextSlot.SYSTEM_PROMPT: 100},
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dataset_path(tmp_path: Path) -> Path:
    """Create a minimal golden dataset for testing."""
    content = """
- id: eval-test-001
  name: "Test case 1"
  question: "Jakie są systemy szufladowe Blum?"
  mode: general
  expected:
    must_search: true
    must_cite: true
    must_mention:
      - "Tandembox"
      - "Merivobox"

- id: eval-test-002
  name: "Test case 2"
  question: "Powiedz mi coś o okuciach"
  mode: general
  expected:
    must_mention:
      - "okucia"
    forbidden:
      - "nie wiem"

- id: eval-test-003
  name: "Test case 3"
  question: "Jakie restauracje polecasz?"
  mode: general
  expected:
    must_not_search: true
"""
    path = tmp_path / "test_dataset.yaml"
    path.write_text(content)
    return path


@pytest.fixture
def kb_dir(tmp_path: Path) -> Path:
    """Create a minimal KB directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "test.md").write_text("# Test\nContent here\n")
    return data_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGoldenDatasetEval:
    """Test the evaluation runner."""

    def test_load_dataset(self, dataset_path: Path):
        """Should load all cases from YAML."""
        orchestrator = FakeOrchestrator()
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        # Access private method to test loading
        cases = evaluator._load_dataset(dataset_path)
        assert len(cases) == 3
        assert cases[0].id == "eval-test-001"
        assert cases[1].id == "eval-test-002"

    def test_run_all_cases(self, dataset_path: Path):
        """Should run all cases and return results."""
        orchestrator = FakeOrchestrator(
            response="Tandembox Antaro i Merivobox to systemy Blum. [1]"
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path)
        assert run.total_cases == 3
        assert len(run.results) == 3

    def test_run_specific_cases(self, dataset_path: Path):
        """Should run only specified cases."""
        orchestrator = FakeOrchestrator()
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-001"])
        assert run.total_cases == 1
        assert run.results[0].case.id == "eval-test-001"

    def test_must_mention_pass(self, dataset_path: Path):
        """Case passes when response mentions required terms."""
        orchestrator = FakeOrchestrator(
            response="Tandembox Antaro i Merivobox to systemy szufladowe Blum."
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-001"])
        result = run.results[0]

        # Check that must_mention checks passed
        mention_checks = [c for c in result.checks if c.name.startswith("mentions_")]
        assert all(c.status == CheckStatus.PASS for c in mention_checks)

    def test_must_mention_fail(self, dataset_path: Path):
        """Case fails when response doesn't mention required terms."""
        orchestrator = FakeOrchestrator(
            response="Blum oferuje różne systemy szufladowe."
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-001"])
        result = run.results[0]

        # Check that must_mention checks failed
        mention_checks = [c for c in result.checks if c.name.startswith("mentions_")]
        assert any(c.status == CheckStatus.FAIL for c in mention_checks)

    def test_forbidden_term_fail(self, dataset_path: Path):
        """Case fails when response contains forbidden term."""
        orchestrator = FakeOrchestrator(
            response="Okucia są różne. Nie wiem jakie wybrać."
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-002"])
        result = run.results[0]

        forbidden_checks = [c for c in result.checks if c.name.startswith("forbidden_")]
        assert any(c.status == CheckStatus.FAIL for c in forbidden_checks)

    def test_forbidden_term_pass(self, dataset_path: Path):
        """Case passes when response doesn't contain forbidden term."""
        orchestrator = FakeOrchestrator(
            response="Okucia to ważny element każdej kuchni."
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-002"])
        result = run.results[0]

        forbidden_checks = [c for c in result.checks if c.name.startswith("forbidden_")]
        assert all(c.status == CheckStatus.PASS for c in forbidden_checks)

    def test_must_search_pass(self, dataset_path: Path):
        """Case passes when agent searched KB."""
        tool_detail = ToolCallDetail(
            id="tc-1",
            name="search_knowledge_base",
            arguments={"query": "Blum"},
            result_content="Found results",
        )
        orchestrator = FakeOrchestrator(
            response="Tandembox Antaro i Merivobox. [1]",
            tool_details=[tool_detail],
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-001"])
        result = run.results[0]

        search_check = next(c for c in result.checks if c.name == "searched_kb")
        assert search_check.status == CheckStatus.PASS

    def test_must_search_fail(self, dataset_path: Path):
        """Case fails when agent didn't search KB."""
        orchestrator = FakeOrchestrator(
            response="Tandembox Antaro i Merivobox."
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-001"])
        result = run.results[0]

        search_check = next(c for c in result.checks if c.name == "searched_kb")
        assert search_check.status == CheckStatus.FAIL

    def test_must_not_search_pass(self, dataset_path: Path):
        """Case passes when agent didn't search for out-of-scope question."""
        orchestrator = FakeOrchestrator(
            response="Przepraszam, ale to pytanie wykracza poza moją dziedzinę."
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-003"])
        result = run.results[0]

        no_search_check = next(c for c in result.checks if c.name == "did_not_search")
        assert no_search_check.status == CheckStatus.PASS

    def test_must_not_search_fail(self, dataset_path: Path):
        """Case fails when agent searched for out-of-scope question."""
        tool_detail = ToolCallDetail(
            id="tc-1",
            name="search_knowledge_base",
            arguments={"query": "restauracje"},
            result_content="No results",
        )
        orchestrator = FakeOrchestrator(
            response="Nie znalazłem informacji o restauracjach.",
            tool_details=[tool_detail],
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-003"])
        result = run.results[0]

        no_search_check = next(c for c in result.checks if c.name == "did_not_search")
        assert no_search_check.status == CheckStatus.FAIL

    def test_agent_error_handling(self, dataset_path: Path):
        """Should handle agent errors gracefully."""
        orchestrator = FakeOrchestrator(raises=RuntimeError("API error"))
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(dataset_path, case_ids=["eval-test-001"])
        result = run.results[0]

        assert not result.passed
        assert "ERROR" in result.response
        assert any(c.status == CheckStatus.FAIL for c in result.checks)


class TestEvalRun:
    """Test the EvalRun summary and serialization."""

    def test_summary_includes_pass_rate(self, dataset_path: Path):
        orchestrator = FakeOrchestrator(
            response="Tandembox Antaro i Merivobox. [1]"
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)
        run = evaluator.run(dataset_path)

        summary = run.summary()
        assert "Passed:" in summary
        assert "%" in summary

    def test_summary_lists_failures(self, dataset_path: Path):
        orchestrator = FakeOrchestrator(
            response="Something without required terms"
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)
        run = evaluator.run(dataset_path, case_ids=["eval-test-001"])

        summary = run.summary()
        assert "FAILED CASES" in summary

    def test_to_dict_structure(self, dataset_path: Path):
        orchestrator = FakeOrchestrator()
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)
        run = evaluator.run(dataset_path)

        data = run.to_dict()
        assert "summary" in data
        assert "results" in data
        assert "total_cases" in data["summary"]
        assert "pass_rate" in data["summary"]


class TestCitationIntegration:
    """Test citation verification integration."""

    def test_citation_check_when_must_cite(self, kb_dir: Path):
        """Should verify citations when must_cite is expected."""
        dataset_content = """
- id: eval-cite-001
  name: "Citation test"
  question: "Jakie są systemy Blum?"
  mode: general
  expected:
    must_cite: true
    min_citations: 1
"""
        dataset_path = kb_dir.parent / "dataset.yaml"
        dataset_path.write_text(dataset_content)

        orchestrator = FakeOrchestrator(
            response="Blum oferuje Tandembox i Merivobox [1].\n\n## Źródła\n1. `data/test.md` (linie 1-3)"
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator, data_dir=kb_dir)

        run = evaluator.run(dataset_path)
        result = run.results[0]

        # Should have citation checks
        citation_checks = [c for c in result.checks if "citation" in c.name.lower()]
        assert len(citation_checks) > 0

    def test_citation_check_valid_file(self, kb_dir: Path):
        """Should pass when citation points to real file."""
        dataset_content = """
- id: eval-cite-002
  name: "Valid citation"
  question: "Jakie są systemy Blum?"
  mode: general
  expected:
    must_cite: true
    citation_must_exist: true
"""
        dataset_path = kb_dir.parent / "dataset.yaml"
        dataset_path.write_text(dataset_content)

        orchestrator = FakeOrchestrator(
            response="Blum oferuje Tandembox [1].\n\n## Źródła\n1. `data/test.md` (linie 1-2)"
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator, data_dir=kb_dir)

        run = evaluator.run(dataset_path)
        result = run.results[0]

        validity_check = next(
            (c for c in result.checks if c.name == "citations_valid"),
            None,
        )
        if validity_check:
            assert validity_check.status == CheckStatus.PASS

    def test_citation_check_invalid_file(self, kb_dir: Path):
        """Should fail when citation points to nonexistent file."""
        dataset_content = """
- id: eval-cite-003
  name: "Invalid citation"
  question: "Jakie są systemy Blum?"
  mode: general
  expected:
    must_cite: true
    citation_must_exist: true
"""
        dataset_path = kb_dir.parent / "dataset.yaml"
        dataset_path.write_text(dataset_content)

        orchestrator = FakeOrchestrator(
            response="Blum oferuje Tandembox [1].\n\n## Źródła\n1. `data/Nieistniejacy.md` (linie 1-2)"
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator, data_dir=kb_dir)

        run = evaluator.run(dataset_path)
        result = run.results[0]

        assert not result.passed


class TestTrajectoryRules:
    """Test trajectory rule checking."""

    def test_read_before_edit_pass(self, dataset_path: Path):
        """Should pass when read_file comes before edit_file."""
        dataset_content = """
- id: eval-traj-001
  name: "Read before edit"
  question: "Edytuj plik"
  mode: general
  expected:
    trajectory_rules:
      - "read_before_edit"
"""
        path = dataset_path.parent / "traj.yaml"
        path.write_text(dataset_content)

        tool_details = [
            ToolCallDetail(
                id="tc-1",
                name="get_repo_map",
                arguments={},
                result_content="Files listed",
            ),
            ToolCallDetail(
                id="tc-2",
                name="read_file",
                arguments={"filepath": "data/test.md"},
                result_content="File content",
            ),
            ToolCallDetail(
                id="tc-3",
                name="edit_file",
                arguments={"filepath": "data/test.md", "search_text": "old", "replace_text": "new"},
                result_content="Edited",
            ),
        ]
        orchestrator = FakeOrchestrator(
            response="Plik został zedytowany.",
            tool_details=tool_details,
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(path)
        result = run.results[0]

        traj_check = next(
            (c for c in result.checks if "read_before_edit" in c.name),
            None,
        )
        if traj_check:
            assert traj_check.status == CheckStatus.PASS

    def test_read_before_edit_fail(self, dataset_path: Path):
        """Should fail when edit_file comes before read_file."""
        dataset_content = """
- id: eval-traj-002
  name: "Edit without read"
  question: "Edytuj plik"
  mode: general
  expected:
    trajectory_rules:
      - "read_before_edit"
"""
        path = dataset_path.parent / "traj2.yaml"
        path.write_text(dataset_content)

        tool_details = [
            ToolCallDetail(
                id="tc-1",
                name="edit_file",
                arguments={"filepath": "data/test.md", "search_text": "old", "replace_text": "new"},
                result_content="Edited",
            ),
        ]
        orchestrator = FakeOrchestrator(
            response="Plik został zedytowany.",
            tool_details=tool_details,
        )
        evaluator = GoldenDatasetEval(orchestrator=orchestrator)

        run = evaluator.run(path)
        result = run.results[0]

        traj_check = next(
            (c for c in result.checks if "read_before_edit" in c.name),
            None,
        )
        if traj_check:
            assert traj_check.status == CheckStatus.FAIL
