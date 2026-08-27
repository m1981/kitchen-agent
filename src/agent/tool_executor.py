"""
src/agent/tool_executor.py
===========================
ToolExecutor — isolated, safe tool execution.

Single responsibility: resolve a tool handler from a registry, execute it,
and return a normalized result.  Errors are caught and wrapped so the LLM
sees them (as a tool error result) instead of the application crashing.

Design decisions
----------------
* **Sync-first**: Current tool handlers are synchronous functions.  The
  executor runs them directly (no ``asyncio.to_thread``) for simplicity
  and determinism.  When async handlers are added, the executor can be
  extended with ``asyncio.iscoroutinefunction`` detection.
* **No provider knowledge**: The executor does not know about LLM providers,
  sessions, or history.  It only knows about tool names and registries.
* **Error wrapping**: Any exception from a tool handler is caught and
  returned as a ``ToolResult(is_error=True)``.  The caller (provider
  agentic loop) decides what to do with the error.

Phase 2 scope
-------------
Initially used by the provider agentic loops (GeminiProvider and
AnthropicProvider) for tool dispatch.  The providers previously called
``FUNCTION_MAP[tool_name](**args)`` inline; they now delegate to
ToolExecutor for the same behavior.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from src.protocols import TokenCounterProtocol, ToolRegistryProtocol

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """Normalized tool call — provider-agnostic."""

    id: str
    name: str
    arguments: dict
    token_count: int = 0  # token count for the call arguments
    # base64 of the model's thought_signature, when the provider supplies one.
    # Gemini 3 requires it back on every replay of this call.
    thought_signature: str | None = None


@dataclass
class ToolResult:
    """Normalized tool result — provider-agnostic."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False
    token_count: int = 0  # token count for this tool result


def _encode_result(result: object) -> str:
    """
    Serialise a tool result for the wire **and** for session storage.

    JSON on both sides: providers rebuild a dict from this string, and the
    stored history is read back with ``json.loads``.
    """
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"content": str(result)}, ensure_ascii=False)


def _path_key(path: str) -> str:
    """
    Canonical key for read-before-edit bookkeeping.

    The model may spell the same file as ``data/01_Proces/x.md``,
    ``./01_Proces/x.md`` or ``01_Proces/x.md`` — all three are the same file.
    """
    cleaned = (path or "").strip().replace("\\", "/").lstrip("./")
    if cleaned.startswith("data/"):
        cleaned = cleaned[len("data/"):]
    return cleaned.strip("/")


@dataclass
class TurnFileGuard:
    """
    Remembers which files the model actually read during one turn.

    A mutating tool that declares ``requires_prior_read`` is refused for a path
    the model never looked at.  Until now "read the file first" was only prose
    in the tool description, so nothing stopped a blind edit whose search text
    happened to match somewhere in the file.

    One instance per turn — the executor is a process-wide singleton, so the
    state deliberately does not live there.
    """

    _read: set[str] = field(default_factory=set)

    def note_read(self, path: str) -> None:
        self._read.add(_path_key(path))

    def was_read(self, path: str) -> bool:
        return _path_key(path) in self._read

    @property
    def paths_read(self) -> list[str]:
        return sorted(self._read)


# ToolRegistryProtocol imported from src/protocols.py — single source of truth.


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class ToolExecutor:
    """
    Execute tool calls safely.

    - Resolves handler from registry
    - Catches and wraps errors (LLM should see error, not crash)
    - Does NOT know about providers or sessions
    """

    def __init__(self, registry: ToolRegistryProtocol, token_counter: TokenCounterProtocol | None = None) -> None:
        self._registry = registry
        self._token_counter = token_counter

    def execute_all(
        self,
        tool_calls: list[ToolCall],
        guard: "TurnFileGuard | None" = None,
    ) -> list[ToolResult]:
        """
        Execute all tool calls and return their results.

        Current implementation runs synchronously (matching the
        synchronous tool handlers in the codebase).  Each call
        is executed sequentially for determinism.

        Args:
            tool_calls: List of ToolCall objects to execute.

        Returns:
            List of ToolResult objects — one per tool call.
            Errors are wrapped, never raised.
        """
        log.debug(
            "tool_executor_batch_start",
            tool_count=len(tool_calls),
            tool_names=[tc.name for tc in tool_calls],
        )
        # Count tokens for tool call arguments
        if self._token_counter:
            for tc in tool_calls:
                args_str = str(tc.arguments)
                tc.token_count = self._token_counter.count(tc.name + args_str)
        results = [self._execute_one(tc, guard) for tc in tool_calls]
        log.debug(
            "tool_executor_batch_complete",
            tool_count=len(results),
            errors=sum(1 for r in results if r.is_error),
        )
        return results

    def _error_result(self, tool_call: ToolCall, message: str) -> ToolResult:
        """Structured refusal the model can act on — never an exception."""
        content = _encode_result({"error": message})
        return ToolResult(
            tool_call_id=tool_call.id,
            name=tool_call.name,
            content=content,
            is_error=True,
            token_count=self._token_counter.count(content) if self._token_counter else 0,
        )

    def _entry_for(self, name: str):
        """Registry entry for a tool, or None for registries that expose none."""
        get_entries = getattr(self._registry, "get_all_entries", None)
        if not callable(get_entries):
            return None
        for entry in get_entries():
            if entry.declaration.name == name:
                return entry
        return None

    def _execute_one(self, tool_call: ToolCall, guard: "TurnFileGuard | None" = None) -> ToolResult:
        log.debug(
            "tool_executing",
            tool_name=tool_call.name,
            tool_call_id=tool_call.id,
            args_keys=list(tool_call.arguments.keys()),
        )
        start = time.perf_counter()
        entry = self._entry_for(tool_call.name)
        path_arg = getattr(entry, "path_argument", "filepath")
        target_path = tool_call.arguments.get(path_arg, "") if entry else ""

        if entry is not None and entry.requires_prior_read and guard is not None:
            if not guard.was_read(target_path):
                log.warning(
                    "tool_blind_edit_refused",
                    tool_name=tool_call.name,
                    filepath=target_path,
                    paths_read_this_turn=guard.paths_read,
                )
                return self._error_result(
                    tool_call,
                    f"Refused: you have not read {target_path!r} in this turn. "
                    "Call read_file on that exact path first — editing text you "
                    "have not seen risks replacing the wrong content.",
                )

        try:
            handler = self._registry.get_handler(tool_call.name)
            result = handler(**tool_call.arguments)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            if (
                entry is not None
                and entry.marks_read
                and guard is not None
                and isinstance(result, dict)
                and "content" in result
            ):
                guard.note_read(target_path)

            # JSON, not str(): the same encoding has to survive the round trip
            # into session history, where it is read back with json.loads.
            # Python's repr uses single quotes and is not valid JSON, so the
            # file content came back to the model double-wrapped on later turns.
            content = _encode_result(result)
            log.debug(
                "tool_executed",
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
                result_size=len(content),
                is_error=False,
                duration_ms=duration_ms,
            )

            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=content,
                is_error=False,
                token_count=self._token_counter.count(content) if self._token_counter else 0,
            )

        except Exception as e:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            error_content = _encode_result({"error": f"{type(e).__name__}: {e}"})
            log.warning(
                "tool_execution_error",
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
                error_type=type(e).__name__,
                error_message=str(e),
                duration_ms=duration_ms,
            )
            # Never crash the turn — return structured error to LLM
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=error_content,
                is_error=True,
                token_count=self._token_counter.count(error_content) if self._token_counter else 0,
            )
