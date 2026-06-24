"""
main.py
───────
Application entry point.

Responsibilities (only these):
  - Create the FastAPI app instance
  - Register middleware
  - Register routers
  - Startup/shutdown lifecycle hooks

Nothing else lives here.
  Routes    → src/api/
  DI wiring → src/dependencies.py
  Config    → src/config.py
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.logger import setup_logging
from src.api import chat, sessions, files, notes, prompts, providers, test_helpers, import_chat, folders


# ── Logging ────────────────────────────────────────────────────────

setup_logging()


# ── Lifespan ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: warm the singleton cache so first request is not slow.
    Shutdown: nothing to clean up (SQLite closes on GC).
    """
    from src.dependencies import (
        get_settings,
        get_db_connection,
        get_tool_registry,
        get_prompt_manager,
    )

    get_settings()       # validates env vars at startup, not first request
    get_db_connection()  # opens DB and runs migrations at startup
    get_tool_registry()  # registers all tools at startup
    get_prompt_manager() # loads prompt files at startup

    yield
    # nothing to teardown


# ── App ────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_title,
    description=settings.app_description,
    lifespan=lifespan,
)


# ── Middleware ─────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TestDelayMiddleware(BaseHTTPMiddleware):
    """Add artificial delay when X-Test-Delay-Ms header is present (dev mode only)."""

    async def dispatch(self, request: Request, call_next):
        if settings.debug:
            delay_ms = request.headers.get("X-Test-Delay-Ms")
            if delay_ms:
                try:
                    await asyncio.sleep(int(delay_ms) / 1000)
                except (ValueError, TypeError):
                    pass
        return await call_next(request)


if settings.debug:
    app.add_middleware(TestDelayMiddleware)


# ── Routers ────────────────────────────────────────────────────────

app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(files.router)
app.include_router(notes.router)
app.include_router(prompts.router)
app.include_router(providers.router)
app.include_router(test_helpers.router)
app.include_router(import_chat.router)
app.include_router(folders.router)
