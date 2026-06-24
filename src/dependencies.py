"""
dependencies.py
───────────────
Single source of truth for application composition.

Every injectable dependency is defined here.
Reading this file top-to-bottom tells you the entire
object graph of the application.

Scopes:
  @lru_cache          → process lifetime (one instance ever)
  def get_*()         → request lifetime (new instance per request)
                        unless explicitly cached

Adding a new dependency:
  1. Write the get_* function here
  2. Import it in the route file that needs it
  3. Never instantiate infrastructure objects inside route handlers
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import structlog
from fastapi import Depends

if TYPE_CHECKING:
    from src.agent.turn_orchestrator import TurnOrchestrator
    from src.chat_service import ChatService
    from src.export_service import ExportService
    from src.repositories import SessionRepository

logger = structlog.get_logger(__name__)


# ── Singletons (process lifetime) ─────────────────────────────────────────────

@lru_cache
def get_settings():
    """Single Settings instance for the process."""
    from src.config import settings
    return settings


@lru_cache
def get_db_connection():
    """Single SQLiteConnection for the process."""
    from src.repositories import SQLiteConnection
    settings = get_settings()
    return SQLiteConnection(db_path=settings.db_path)


@lru_cache
def get_tool_registry():
    """
    Single ToolRegistry for the process.
    All tool schemas and handlers come from here.
    Wires SearchCoordinator so the search tool can fan out to
    multiple backends (grep today, BM25/embeddings tomorrow).
    """
    from src.tools.registry import build_default_registry
    return build_default_registry(
        search_coordinator=get_search_coordinator(),
    )


@lru_cache
def get_prompt_manager():
    """Single PromptManager for the process."""
    from src.prompt_manager import PromptManager
    settings = get_settings()
    prompts_dir = getattr(settings, "prompts_dir", "prompts")
    return PromptManager(prompts_dir=prompts_dir)


@lru_cache
def get_response_normalizer():
    """Single ResponseNormalizer — stateless, safe to cache."""
    from src.providers.normalizer import ResponseNormalizer
    return ResponseNormalizer()


# ── Request-scoped repositories ────────────────────────────────────────────────

def get_session_repo() -> "SessionRepository":
    """SessionRepository backed by SQLite."""
    from src.repositories import SQLiteSessionRepository
    return SQLiteSessionRepository(get_db_connection())


def get_note_repo():
    """NoteRepository backed by SQLite."""
    from src.repositories import SQLiteNoteRepository
    return SQLiteNoteRepository(get_db_connection())


# ── Provider factory ───────────────────────────────────────────────────────────

def get_llm_provider(
    provider_name: str | None = None,
    model_override: str | None = None,
):
    """
    Construct the active LLM provider.
    This is the ONLY place that maps provider name strings to classes.
    """
    from src.providers.base import get_provider
    return get_provider(
        provider_name=provider_name,
        model_override=model_override,
    )


# ── Token counter ──────────────────────────────────────────────────────────────

@lru_cache
def get_token_counter():
    """TokenCounter — stateless estimator, safe to cache."""
    from src.token_counter import TokenCounter
    return TokenCounter()


# ── Content layer ──────────────────────────────────────────────────────────────

@lru_cache
def get_search_coordinator():
    """SearchCoordinator with active backends."""
    from src.content.search_coordinator import SearchCoordinator, GrepSearchBackend
    settings = get_settings()
    return SearchCoordinator(
        backends={
            "grep": GrepSearchBackend(
                base_dir=getattr(settings, "data_dir", "data")
            ),
        }
    )


@lru_cache
def get_note_manager():
    """NoteManager — orchestrates note lifecycle."""
    from src.content.note_manager import NoteManager
    return NoteManager(
        repo=get_note_repo(),
        search=get_search_coordinator(),
    )


@lru_cache
def get_file_manager():
    """FileManager — orchestrates file content for context injection."""
    from src.content.file_manager import FileManager
    settings = get_settings()
    return FileManager(
        data_dir=getattr(settings, "data_dir", "data"),
    )


# ── Agent layer ────────────────────────────────────────────────────────────────

@lru_cache
def get_context_budget():
    """ContextBudget — token allocation per context slot."""
    from src.agent.context_assembler import ContextBudget
    settings = get_settings()
    total = getattr(settings, "context_window_tokens", 128_000)
    return ContextBudget(total=total)


@lru_cache
def get_context_assembler():
    """
    ContextAssembler — builds the context window for each turn.
    """
    from src.agent.context_assembler import ContextAssembler
    return ContextAssembler(
        token_budget=get_context_budget(),
        token_counter=get_token_counter(),
        prompt_manager=get_prompt_manager(),
        note_manager=get_note_manager(),
        file_manager=get_file_manager(),
    )


@lru_cache
def get_tool_executor():
    """ToolExecutor — resolves and runs tool calls safely."""
    from src.agent.tool_executor import ToolExecutor
    return ToolExecutor(registry=get_tool_registry(), token_counter=get_token_counter())


@lru_cache
def get_turn_orchestrator() -> "TurnOrchestrator":
    """
    TurnOrchestrator — manages one complete LLM turn lifecycle.
    Wires provider + tool registry + context assembler.
    """
    from src.agent.turn_orchestrator import TurnOrchestrator
    settings = get_settings()
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


# ── Service layer ──────────────────────────────────────────────────────────────

def get_chat_service(
    session_repo: "SessionRepository" = Depends(get_session_repo),
    orchestrator: "TurnOrchestrator" = Depends(get_turn_orchestrator),
) -> "ChatService":
    """ChatService — thin orchestrator for chat turns."""
    from src.chat_service import ChatService
    return ChatService(
        session_repo=session_repo,
        turn_orchestrator=orchestrator,
    )


def get_message_editor(
    session_repo: "SessionRepository" = Depends(get_session_repo),
):
    """MessageEditService — edit, delete, truncate conversation turns."""
    from src.message_editor import MessageEditService
    return MessageEditService(session_repo=session_repo)


def get_export_service(
    session_repo: "SessionRepository" = Depends(get_session_repo),
) -> "ExportService":
    """ExportService — formats sessions for export."""
    from src.export_service import ExportService
    return ExportService(session_repo=session_repo)


def get_import_service(
    session_repo: "SessionRepository" = Depends(get_session_repo),
) -> "ImportService":
    """ImportService — imports chat sessions from external JSON."""
    from src.import_service import ImportService
    return ImportService(
        session_repo=session_repo,
        token_counter=get_token_counter(),
    )


def get_folder_repo() -> "SQLiteFolderRepository":
    """FolderRepository backed by SQLite."""
    from src.repositories import SQLiteFolderRepository
    return SQLiteFolderRepository(get_db_connection())


def get_folder_service(
    folder_repo: "SQLiteFolderRepository" = Depends(get_folder_repo),
) -> "FolderService":
    """FolderService — folder business logic."""
    from src.folder_service import FolderService
    return FolderService(folder_repo=folder_repo)
