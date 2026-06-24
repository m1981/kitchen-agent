# Evaluation Guide — Beyond Unit Tests

## The Problem

Your 600+ tests verify that:

- `search_knowledge_base` returns results for a regex pattern ✓
- `ToolExecutor` catches exceptions and wraps them ✓
- `ResponseNormalizer` converts provider formats ✓
- `ContextAssembler` trims history to budget ✓

They do NOT verify that:

- The LLM actually searches before answering
- The response uses KB data correctly (not hallucinated)
- Citations point to real content that supports the claims
- The agent doesn't call `search_knowledge_base` 5 times when once would suffice
- Two providers give equally good answers to the same question

**Tests verify the plumbing. Evaluation verifies the behavior.**

---

## Evaluation Layers

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 5: Human Review                                           │
│ "Does this answer actually help a carpenter do their job?"      │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Behavioral Evaluation                                  │
│ "Did the agent call the right tools in the right order?"        │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Citation & Hallucination Verification                  │
│ "Do cited sources actually support the claims?"                 │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: RAG Quality Metrics                                    │
│ "Did it find the right content? Is the answer faithful to it?"  │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Golden Dataset Evaluation                              │
│ "For known Q&A pairs, does the agent produce acceptable answers?"│
├─────────────────────────────────────────────────────────────────┤
│ Layer 0: Unit/Integration/E2E Tests (you have this)             │
│ "Does the code work correctly?"                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Golden Dataset Evaluation

### What It Is

A curated set of questions with **expected answers** or **expected behaviors**. Run the agent against them and score the results.

### How It Works

```python
# tests/eval/golden_dataset.yaml
- id: eval-001
  question: "Jakie są systemy szufladowe Blum?"
  mode: "general"
  expected:
    must_mention: ["Tandembox Antaro", "Merivobox", "Legrabox"]
    must_cite: true
    must_search: true  # agent should call search_knowledge_base
    forbidden: ["Häfele", "Hettich"]  # these are NOT Blum systems

- id: eval-002
  question: "Jaka jest cena Merivobox 400mm?"
  mode: "general"
  expected:
    must_mention: ["Merivobox"]
    must_cite: true
    must_cite_file: "data/04_Okucia_i_Akcesoria/*"  # citation must match this glob
    must_search: true

- id: eval-003
  question: "Jak zamontować zawias Blum?"
  mode: "assembly"
  expected:
    must_mention: ["montaż", "zawias"]
    must_search: true
    must_use_tools: ["search_knowledge_base"]  # specific tools expected
```

### Evaluation Runner

```python
# tests/eval/run_eval.py
import yaml
from src.agent.turn_orchestrator import TurnOrchestrator, TurnInput

class GoldenDatasetEval:
    def __init__(self, orchestrator: TurnOrchestrator):
        self.orchestrator = orchestrator

    def evaluate(self, dataset_path: str) -> list[EvalResult]:
        with open(dataset_path) as f:
            cases = yaml.safe_load(f)

        results = []
        for case in cases:
            result = self._run_case(case)
            results.append(result)

        return results

    def _run_case(self, case: dict) -> EvalResult:
        turn_input = TurnInput(
            user_message=case["question"],
            mode=case.get("mode", "general"),
            use_tools=True,
        )
        session = {"messages": [], "system_prompt": None}

        output = self.orchestrator.run(session, turn_input)

        checks = []
        expected = case["expected"]

        # Check must_mention
        if "must_mention" in expected:
            for term in expected["must_mention"]:
                checks.append(Check(
                    name=f"mentions_{term}",
                    passed=term.lower() in output.assistant_message.lower(),
                ))

        # Check must_cite
        if expected.get("must_cite"):
            has_citation = "## Źródła" in output.assistant_message or "[1]" in output.assistant_message
            checks.append(Check(name="has_citation", passed=has_citation))

        # Check must_search
        if expected.get("must_search"):
            searched = any(tc.name == "search_knowledge_base" for tc in output.tool_calls_made)
            checks.append(Check(name="searched_kb", passed=searched))

        # Check forbidden terms
        if "forbidden" in expected:
            for term in expected["forbidden"]:
                checks.append(Check(
                    name=f"forbidden_{term}",
                    passed=term.lower() not in output.assistant_message.lower(),
                ))

        return EvalResult(
            case_id=case["id"],
            question=case["question"],
            response=output.assistant_message,
            tool_calls=[tc.name for tc in output.tool_calls_made],
            checks=checks,
            passed=all(c.passed for c in checks),
        )
```

### When to Run

- **Before every prompt change** — run the golden dataset, compare pass rate
- **After provider changes** — verify Gemini and Anthropic give comparable results
- **Weekly regression** — catch drift in LLM behavior

---

## Layer 2: RAG Quality Metrics

### What It Is

Measures how well the retrieval + generation pipeline works. Three key metrics:

| Metric                | Question                                              | How to Measure                                 |
| --------------------- | ----------------------------------------------------- | ---------------------------------------------- |
| **Context Recall**    | Did the agent find the right KB content?              | Compare retrieved content against ground truth |
| **Context Precision** | Was the retrieved content relevant to the question?   | LLM judges relevance of each retrieved chunk   |
| **Faithfulness**      | Does the response stay true to the retrieved content? | Extract claims, verify each against KB         |

### Simple Implementation (No Framework Needed)

```python
# tests/eval/rag_metrics.py
class RAGEvaluator:
    """Evaluates RAG quality using LLM-as-judge."""

    def __init__(self, judge_llm):
        self.judge = judge_llm

    def evaluate_faithfulness(
        self,
        question: str,
        response: str,
        tool_logs: list[dict],
    ) -> float:
        """
        Check if response claims are supported by KB content.

        Returns: 0.0 (hallucinated) to 1.0 (fully faithful)
        """
        # Extract KB content from tool logs
        kb_content = self._extract_kb_content(tool_logs)

        # Extract claims from response
        claims = self._extract_claims(response)

        # Ask judge: is each claim supported by the KB content?
        supported = 0
        for claim in claims:
            judgment = self.judge.complete(
                f"Does this KB content support the claim?\n\n"
                f"KB Content:\n{kb_content}\n\n"
                f"Claim: {claim}\n\n"
                f"Answer ONLY 'yes' or 'no'."
            )
            if "yes" in judgment.lower():
                supported += 1

        return supported / len(claims) if claims else 1.0

    def evaluate_context_relevance(
        self,
        question: str,
        tool_logs: list[dict],
    ) -> float:
        """
        Check if retrieved KB content is relevant to the question.

        Returns: 0.0 (irrelevant) to 1.0 (highly relevant)
        """
        kb_content = self._extract_kb_content(tool_logs)

        judgment = self.judge.complete(
            f"Rate the relevance of this KB content to the question.\n\n"
            f"Question: {question}\n\n"
            f"KB Content:\n{kb_content[:2000]}\n\n"
            f"Rate 0-10 (10 = perfectly relevant). Answer with ONLY a number."
        )

        try:
            score = int(judgment.strip()) / 10
            return min(1.0, max(0.0, score))
        except ValueError:
            return 0.5  # default if judge fails

    def _extract_kb_content(self, tool_logs: list[dict]) -> str:
        """Extract KB content from tool execution logs."""
        content = []
        for log in tool_logs:
            if log["name"] in ("search_knowledge_base", "read_file"):
                result = log.get("result", {})
                if "content" in result:
                    content.append(result["content"])
        return "\n---\n".join(content)

    def _extract_claims(self, response: str) -> list[str]:
        """Extract factual claims from the response."""
        # Simple: split by sentences. Better: use LLM to extract claims.
        sentences = response.split(".")
        return [s.strip() for s in sentences if len(s.strip()) > 20]
```

---

## Layer 3: Citation Verification

### What It Is

Your system mandates citations. But do citations actually point to real content? Does the cited content support the claim?

### Automated Check

```python
# tests/eval/citation_verifier.py
from pathlib import Path
import re

class CitationVerifier:
    """Verifies that citations in agent responses are accurate."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def verify(self, response: str) -> CitationReport:
        """
        Extract citations and verify they point to real content.

        Returns report with:
        - total_citations: number of citations found
        - valid_citations: citations that point to real files
        - invalid_citations: citations with wrong paths or line numbers
        - unsupported_claims: claims without citations
        """
        citations = self._extract_citations(response)
        claims = self._extract_claims_with_citations(response)

        valid = []
        invalid = []

        for citation in citations:
            if self._verify_citation(citation):
                valid.append(citation)
            else:
                invalid.append(citation)

        return CitationReport(
            total_citations=len(citations),
            valid_citations=len(valid),
            invalid_citations=invalid,
            claims_without_citation=[c for c in claims if not c.has_citation],
        )

    def _extract_citations(self, response: str) -> list[Citation]:
        """Extract citations like `data/path/file.md` (linie 12-28)"""
        pattern = r'`(data/[^`]+)`\s*\(linie?\s*(\d+)-(\d+)\)'
        matches = re.findall(pattern, response)
        return [
            Citation(filepath=m[0], line_start=int(m[1]), line_end=int(m[2]))
            for m in matches
        ]

    def _verify_citation(self, citation: Citation) -> bool:
        """Check if the cited file and line range actually exist."""
        file_path = self.data_dir / citation.filepath
        if not file_path.exists():
            return False

        try:
            lines = file_path.read_text().splitlines()
            # Line numbers are 1-indexed
            if citation.line_start < 1 or citation.line_end > len(lines):
                return False
            return True
        except Exception:
            return False
```

---

## Layer 4: Trajectory Evaluation

### What It Is

Evaluates the **tool calls the agent made**, not just the final answer. This catches:

- Agent calls `search_knowledge_base` when it should use `get_repo_map` first
- Agent calls `search_knowledge_base` 5 times with the same query (retry loop)
- Agent calls `edit_file` without calling `read_file` first (violates rules)
- Agent doesn't search at all when it should

### Implementation

```python
# tests/eval/trajectory_eval.py
@dataclass
class TrajectoryRule:
    """A rule that the agent's tool call trajectory must follow."""
    name: str
    check: Callable[[list[str]], bool]  # tool_names -> passed?
    description: str

# Define rules
TRAJECTORY_RULES = [
    TrajectoryRule(
        name="search_before_answer",
        check=lambda tools: "search_knowledge_base" in tools,
        description="Agent must search KB before answering factual questions",
    ),
    TrajectoryRule(
        name="read_before_edit",
        check=lambda tools: (
            "edit_file" not in tools or
            tools.index("read_file") < tools.index("edit_file")
            if "edit_file" in tools else True
        ),
        description="Agent must read file before editing it",
    ),
    TrajectoryRule(
        name="map_before_unknown_file",
        check=lambda tools: (
            "get_repo_map" in tools or
            "read_file" not in tools
        ),
        description="Agent should discover files before reading unknown paths",
    ),
    TrajectoryRule(
        name="no_repeated_search",
        check=lambda tools: len([
            t for t in tools if t == "search_knowledge_base"
        ]) <= 2,
        description="Agent should not search more than twice for the same query",
    ),
    TrajectoryRule(
        name="max_tool_calls",
        check=lambda tools: len(tools) <= 8,
        description="Agent should not make more than 8 tool calls per turn",
    ),
]

class TrajectoryEvaluator:
    def evaluate(self, tool_calls: list[str]) -> list[CheckResult]:
        results = []
        for rule in TRAJECTORY_RULES:
            results.append(CheckResult(
                rule=rule.name,
                passed=rule.check(tool_calls),
                description=rule.description,
            ))
        return results
```

---

## Layer 5: Observability & Tracing

### What It Is

You can't evaluate what you can't see. For LLM agents, you need **traces** — a complete record of what happened during a request.

### What to Capture

```python
# For each turn, record:
trace = {
    "turn_id": "...",
    "session_id": "...",
    "timestamp": "...",
    "user_message": "...",
    "provider": "gemini",
    "model": "gemini-2.5-flash",
    "mode": "assembly",

    # Context assembly
    "context": {
        "system_prompt_tokens": 1200,
        "history_tokens": 3400,
        "user_message_tokens": 50,
        "tool_schemas_tokens": 800,
        "total_tokens": 5450,
    },

    # Tool calls
    "tool_calls": [
        {
            "name": "search_knowledge_base",
            "args": {"query": "Blum|Merivobox"},
            "result_tokens": 2300,
            "duration_ms": 45,
            "truncated": False,
        },
        {
            "name": "read_file",
            "args": {"filepath": "data/04_Okucia_i_Akcesoria/Szuflady_Blum.md"},
            "result_tokens": 4500,
            "duration_ms": 12,
            "truncated": True,  # budget exceeded
        },
    ],

    # LLM calls
    "llm_calls": [
        {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "input_tokens": 5450,
            "output_tokens": 800,
            "duration_ms": 2300,
            "has_tool_calls": True,
        },
        {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "input_tokens": 8550,
            "output_tokens": 600,
            "duration_ms": 1800,
            "has_tool_calls": False,
        },
    ],

    # Response
    "response": {
        "text": "...",
        "has_citations": True,
        "citation_count": 3,
        "tool_calls_made": 2,
    },

    # Budget
    "budget": {
        "tool_tokens_used": 6800,
        "tool_budget_tokens": 6400,
        "was_truncated": True,
    },
}
```

### Tools for Tracing

| Tool                            | Type                 | Cost      | Best For                              |
| ------------------------------- | -------------------- | --------- | ------------------------------------- |
| **Langfuse**                    | Self-hosted or cloud | Free tier | Full traces, evals, prompt management |
| **LangSmith**                   | Cloud                | Free tier | LangChain integration, dataset evals  |
| **Phoenix (Arize)**             | Self-hosted          | Free      | RAG-specific metrics, embeddings viz  |
| **Custom (your prompt_log.md)** | File                 | Free      | Simple, no dependencies               |

Your `prompt_logger.py` already captures tool calls and user messages. The missing pieces are:

- Token usage per tool call
- Truncation events
- Full LLM request/response pairs
- Timing data

---

## Layer 6: A/B Testing Across Providers

### What It Is

You have three providers. Do they give equally good answers? How do you know?

### Implementation

```python
# tests/eval/provider_comparison.py
class ProviderComparison:
    """Run the same questions through different providers and compare."""

    def __init__(self, orchestrators: dict[str, TurnOrchestrator]):
        self.orchestrators = orchestrators  # {"gemini": ..., "anthropic": ..., "mimo": ...}

    def compare(self, questions: list[str]) -> ComparisonReport:
        results = {}
        for provider_name, orchestrator in self.orchestrators.items():
            results[provider_name] = []
            for question in questions:
                output = orchestrator.run(
                    session={"messages": [], "system_prompt": None},
                    turn_input=TurnInput(user_message=question, mode="general"),
                )
                results[provider_name].append({
                    "question": question,
                    "response": output.assistant_message,
                    "tool_calls": [tc.name for tc in output.tool_calls_made],
                    "tokens": output.tokens_used,
                })

        return ComparisonReport(results)
```

### What to Compare

| Metric                 | Why                                      |
| ---------------------- | ---------------------------------------- |
| **Tool call patterns** | Do all providers search the same way?    |
| **Response length**    | Is one provider more verbose?            |
| **Citation count**     | Does one provider cite more than others? |
| **Token usage**        | Is one provider more efficient?          |
| **Response time**      | Which provider is fastest?               |

---

## Recommended Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. DEVELOP — Make a change (prompt, tool, provider)             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ 2. UNIT TESTS — Does the code still work?                       │
│    pytest tests/unit tests/contract tests/integration           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ 3. GOLDEN DATASET — Does the agent still answer correctly?      │
│    python tests/eval/run_eval.py                                │
│    Compare pass rate to baseline (e.g., 85% → 87% = improvement)│
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ 4. TRAJECTORY CHECK — Did the agent use tools correctly?        │
│    python tests/eval/run_trajectory.py                          │
│    Verify: search before answer, read before edit, etc.         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ 5. CITATION VERIFICATION — Are citations accurate?              │
│    python tests/eval/verify_citations.py                        │
│    Check: file exists, line numbers valid, content supports claim│
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ 6. HUMAN REVIEW — Does the answer actually help?                │
│    Open the UI, ask real questions, judge quality               │
│    Record findings in eval dataset for future automation        │
└─────────────────────────────────────────────────────────────────┘
```

---

## What to Evaluate First

Based on your system's critical paths:

| Priority | Evaluation                | Why                                                     |
| -------- | ------------------------- | ------------------------------------------------------- |
| **P0**   | Citation verification     | Citations are mandatory but untested for accuracy       |
| **P0**   | Golden dataset (10 cases) | Catch regressions when you change prompts               |
| **P1**   | Trajectory rules          | Prevent common agent mistakes (edit without read, etc.) |
| **P1**   | Faithfulness metric       | Detect when LLM hallucinates beyond KB content          |
| **P2**   | Provider comparison       | Ensure Gemini and Anthropic give comparable results     |
| **P2**   | Observability tracing     | Debug production issues                                 |

---

## Golden Dataset Starter (10 Cases)

```yaml
# tests/eval/golden_dataset.yaml

# --- Discovery ---
- id: eval-001
  question: 'Jakie pliki są w bazie wiedzy o okuciach?'
  mode: 'general'
  expected:
      must_use_tools: ['get_repo_map']
      must_mention: ['Okucia']

# --- Search + Answer ---
- id: eval-002
  question: 'Jakie są systemy szufladowe Blum?'
  mode: 'general'
  expected:
      must_search: true
      must_cite: true
      must_mention: ['Tandembox', 'Merivobox']

# --- Search + Specific Data ---
- id: eval-003
  question: 'Jaka jest cena Merivobox?'
  mode: 'general'
  expected:
      must_search: true
      must_cite: true

# --- Read + Edit ---
- id: eval-004
  question: 'Dodaj informację o nowym systemie Legrabox Premium do pliku o okuciach Blum'
  mode: 'general'
  expected:
      must_use_tools: ['get_repo_map', 'read_file', 'edit_file']
      trajectory_rules:
          - 'read_before_edit'

# --- Context Files ---
- id: eval-005
  question: 'Podsumuj ten dokument'
  mode: 'general'
  context_files: ['data/00_Dokumenty_Strategiczne/test.md']
  expected:
      must_mention_any_from_file: true

# --- Mode-Specific ---
- id: eval-006
  question: 'Jak zamontować szufladę Merivobox?'
  mode: 'assembly'
  expected:
      must_search: true
      must_mention: ['montaż']

# --- Design Mode ---
- id: eval-007
  question: 'Jakie są ergonomiczne wysokości dla blatów kuchennych?'
  mode: 'design'
  expected:
      must_mention: ['wysokość', 'blat']

# --- Negative: No Hallucination ---
- id: eval-008
  question: 'Jaka jest cena kuchni IKEA Metod?'
  mode: 'general'
  expected:
      forbidden_in_response: ['cena wynosi', 'kosztuje'] # should NOT give a specific price if not in KB

# --- Multi-Tool ---
- id: eval-009
  question: 'Porównaj Tandembox Antaro z Merivobox'
  mode: 'general'
  expected:
      must_search: true
      must_cite: true
      must_mention: ['Tandembox', 'Merivobox']

# --- Edge Case: Empty KB ---
- id: eval-010
  question: 'Jakie są najlepsze praktyki dla montażu szafek?'
  mode: 'assembly'
  expected:
      must_search: true
      # Should answer from training data if KB has nothing
```
