"""
src/protocols.py
================
Shared Protocol interfaces used across multiple layers.

Having protocols in one place prevents:
  - Silent drift between duplicate definitions
  - Circular imports between layers
  - Multiple "sources of truth" for the same contract

Each protocol is minimal — only the methods that the *consumer* actually
needs.  This follows the Interface Segregation Principle (ISP).
"""
from __future__ import annotations

from typing import Any, Protocol


class TokenCounterProtocol(Protocol):
    """What any token counter must provide."""

    def count(self, text: str) -> int: ...
    def count_message(self, message: dict) -> int: ...
    def trim_to(self, text: str, max_tokens: int) -> str: ...


class PromptManagerProtocol(Protocol):
    """What the context assembler needs from PromptManager."""

    def get_system_instruction(self, mode: str = "default") -> str: ...


class NoteManagerProtocol(Protocol):
    """What the context assembler needs from NoteManager."""

    def get_for_context(
        self,
        session_id: str,
        max_tokens: int = 2000,
    ) -> str: ...


class FileManagerProtocol(Protocol):
    """What the context assembler needs from FileManager."""

    def get_for_context(
        self,
        file_paths: list[str],
        max_tokens: int = 4000,
    ) -> str: ...


class SearchCoordinatorProtocol(Protocol):
    """What NoteManager needs from SearchCoordinator."""

    def search(
        self,
        query: str,
        limit: int = 10,
        backends: list[str] | None = None,
    ) -> list[Any]: ...


class ToolRegistryProtocol(Protocol):
    """What ToolExecutor needs from ToolRegistry."""

    def get_handler(self, name: str) -> Any: ...
