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
    session_id: str = ""              # session identifier (used by ChatService, ignored by orchestrator)
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

    Raw facts only — ChatService owns history building and persistence.
    """
    assistant_message: str
    user_turn_id: str                  # stable ID for the user message
    assistant_turn_id: str             # stable ID for the assistant message
    tool_calls_made: list[ToolCall]    # all tool calls in execution order
    tool_details: list[ToolCallDetail] # raw tool call details for history building
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

    # ── Provider + context helpers ──────────────────────────────────────

    def _resolve_provider(
        self,
        turn_input: TurnInput,
    ) -> tuple[LLMProvider, str]:
        """Resolve provider for this turn (override vs default)."""
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
        return provider, provider_name

    def _setup_context(
        self,
        session: dict,
        turn_input: TurnInput,
        provider_name: str,
    ) -> AssembledContext:
        """Assemble context window and inject tool schemas."""
        with log_timing(self._log, "orchestrator_context_assembled"):
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

        return context

    # ── Unified turn execution ───────────────────────────────────────────

    def _execute_turn(
        self,
        session: dict,
        turn_input: TurnInput,
        *,
        streaming: bool = False,
    ) -> Iterator[dict]:
        """
        Single implementation of the turn lifecycle.

        A generator that yields events.  ``run()`` collects them;
        ``stream()`` forwards them to the caller.

        Events yielded:
          - {"type": "text_delta", "content": "..."}  (streaming only)
          - {"type": "tool_call", "name": "...", ...}
          - {"type": "tool_result", "name": "...", ...}
          - {"type": "__done__", "text": ..., "tool_details": ...}
        """
        # ── 1. Resolve provider + context ───────────────────────────────
        provider, provider_name = self._resolve_provider(turn_input)
        actual_model = getattr(provider, "_model", "unknown")
        context = self._setup_context(session, turn_input, provider_name)

        self._log.info(
            "orchestrator_llm_call_start",
            provider=provider_name,
            model=actual_model,
            has_system_prompt=bool(context.system_prompt),
            tool_schemas_count=len(context.tool_schemas) if context.tool_schemas else 0,
            use_tools=turn_input.use_tools,
            streaming=streaming,
        )

        # ── 2. Initial LLM call ─────────────────────────────────────────
        normalized: NormalizedResponse | None = None

        if streaming:
            for event in self._stream_and_collect(
                provider, context, provider_name,
            ):
                if event["type"] == "__normalized__":
                    normalized = event["response"]
                else:
                    yield event  # text_delta
        else:
            with log_timing(self._log, "orchestrator_llm_call_complete"):
                raw_response = provider.complete(context)
                normalized = self._normalizer.normalize(raw_response, provider_name)

        assert normalized is not None, "LLM returned no response"

        # ── 3. Guard: hallucinated tools when use_tools=False ───────────
        if normalized.has_tool_calls and not turn_input.use_tools:
            self._log.warning(
                "orchestrator_unexpected_tool_calls",
                tool_calls=[tc.name for tc in normalized.tool_calls],
                message="use_tools=False but LLM returned tool_calls. Ignoring.",
            )
            normalized = NormalizedResponse(
                text=normalized.text,
                has_tool_calls=False,
                tool_calls=[],
                usage=normalized.usage,
                raw=normalized.raw,
            )

        # ── 4. Agentic tool loop ────────────────────────────────────────
        tool_calls_made: list[str] = []
        tool_details: list[ToolCallDetail] = []
        iterations = 0
        tool_tokens_used = 0
        tool_budget_tokens = self._get_tool_budget_tokens()

        while normalized.has_tool_calls:
            iterations += 1
            if iterations > self._max_tool_iterations:
                raise MaxToolIterationsError(self._max_tool_iterations)

            self._log.info(
                "orchestrator_tool_iteration",
                iteration=iterations,
                tool_calls=[tc.name for tc in normalized.tool_calls],
            )

            # Execute tools
            with log_timing(self._log, "orchestrator_tools_executed"):
                calls, results = self._execute_tool_calls(normalized, tool_details)

            # Token budget enforcement
            was_truncated = False
            if tool_budget_tokens is not None:
                results, tool_tokens_used, was_truncated = (
                    self._count_and_truncate_tool_results(
                        results, tool_tokens_used, tool_budget_tokens,
                    )
                )
                for detail, tr in zip(tool_details[-len(results):], results):
                    detail.result_content = tr.content

            # Yield tool events
            for tc, tr in zip(calls, results):
                tool_calls_made.append(tc.name)
                yield {
                    "type": "tool_call",
                    "name": tc.name,
                    "args": tc.arguments,
                    "id": tc.id,
                }
                yield {
                    "type": "tool_result",
                    "name": tc.name,
                    "args": tc.arguments,
                    "result": {"content": tr.content} if not tr.is_error else {"error": tr.content},
                    "id": tc.id,
                }

            # Feed results back to LLM
            if was_truncated:
                self._log.warning(
                    "orchestrator_tool_budget_exceeded",
                    tool_tokens_used=tool_tokens_used,
                    tool_budget_tokens=tool_budget_tokens,
                )
                normalized = self._force_text_response(
                    provider, context, calls, results,
                    provider_name, tool_details, streaming,
                )
            else:
                self._log.info("orchestrator_feeding_tool_results_to_llm")
                normalized = None
                if streaming:
                    for event in self._stream_and_collect_with_tools(
                        provider, context, calls, results, provider_name,
                    ):
                        if event["type"] == "__normalized__":
                            normalized = event["response"]
                        else:
                            yield event
                else:
                    raw = provider.complete_with_tools(context, calls, results)
                    normalized = self._normalizer.normalize(raw, provider_name)

        # ── 5. Citation compliance check ────────────────────────────────
        if tool_details:
            self._check_citation_compliance(normalized.text, tool_details)

        # ── 6. Record tool token usage for observability ────────────────
        if tool_budget_tokens is not None:
            from src.agent.context_assembler import ContextSlot
            context.slots_used[ContextSlot.TOOL_RESULTS] = tool_tokens_used

        # ── 7. Token breakdown ──────────────────────────────────────────
        user_tokens = self._token_counter.count(turn_input.user_message) if self._token_counter else 0
        tool_calls_tokens = sum(d.call_tokens for d in tool_details)
        tool_results_tokens = sum(d.result_tokens for d in tool_details)
        assistant_tokens = self._token_counter.count(normalized.text) if self._token_counter else 0

        token_breakdown = TokenBreakdown(
            user_message_tokens=user_tokens,
            tool_calls_tokens=tool_calls_tokens,
            tool_results_tokens=tool_results_tokens,
            assistant_tokens=assistant_tokens,
            turn_total=user_tokens + tool_calls_tokens + tool_results_tokens + assistant_tokens,
        )

        # ── 8. Yield done signal ────────────────────────────────────────
        yield {
            "type": "__done__",
            "text": normalized.text,
            "usage": normalized.usage,
            "tool_calls_made": tool_calls_made,
            "tool_details": tool_details,
            "token_breakdown": token_breakdown,
            "context_slots": context.slots_used,
            "provider_name": provider_name,
            "model_name": getattr(provider, "_model", "") or "",
        }

    def _force_text_response(
        self,
        provider: LLMProvider,
        context: AssembledContext,
        calls: list[ToolCall],
        results: list[ToolResult],
        provider_name: str,
        tool_details: list[ToolCallDetail],
        streaming: bool,
    ) -> NormalizedResponse:
        """Force LLM to produce text after budget truncation."""
        normalized: NormalizedResponse | None = None

        if streaming:
            for event in self._stream_and_collect_with_tools(
                provider, context, calls, results, provider_name,
            ):
                if event["type"] == "__normalized__":
                    normalized = event["response"]
                # text_delta events are silently consumed here
        else:
            raw = provider.complete_with_tools(context, calls, results)
            normalized = self._normalizer.normalize(raw, provider_name)

        if normalized and normalized.has_tool_calls:
            self._log.warning(
                "orchestrator_forcing_text_response",
                had_tool_calls=True,
            )

        if normalized and normalized.text.strip() and not normalized.has_tool_calls:
            return NormalizedResponse(
                text=normalized.text,
                has_tool_calls=False,
                tool_calls=[],
                usage=normalized.usage,
                raw=normalized.raw,
            )

        # LLM returned no usable text — build synthetic summary
        result_summary = self._build_truncation_summary(tool_details)
        return NormalizedResponse(
            text=result_summary,
            has_tool_calls=False,
            tool_calls=[],
            usage=normalized.usage if normalized else {},
            raw=normalized,
        )

    # ── Public API: run() and stream() ───────────────────────────────────

    def run(
        self,
        session: dict,
        turn_input: TurnInput,
    ) -> TurnOutput:
        """
        Execute one complete chat turn (non-streaming).

        Thin wrapper over ``_execute_turn`` that collects all events
        and builds a ``TurnOutput``.

        Raises:
            MaxToolIterationsError: if the tool loop exceeds the cap.
        """
        user_turn_id = str(uuid.uuid4())
        assistant_turn_id = str(uuid.uuid4())

        result: dict | None = None
        for event in self._execute_turn(session, turn_input, streaming=False):
            if event["type"] == "__done__":
                result = event

        assert result is not None, "Turn execution completed without __done__ event"

        tool_calls_made_objects, tool_logs = self._build_output_from_details(
            result["tool_details"]
        )

        return TurnOutput(
            assistant_message=result["text"],
            user_turn_id=user_turn_id,
            assistant_turn_id=assistant_turn_id,
            tool_calls_made=tool_calls_made_objects,
            tool_details=result["tool_details"],
            tool_logs=tool_logs,
            tokens_used=result["usage"],
            provider_name=result["provider_name"],
            model_name=result["model_name"],
            context_slots=result["context_slots"],
            token_breakdown=result["token_breakdown"],
        )

    def stream(
        self,
        session: dict,
        turn_input: TurnInput,
    ) -> Iterator[dict]:
        """
        Stream one complete chat turn.

        Thin wrapper over ``_execute_turn`` that forwards events
        as SSE-compatible dicts.

        Yields:
          - {"type": "text_delta", "content": "..."}
          - {"type": "tool_call", "name": "...", "args": {...}, "id": "..."}
          - {"type": "tool_result", "name": "...", "result": {...}, "id": "..."}
          - {"type": "done", "provider": "...", "model": "...", ...}
        """
        user_turn_id = str(uuid.uuid4())
        assistant_turn_id = str(uuid.uuid4())

        for event in self._execute_turn(session, turn_input, streaming=True):
            if event["type"] == "__done__":
                tool_calls_made_names = event["tool_calls_made"]
                yield {
                    "type": "done",
                    "provider": event["provider_name"],
                    "model": event["model_name"],
                    "user_turn_id": user_turn_id,
                    "assistant_turn_id": assistant_turn_id,
                    "tool_calls_made": tool_calls_made_names,
                    "tool_details": event["tool_details"],
                    "token_breakdown": {
                        "user_message_tokens": event["token_breakdown"].user_message_tokens,
                        "tool_calls_tokens": event["token_breakdown"].tool_calls_tokens,
                        "tool_results_tokens": event["token_breakdown"].tool_results_tokens,
                        "assistant_tokens": event["token_breakdown"].assistant_tokens,
                        "turn_total": event["token_breakdown"].turn_total,
                    },
                }
            else:
                yield event

    # ── Streaming internals ─────────────────────────────────────────────

    def _stream_and_collect(
        self,
        provider: LLMProvider,
        context: AssembledContext,
        provider_name: str,
    ) -> Iterator[dict]:
        """
        Stream a single LLM call, yielding text_delta events.

        Yields:
            {"type": "text_delta", "content": "..."} for each chunk.
            {"type": "__normalized__", "response": NormalizedResponse} at the end.
        """
        final_message: Any = None
        last_raw_chunk: Any = None
        accumulated_text = ""

        for chunk in provider.stream(context):
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

    def _stream_and_collect_with_tools(
        self,
        provider: LLMProvider,
        context: AssembledContext,
        tool_calls: list[ToolCall],
        tool_results: list[ToolResult],
        provider_name: str,
    ) -> Iterator[dict]:
        """
        Stream an LLM call after tool execution.

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
