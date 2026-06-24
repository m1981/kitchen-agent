"""
src/agent/turn_orchestrator.py
================================
TurnOrchestrator — manages one complete chat turn lifecycle.

Before this module, the turn lifecycle (context assembly → LLM call → tool
loop → response normalization) was embedded inside ``process_chat_turn`` in
``src/agent/__init__.py``.  This made it impossible to test the orchestration
logic in isolation or swap providers without touching the agent code.

The TurnOrchestrator composes three already-extracted components:
  - **ContextAssembler** (Phase 3) — builds the context window
  - **ToolExecutor** (Phase 2) — runs tools safely
  - **ResponseNormalizer** (Phase 1) — unifies provider response shapes

Design decisions
----------------
* **Provider protocol**: The orchestrator requires a provider that exposes
  ``complete(context)`` and ``complete_with_tools(context, tool_calls,
  tool_results)``.  This is a *new* protocol (``LLMProvider``) distinct
  from the existing ``LLMProvider`` protocol in ``providers/base.py``.
  Existing providers can be adapted to this protocol later; the orchestrator
  does not depend on the old ``process_chat_turn`` interface.
* **Max tool iterations**: A hard cap prevents infinite tool loops when the
  LLM keeps requesting tool calls.  The default is 10; override via
  constructor.
* **Sync tool execution**: Current tool handlers are synchronous.  The
  orchestrator calls ``ToolExecutor.execute_all`` directly (no async).
  When async handlers arrive, the executor can be extended independently.
* **No persistence**: The orchestrator does NOT save sessions, log prompts,
  or count global tokens.  Those are ChatService responsibilities.

Phase 4 scope
-------------
TurnOrchestrator is introduced as a standalone component.  It is NOT yet
wired into ChatService or the existing ``process_chat_turn`` function.
That wiring will happen in a later phase once providers expose the
``LLMProvider`` interface.

Public API
----------
``TurnInput``  — dataclass describing one user turn
``TurnOutput`` — dataclass describing the assistant's response
``TurnOrchestrator.run(session, turn_input)`` — execute one turn
``TurnOrchestrator.stream(session, turn_input)`` — stream one turn (future)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

import structlog
from src.agent.context_assembler import AssembledContext, ContextAssembler
from src.agent.tool_executor import ToolCall, ToolExecutor, ToolResult
from src.logger import log_timing
from src.providers.base import LLMProvider
from src.providers.normalizer import NormalizedResponse, ResponseNormalizer


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TurnInput:
    """Describes one user turn — what the orchestrator needs to proceed."""

    user_message: str
    mode: str = "default"
    system_prompt: str | None = None  # override system prompt (bypass PromptManager)
    note_ids: list[str] = field(default_factory=list)
    file_ids: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    context_files: list[str] = field(default_factory=list)
    use_tools: bool = True
    # Provider routing — when set, overrides the server default for this turn.
    provider: str | None = None
    model: str | None = None


@dataclass
class ToolCallDetail:
    """Full detail of a tool call for history persistence."""

    id: str
    name: str
    arguments: dict
    result_content: str
    is_error: bool = False
    call_tokens: int = 0    # tokens in the tool call arguments
    result_tokens: int = 0  # tokens in the tool result content


@dataclass
class TokenBreakdown:
    """Per-turn token breakdown."""

    user_message_tokens: int = 0
    tool_calls_tokens: int = 0
    tool_results_tokens: int = 0
    assistant_tokens: int = 0
    turn_total: int = 0
    conversation_total: int = 0


@dataclass
class TurnOutput:
    """
    Everything produced by one complete turn execution.
    ChatService reads this — nothing else should need to.
    """
    assistant_message: str
    updated_api_history: list          # full history after turn, ready to persist
    user_turn_id: str                  # stable ID for the user message
    assistant_turn_id: str             # stable ID for the assistant message
    tool_calls_made: list[ToolCall]    # all tool calls in execution order
    tool_logs: list[dict]              # serializable tool log for UI + PromptLogger
    tokens_used: dict                  # {input, output, total} from provider
    provider_name: str = ""            # actual provider used (e.g. "gemini", "anthropic")
    model_name: str = ""               # actual model used (e.g. "gemini-2.5-flash")
    context_slots: dict = field(default_factory=dict)  # observability
    token_breakdown: TokenBreakdown = field(default_factory=TokenBreakdown)  # per-turn token breakdown



# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class MaxToolIterationsError(Exception):
    """Raised when the tool loop exceeds the maximum allowed iterations."""

    def __init__(self, max_iterations: int) -> None:
        self.max_iterations = max_iterations
        super().__init__(
            f"Tool loop exceeded {max_iterations} iterations. "
            "The LLM may be stuck in a tool-calling cycle."
        )


# ---------------------------------------------------------------------------
# TurnOrchestrator
# ---------------------------------------------------------------------------

class TurnOrchestrator:
    """
    Manages one complete chat turn lifecycle.

    Lifecycle:
    1. Assemble context (via ContextAssembler)
    2. Call LLM (via LLMProvider)
    3. Normalize response (via ResponseNormalizer)
    4. If tool calls: execute tools, feed results back, repeat
    5. Return TurnOutput

    Does NOT: persist sessions, log prompts, count global tokens.
    Those are ChatService responsibilities.
    """

    def __init__(
        self,
        context_assembler: ContextAssembler,
        tool_executor: ToolExecutor,
        provider: LLMProvider,
        response_normalizer: ResponseNormalizer,
        provider_name: str = "gemini",
        max_tool_iterations: int = 10,
        tool_registry: Any | None = None,
        token_counter: Any | None = None,
        context_budget: Any | None = None,
    ) -> None:
        self._ctx = context_assembler
        self._tools = tool_executor
        self._provider = provider
        self._normalizer = response_normalizer
        self._provider_name = provider_name
        self._max_tool_iterations = max_tool_iterations
        self._tool_registry = tool_registry
        self._token_counter = token_counter
        self._context_budget = context_budget
        self._log = structlog.get_logger(__name__)

    # ── Shared helpers ──────────────────────────────────────────────────

    def _execute_tool_calls(
        self,
        normalized: NormalizedResponse,
        tool_details: list[ToolCallDetail],
    ) -> tuple[list[ToolCall], list[ToolResult]]:
        """
        Execute tool calls and record details for history.

        Returns:
            Tuple of (tool_calls, tool_results) for feeding back to the LLM.
        """
        tool_results = self._tools.execute_all(normalized.tool_calls)

        for tc, tr in zip(normalized.tool_calls, tool_results):
            tool_details.append(ToolCallDetail(
                id=tc.id,
                name=tc.name,
                arguments=tc.arguments,
                result_content=tr.content,
                is_error=tr.is_error,
                call_tokens=tc.token_count,
                result_tokens=tr.token_count,
            ))

        return normalized.tool_calls, tool_results

    @staticmethod
    def _build_output_from_details(
        tool_details: list[ToolCallDetail],
    ) -> tuple[list[ToolCall], list[dict]]:
        """
        Convert internal ToolCallDetail list to serializable forms.

        Returns:
            Tuple of (tool_calls_made_objects, tool_logs) for TurnOutput.
        """
        calls = [
            ToolCall(id=d.id, name=d.name, arguments=d.arguments, token_count=d.call_tokens)
            for d in tool_details
        ]
        logs = [{
            "name": d.name,
            "args": d.arguments,
            "result": ({"content": d.result_content}
                       if not d.is_error
                       else {"error": d.result_content}),
            "token_count": d.call_tokens + d.result_tokens,
        } for d in tool_details]
        return calls, logs

    # ── Tool budget enforcement ────────────────────────────────────────

    def _get_tool_budget_tokens(self) -> int | None:
        """Return the tool budget in tokens, or None if no budget configured."""
        if self._context_budget is None or self._token_counter is None:
            return None
        from src.agent.context_assembler import ContextSlot
        return self._context_budget.tokens_for(ContextSlot.TOOL_RESULTS)

    def _count_and_truncate_tool_results(
        self,
        tool_results: list[ToolResult],
        tool_tokens_used: int,
        tool_budget_tokens: int,
    ) -> tuple[list[ToolResult], int, bool]:
        """
        Count tokens for tool results and truncate if over budget.

        When a result is truncated, remaining results in the batch are
        zeroed out (replaced with a short message) to prevent them from
        inflating the token count beyond the budget.

        Returns:
            (possibly_truncated_results, new_tool_tokens_used, was_truncated)
        """
        truncated = False
        warning_suffix = (
            "\n\n... [truncated: content above is partial. "
            "Answer from what you have. If you need more detail on a specific file, "
            "use read_file on the most relevant file path shown above.]"
        )
        warning_tokens = self._token_counter.count(warning_suffix)

        for i, tr in enumerate(tool_results):
            if truncated:
                # Previous result was truncated — zero out remaining results
                tr.content = "[skipped: context budget exceeded]"
                tool_tokens_used += self._token_counter.count(tr.content)
                continue

            tokens = self._token_counter.count(tr.content)
            remaining_budget = tool_budget_tokens - tool_tokens_used

            if tokens > remaining_budget and remaining_budget > 0:
                # Reserve space for the warning text
                truncate_budget = max(0, remaining_budget - warning_tokens)
                original_content = tr.content
                tr.content = self._token_counter.trim_to(tr.content, truncate_budget)
                tr.content += warning_suffix
                tokens = self._token_counter.count(tr.content)
                truncated = True
                self._log.warning(
                    "tool_result_truncated",
                    tool_name=tr.name,
                    original_tokens=self._token_counter.count(original_content),
                    truncated_tokens=tokens,
                    remaining_budget=remaining_budget,
                )

            tool_tokens_used += tokens

        return tool_results, tool_tokens_used, truncated

    def _build_truncation_summary(self, tool_details: list[ToolCallDetail]) -> str:
        """
        Build a synthetic response when the LLM returns no text after
        tool results were truncated.

        Extracts key information from the tool results to give the user
        a useful answer even when the LLM didn't produce one.
        """
        if not tool_details:
            return "Przepraszam, nie udało mi się wygenerować odpowiedzi. Spróbuj zadać bardziej konkretne pytanie."

        # Get the last tool result (the one that was truncated)
        last_detail = tool_details[-1]
        result_content = last_detail.result_content

        # Extract file paths and line numbers from the result
        lines = result_content.split("\n")
        file_paths: list[str] = []
        key_findings: list[str] = []

        for line in lines:
            # File headers: === data/... ===
            if line.startswith("=== ") and line.endswith(" ==="):
                file_path = line[4:-4].strip()
                if file_path not in file_paths:
                    file_paths.append(file_path)
            # Matching lines with >> marker
            elif line.strip().startswith(">>") and ":" in line:
                # Extract the content after line number
                parts = line.split(":", 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    if len(content) > 20:  # Skip very short lines
                        key_findings.append(content[:100])

        # Build the response
        response_parts = [
            "Na podstawie przeszukania bazy wiedzy znalazłem informacje w nastêpuj¹cych plikach:",
            ""
        ]

        if file_paths:
            for fp in file_paths[:5]:  # Show top 5 files
                response_parts.append(f"- `{fp}`")
            response_parts.append("")

        if key_findings:
            response_parts.append("Kluczowe znaleziska:")
            for i, finding in enumerate(key_findings[:5], 1):
                response_parts.append(f"{i}. {finding}...")
            response_parts.append("")

        response_parts.extend([
            "---",
            "_Uwaga: Wyniki zostały ograniczone limitem tokenów. "
            "Aby uzyskać pełną odpowiedź, zadaj bardziej szczegółowe pytanie "
            "lub użyj `read_file` na konkretnym pliku z listy powyżej._"
        ])

        return "\n".join(response_parts)

    def _check_citation_compliance(
        self,
        response: str,
        tool_details: list[ToolCallDetail],
    ) -> None:
        """
        Check if response includes citations when tools were used.
        Logs a warning if citations are missing — does NOT modify the response.
        """
        response_lower = response.lower()
        has_citation_section = "## źródła" in response_lower
        has_inline_marker = "[1]" in response or "[2]" in response

        if not has_citation_section and not has_inline_marker:
            # Extract tool names used
            tools_used = list(set(d.name for d in tool_details))
            self._log.warning(
                "citation_compliance_missing",
                tools_used=tools_used,
                response_length=len(response),
                message=(
                    "Response uses knowledge base tools but has no citations. "
                    "Expected ## Źródła section with [1] inline markers."
                ),
            )
        elif not has_citation_section:
            self._log.warning(
                "citation_compliance_partial",
                has_inline=has_inline_marker,
                has_section=has_citation_section,
                message="Response has inline markers but missing ## Źródła section.",
            )

    # ── run() ────────────────────────────────────────────────────────────

    def run(
        self,
        session: dict,
        turn_input: TurnInput,
    ) -> TurnOutput:
        """
        Execute one complete chat turn.

        Args:
            session:     Session-like dict with a ``messages`` key.
            turn_input:  Describes the user's turn.

        Returns:
            TurnOutput with assistant message, tool calls made,
            token usage, and context slot observability.

        Raises:
            MaxToolIterationsError: if the tool loop exceeds the cap.
        """
        # ── 1. Resolve provider for this turn ───────────────────────────
        if turn_input.provider:
            from src.providers.base import get_provider
            provider = get_provider(
                provider_name=turn_input.provider,
                model_override=turn_input.model,
            )
            provider_name = turn_input.provider
        else:
            provider = self._provider
            provider_name = self._provider_name

        actual_model = getattr(provider, "_model", "unknown")
        self._log.info(
            "orchestrator_provider_resolved",
            provider=provider_name,
            model=actual_model,
            override_used=bool(turn_input.provider),
        )

        # ── 2. Assemble context ─────────────────────────────────────────
        with log_timing(self._log, "orchestrator_context_assembled"):
            context = self._ctx.assemble(
                session=session,
                mode=turn_input.mode,
                user_message=turn_input.user_message,
                note_ids=turn_input.note_ids or None,
                file_ids=turn_input.file_ids or None,
            )

        # Override system prompt if provided in TurnInput
        if turn_input.system_prompt is not None:
            context.system_prompt = turn_input.system_prompt

        # Propagate images and context_files from TurnInput to context
        # so providers can access them via the LLMProvider interface.
        context.images = turn_input.images or []
        context.context_files = turn_input.context_files or []

        # Inject tool schemas from registry
        if self._tool_registry is not None and turn_input.use_tools:
            context.tool_schemas = self._tool_registry.schemas_for_provider(
                provider=provider_name,
            )

        self._log.info(
            "orchestrator_llm_call_start",
            provider=provider_name,
            model=actual_model,
            has_system_prompt=bool(context.system_prompt),
            has_images=bool(context.images),
            has_context_files=bool(context.context_files),
            tool_schemas_count=len(context.tool_schemas) if context.tool_schemas else 0,
            use_tools=turn_input.use_tools,
        )

        # ── 3. Call LLM ────────────────────────────────────────────────
        with log_timing(self._log, "orchestrator_llm_call_complete") as timing:
            raw_response = provider.complete(context)
            normalized = self._normalizer.normalize(raw_response, provider_name)
        timing["has_tool_calls"] = normalized.has_tool_calls

        # ── 4. Agentic tool loop ───────────────────────────────────────
        tool_calls_made: list[str] = []
        tool_details: list[ToolCallDetail] = []
        iterations = 0
        tool_tokens_used = 0
        tool_budget_tokens = self._get_tool_budget_tokens()

        # Edge case: LLM returned tool_calls but use_tools=False.
        # This can happen when the model hallucinates tools (e.g. mimo).
        # Do NOT execute tools — just log and return whatever text was produced.
        if normalized.has_tool_calls and not turn_input.use_tools:
            self._log.warning(
                "orchestrator_unexpected_tool_calls",
                tool_calls=[tc.name for tc in normalized.tool_calls],
                message="use_tools=False but LLM returned tool_calls. "
                        "Ignoring tool calls.",
            )
            # Skip tool execution — return text-only response
            normalized = NormalizedResponse(
                text=normalized.text,
                has_tool_calls=False,
                tool_calls=[],
                usage=normalized.usage,
                raw=normalized.raw,
            )

        while normalized.has_tool_calls:
            iterations += 1
            if iterations > self._max_tool_iterations:
                raise MaxToolIterationsError(self._max_tool_iterations)

            self._log.info(
                "orchestrator_tool_iteration",
                iteration=iterations,
                tool_calls=[tc.name for tc in normalized.tool_calls],
            )

            # Execute tools and record details
            with log_timing(self._log, "orchestrator_tools_executed") as timing:
                calls, results = self._execute_tool_calls(normalized, tool_details)
            timing["tools_count"] = len(results)

            # ── Token budget enforcement ──────────────────────────────
            was_truncated = False
            if tool_budget_tokens is not None:
                results, tool_tokens_used, was_truncated = (
                    self._count_and_truncate_tool_results(
                        results, tool_tokens_used, tool_budget_tokens,
                    )
                )
                # Update tool_details with possibly truncated content
                for detail, tr in zip(tool_details[-len(results):], results):
                    detail.result_content = tr.content

                self._log.info(
                    "orchestrator_tool_budget",
                    tool_tokens_used=tool_tokens_used,
                    tool_budget_tokens=tool_budget_tokens,
                    was_truncated=was_truncated,
                )

            tool_calls_made.extend(
                tc.name for tc in normalized.tool_calls
            )

            # If budget exceeded, stop the tool loop
            if was_truncated:
                self._log.warning(
                    "orchestrator_tool_budget_exceeded",
                    tool_tokens_used=tool_tokens_used,
                    tool_budget_tokens=tool_budget_tokens,
                    message="Tool results exceeded budget. Stopping tool loop.",
                )
                # Force LLM to produce a text response from partial results
                raw_response = provider.complete_with_tools(
                    context, calls, results,
                )
                normalized = self._normalizer.normalize(raw_response, provider_name)
                
                # If LLM returned tool calls instead of text, force a synthetic response
                if normalized.has_tool_calls or not normalized.text.strip():
                    self._log.warning(
                        "orchestrator_forcing_text_response",
                        had_tool_calls=normalized.has_tool_calls,
                        had_text=bool(normalized.text.strip()),
                    )
                    # Build a summary from the tool results we have
                    result_summary = self._build_truncation_summary(tool_details)
                    normalized = NormalizedResponse(
                        text=result_summary,
                        has_tool_calls=False,
                        tool_calls=[],
                        usage=normalized.usage,
                        raw=normalized.raw,
                    )
                else:
                    # LLM returned text — use it, but don't allow more tool calls
                    normalized = NormalizedResponse(
                        text=normalized.text,
                        has_tool_calls=False,
                        tool_calls=[],
                        usage=normalized.usage,
                        raw=normalized.raw,
                    )
            else:
                # Feed results back to LLM normally
                self._log.info("orchestrator_feeding_tool_results_to_llm")
                raw_response = provider.complete_with_tools(
                    context, calls, results,
                )
                normalized = self._normalizer.normalize(raw_response, provider_name)

        # 4. Build output
        tool_calls_made_objects, tool_logs = self._build_output_from_details(tool_details)

        # Build updated_api_history from session messages + new turns
        # Using provider-agnostic common format
        updated_api_history: list = list(session.get("messages", []))
        
        # User message
        user_tokens = self._token_counter.count(turn_input.user_message) if self._token_counter else 0
        updated_api_history.append({"role": "user", "content": turn_input.user_message, "token_count": user_tokens})
        
        # Tool call/response pairs
        tool_calls_tokens = 0
        tool_results_tokens = 0
        for detail in tool_details:
            tool_calls_tokens += detail.call_tokens
            tool_results_tokens += detail.result_tokens
            # Assistant tool call message
            updated_api_history.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": detail.id,
                    "name": detail.name,
                    "arguments": detail.arguments,
                }],
                "token_count": detail.call_tokens,
            })
            # Tool response message
            updated_api_history.append({
                "role": "tool",
                "tool_call_id": detail.id,
                "content": detail.result_content,
                "token_count": detail.result_tokens,
            })
        
        # Assistant response
        assistant_tokens = self._token_counter.count(normalized.text) if self._token_counter else 0
        updated_api_history.append({
            "role": "assistant",
            "content": normalized.text,
            "token_count": assistant_tokens,
        })

        # Generate stable turn IDs
        user_turn_id = str(uuid.uuid4())
        assistant_turn_id = str(uuid.uuid4())

        # Capture actual model used — provider._model holds the resolved value.
        actual_model = getattr(provider, "_model", "") or ""

        # Record tool token usage for observability
        if tool_budget_tokens is not None:
            from src.agent.context_assembler import ContextSlot
            context.slots_used[ContextSlot.TOOL_RESULTS] = tool_tokens_used

        # ── 5. Citation compliance check ───────────────────────────────
        if tool_details:
            self._check_citation_compliance(normalized.text, tool_details)

        # ── 6. Calculate token breakdown ───────────────────────────────
        turn_total = user_tokens + tool_calls_tokens + tool_results_tokens + assistant_tokens

        # Calculate conversation total (sum of all message token_counts)
        conversation_total = 0
        for msg in updated_api_history:
            if isinstance(msg, dict):
                conversation_total += msg.get("token_count", 0)

        token_breakdown = TokenBreakdown(
            user_message_tokens=user_tokens,
            tool_calls_tokens=tool_calls_tokens,
            tool_results_tokens=tool_results_tokens,
            assistant_tokens=assistant_tokens,
            turn_total=turn_total,
            conversation_total=conversation_total,
        )

        return TurnOutput(
            assistant_message=normalized.text,
            updated_api_history=updated_api_history,
            user_turn_id=user_turn_id,
            assistant_turn_id=assistant_turn_id,
            tool_calls_made=tool_calls_made_objects,
            tool_logs=tool_logs,
            tokens_used=normalized.usage,
            provider_name=provider_name,
            model_name=actual_model,
            context_slots=context.slots_used,
            token_breakdown=token_breakdown,
        )

    def stream(
        self,
        session: dict,
        turn_input: TurnInput,
    ) -> Iterator[dict]:
        """
        Stream one complete chat turn.

        Yields event dicts:
          - {"type": "text_delta", "content": "..."}
          - {"type": "tool_call", "name": "...", "args": {...}, "id": "..."}
          - {"type": "tool_result", "name": "...", "result": {...}, "id": "..."}
          - {"type": "done", "provider": "...", "model": "...", ...}

        Handles recursive tool loops (same as run()) — if the LLM makes
        tool calls after stream_with_tools(), they are executed in the
        next iteration.
        """
        # ── 1. Resolve provider ───────────────────────────────────────
        if turn_input.provider:
            from src.providers.base import get_provider
            provider = get_provider(
                provider_name=turn_input.provider,
                model_override=turn_input.model,
            )
            provider_name = turn_input.provider
        else:
            provider = self._provider
            provider_name = self._provider_name

        actual_model = getattr(provider, "_model", "unknown")

        self._log.info(
            "orchestrator_stream_start",
            provider=provider_name,
            model=actual_model,
        )

        # ── 2. Assemble context ───────────────────────────────────────
        context = self._ctx.assemble(
            session=session,
            mode=turn_input.mode,
            user_message=turn_input.user_message,
            note_ids=turn_input.note_ids or None,
            file_ids=turn_input.file_ids or None,
        )

        if turn_input.system_prompt is not None:
            context.system_prompt = turn_input.system_prompt

        context.images = turn_input.images or []
        context.context_files = turn_input.context_files or []

        if self._tool_registry is not None and turn_input.use_tools:
            context.tool_schemas = self._tool_registry.schemas_for_provider(
                provider=provider_name,
            )

        # ── 3. Stream LLM response + recursive tool loop ─────────────
        full_text = ""
        tool_calls_made: list[str] = []
        tool_details: list[ToolCallDetail] = []
        iterations = 0
        tool_tokens_used = 0
        tool_budget_tokens = self._get_tool_budget_tokens()

        # Generate stable turn IDs
        user_turn_id = str(uuid.uuid4())
        assistant_turn_id = str(uuid.uuid4())

        # First LLM streaming call
        normalized = None
        for event in self._stream_and_collect(
            provider, context, provider_name, full_text,
        ):
            if event["type"] == "__normalized__":
                normalized = event["response"]
            else:
                yield event  # forward text_delta

        if normalized:
            full_text += normalized.text

        # Recursive tool loop (mirrors run() logic)
        while normalized and normalized.has_tool_calls and turn_input.use_tools:
            iterations += 1
            if iterations > self._max_tool_iterations:
                raise MaxToolIterationsError(self._max_tool_iterations)

            self._log.info(
                "orchestrator_stream_tool_iteration",
                iteration=iterations,
                tool_calls=[tc.name for tc in normalized.tool_calls],
            )

            # Yield tool_call events
            for tc in normalized.tool_calls:
                tool_calls_made.append(tc.name)
                yield {
                    "type": "tool_call",
                    "name": tc.name,
                    "args": tc.arguments,
                    "id": tc.id,
                }

            # Execute tools and record details
            calls, results = self._execute_tool_calls(normalized, tool_details)

            # ── Token budget enforcement ──────────────────────────────
            was_truncated = False
            if tool_budget_tokens is not None:
                results, tool_tokens_used, was_truncated = (
                    self._count_and_truncate_tool_results(
                        results, tool_tokens_used, tool_budget_tokens,
                    )
                )
                # Update tool_details with possibly truncated content
                for detail, tr in zip(tool_details[-len(results):], results):
                    detail.result_content = tr.content

            # Yield tool_result events
            for tc, tr in zip(calls, results):
                yield {
                    "type": "tool_result",
                    "name": tc.name,
                    "args": tc.arguments,
                    "result": {"content": tr.content} if not tr.is_error else {"error": tr.content},
                    "id": tc.id,
                }

            # If budget exceeded, stop the tool loop
            if was_truncated:
                self._log.warning(
                    "orchestrator_stream_tool_budget_exceeded",
                    tool_tokens_used=tool_tokens_used,
                    tool_budget_tokens=tool_budget_tokens,
                )
                # Force LLM to produce text from partial results
                normalized = None
                for event in self._stream_and_collect_with_tools(
                    provider, context, calls, results, provider_name, full_text,
                ):
                    if event["type"] == "__normalized__":
                        normalized = event["response"]
                    else:
                        yield event
                
                if normalized:
                    full_text += normalized.text
                    
                    # If LLM returned tool calls instead of text, force synthetic response
                    if normalized.has_tool_calls or not normalized.text.strip():
                        self._log.warning(
                            "orchestrator_stream_forcing_text_response",
                            had_tool_calls=normalized.has_tool_calls,
                            had_text=bool(normalized.text.strip()),
                        )
                        result_summary = self._build_truncation_summary(tool_details)
                        full_text = result_summary
                        yield {"type": "text_delta", "content": result_summary}
                else:
                    # No normalized response at all — use synthetic
                    result_summary = self._build_truncation_summary(tool_details)
                    full_text = result_summary
                    yield {"type": "text_delta", "content": result_summary}
                
                # Override: no more tool calls
                normalized = NormalizedResponse(
                    text=full_text,
                    has_tool_calls=False,
                    tool_calls=[],
                    usage=normalized.usage if normalized else {},
                    raw=normalized,
                ) if normalized else None
            else:
                # Continue streaming after tools — next iteration
                normalized = None
                for event in self._stream_and_collect_with_tools(
                    provider, context, calls, results, provider_name, full_text,
                ):
                    if event["type"] == "__normalized__":
                        normalized = event["response"]
                    else:
                        yield event  # forward text_delta

                if normalized:
                    full_text += normalized.text

        # ── 4. Done event ─────────────────────────────────────────────
        # Calculate token breakdown for streaming
        user_tokens = self._token_counter.count(turn_input.user_message) if self._token_counter else 0
        tool_calls_tokens = sum(d.call_tokens for d in tool_details)
        tool_results_tokens = sum(d.result_tokens for d in tool_details)
        assistant_tokens = self._token_counter.count(full_text) if self._token_counter else 0
        turn_total = user_tokens + tool_calls_tokens + tool_results_tokens + assistant_tokens

        yield {
            "type": "done",
            "provider": provider_name,
            "model": actual_model,
            "user_turn_id": user_turn_id,
            "assistant_turn_id": assistant_turn_id,
            "tool_calls_made": tool_calls_made,
            "tool_details": tool_details,  # for history building
            "token_breakdown": {
                "user_message_tokens": user_tokens,
                "tool_calls_tokens": tool_calls_tokens,
                "tool_results_tokens": tool_results_tokens,
                "assistant_tokens": assistant_tokens,
                "turn_total": turn_total,
            },
        }

    def _stream_and_collect(
        self,
        provider: LLMProvider,
        context: AssembledContext,
        provider_name: str,
        _accumulated: str,
    ) -> Iterator[dict]:
        """
        Stream a single LLM call, yielding text_delta events in real-time.

        After all chunks are consumed, yields a special ``__normalized__``
        event containing the final ``NormalizedResponse``.  The caller
        uses ``yield from`` to forward text deltas and receives the
        normalized response as the generator's return value.

        Yields:
            {"type": "text_delta", "content": "..."} for each chunk.
            {"type": "__normalized__", "response": NormalizedResponse} at the end.
        """
        final_message: Any = None
        last_raw_chunk: Any = None
        accumulated_text = ""

        for chunk in provider.stream(context):
            # Providers yield __final_message__ with the complete response
            if isinstance(chunk, dict) and chunk.get("type") == "__final_message__":
                final_message = chunk["message"]
                continue

            last_raw_chunk = chunk
            text_delta = self._normalizer.normalize_chunk(chunk, provider_name)
            if text_delta:
                accumulated_text += text_delta
                yield {"type": "text_delta", "content": text_delta}

        # Normalize the final response
        message_to_normalize = final_message if final_message is not None else last_raw_chunk
        if message_to_normalize is not None:
            normalized = self._normalizer.normalize(message_to_normalize, provider_name)
            if accumulated_text:
                normalized.text = accumulated_text
            yield {"type": "__normalized__", "response": normalized}

    def _stream_and_collect_with_tools(
        self,
        provider: LLMProvider,
        context: AssembledContext,
        tool_calls: list[ToolCall],
        tool_results: list[ToolResult],
        provider_name: str,
        _accumulated: str,
    ) -> Iterator[dict]:
        """
        Stream an LLM call after tool execution, yielding text_delta events.

        Same pattern as _stream_and_collect but calls stream_with_tools().

        Yields:
            {"type": "text_delta", "content": "..."} for each chunk.
            {"type": "__normalized__", "response": NormalizedResponse} at the end.
        """
        final_message: Any = None
        last_raw_chunk: Any = None
        accumulated_text = ""

        for chunk in provider.stream_with_tools(context, tool_calls, tool_results):
            if isinstance(chunk, dict) and chunk.get("type") == "__final_message__":
                final_message = chunk["message"]
                continue

            last_raw_chunk = chunk
            text_delta = self._normalizer.normalize_chunk(chunk, provider_name)
            if text_delta:
                accumulated_text += text_delta
                yield {"type": "text_delta", "content": text_delta}

        message_to_normalize = final_message if final_message is not None else last_raw_chunk
        if message_to_normalize is not None:
            normalized = self._normalizer.normalize(message_to_normalize, provider_name)
            if accumulated_text:
                normalized.text = accumulated_text
            yield {"type": "__normalized__", "response": normalized}
