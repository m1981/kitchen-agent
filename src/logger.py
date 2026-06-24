"""
src/logger.py
=============
Structured logging configuration with request-context propagation.

Design principles
-----------------
1. **Structured**: All logs are key-value pairs (via structlog), easy to filter/parse.
2. **Contextual**: Request context (session_id, turn_id, provider, model) propagates
   automatically through all log calls in a request lifecycle.
3. **Layered**: Each layer logs its own concerns — no duplication.
4. **Configurable**: LOG_LEVEL env var controls verbosity; DEBUG mode enables
   additional timing and payload logging.

Environment variables
---------------------
LOG_LEVEL=INFO          # DEBUG | INFO | WARNING | ERROR
LOG_TIMING=true         # Log duration of LLM calls and tool execution
LOG_LLM_PAYLOADS=false  # Log full context sent to LLM (verbose, for debugging)

Log layers and what they capture
--------------------------------
┌─────────────────────┬──────────────────────────────────────────────────┐
│ Layer               │ What is logged                                  │
├─────────────────────┼──────────────────────────────────────────────────┤
│ api/chat.py         │ HTTP request received, response sent            │
│ chat_service.py     │ Turn lifecycle: load → execute → persist        │
│ turn_orchestrator.py│ Provider resolution, context assembly, LLM call │
│ providers/*.py      │ API call params, response metadata, errors      │
│ agent/tool_executor │ Tool execution: name, args, result, duration    │
└─────────────────────┴──────────────────────────────────────────────────┘
"""

import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Generator

import structlog


def setup_logging(is_local_dev: bool = True) -> None:
    """
    Configures structlog with environment-driven verbosity.

    Args:
        is_local_dev: True for colored console output, False for JSON.
    """
    # ── Log level from environment ───────────────────────────────────────────
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    # ── Renderer based on environment ────────────────────────────────────────
    if is_local_dev:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Add request context from thread-local if available
            _add_request_context,
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# ---------------------------------------------------------------------------
# Request context propagation
# ---------------------------------------------------------------------------
# Uses thread-local storage to attach session_id, turn_id, provider, model
# to every log call within a request lifecycle.  Set via bind_request_context()
# at the start of each request, clear via clear_request_context() at the end.

import threading

_request_context = threading.local()


def _add_request_context(
    logger: logging.Logger, method_name: str, event_dict: dict
) -> dict:
    """Structlog processor that injects request context into every log line."""
    ctx = getattr(_request_context, "data", None)
    if ctx:
        for key, value in ctx.items():
            if value and key not in event_dict:
                event_dict[key] = value
    return event_dict


def bind_request_context(**kwargs: str | None) -> None:
    """
    Bind request-scoped context that will appear in all subsequent log lines.

    Typical usage at the start of a request handler:
        bind_request_context(session_id="abc123", provider="gemini")
    """
    if not hasattr(_request_context, "data"):
        _request_context.data = {}
    _request_context.data.update({k: v for k, v in kwargs.items() if v is not None})


def clear_request_context() -> None:
    """Clear request context — call at the end of a request."""
    _request_context.data = {}


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

LOG_TIMING = os.environ.get("LOG_TIMING", "true").lower() in ("true", "1", "yes")
LOG_LLM_PAYLOADS = os.environ.get("LOG_LLM_PAYLOADS", "false").lower() in ("true", "1", "yes")


@contextmanager
def log_timing(
    log: structlog.BoundLogger,
    event: str,
    **extra: str | int | float,
) -> Generator[dict, None, None]:
    """
    Context manager that logs the duration of a block.

    Usage:
        with log_timing(log, "llm_call", provider="gemini") as timing:
            response = provider.complete(context)
        # Logs: "llm_call provider=gemini duration_ms=1234.5"

    The ``timing`` dict can be extended inside the block:
        with log_timing(log, "llm_call") as timing:
            timing["tokens"] = 100
    """
    if not LOG_TIMING:
        yield {}
        return

    timing: dict = {"duration_ms": 0.0, **extra}
    start = time.perf_counter()
    try:
        yield timing
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        timing["duration_ms"] = round(elapsed_ms, 2)
        log.info(event, **timing)
