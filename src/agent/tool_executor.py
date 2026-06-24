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

import time
from dataclasses import dataclass
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


@dataclass
class ToolResult:
    """Normalized tool result — provider-agnostic."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False
    token_count: int = 0  # token count for this tool result


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
        results = [self._execute_one(tc) for tc in tool_calls]
        log.debug(
            "tool_executor_batch_complete",
            tool_count=len(results),
            errors=sum(1 for r in results if r.is_error),
        )
        return results

    def _execute_one(self, tool_call: ToolCall) -> ToolResult:
        log.debug(
            "tool_executing",
            tool_name=tool_call.name,
            tool_call_id=tool_call.id,
            args_keys=list(tool_call.arguments.keys()),
        )
        start = time.perf_counter()
        try:
            handler = self._registry.get_handler(tool_call.name)
            result = handler(**tool_call.arguments)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            content = str(result)
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
            error_content = f"Tool error: {type(e).__name__}: {e}"
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
