"""
src/content/note_manager.py
=============================
NoteManager — domain logic for notes.

Sits between the service layer and the NoteRepository.
Provides:
  - CRUD operations with validation
  - Context assembly (get notes formatted for LLM context window)
  - Search delegation to SearchCoordinator

Phase 5 scope: basic CRUD + context assembly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.protocols import (
    SearchCoordinatorProtocol,
    TokenCounterProtocol,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Note:
    """Domain object for a note."""

    id: str
    session_id: str
    selected_text: str
    note: str = ""
    source_role: str = ""
    created_at: str = ""


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class NoteRepositoryProtocol(Protocol):
    """Minimal interface NoteManager needs from a repository."""

    def add_note(
        self,
        session_id: str,
        selected_text: str,
        source_role: str,
        note: str = "",
    ) -> dict: ...

    def list_notes(self, session_id: str) -> list[dict]: ...

    def delete_note(self, note_id: str, session_id: str) -> bool: ...


# TokenCounterProtocol and SearchCoordinatorProtocol
# imported from src/protocols.py at module level (see top of file).


# ---------------------------------------------------------------------------
# NoteManager
# ---------------------------------------------------------------------------

class NoteManager:
    """
    Domain logic for notes.

    Responsibilities:
    - CRUD operations with validation
    - Context assembly (format notes for LLM context window)
    - Search delegation to SearchCoordinator

    Does NOT know about HTTP, schemas, or database specifics.
    """

    def __init__(
        self,
        repo: NoteRepositoryProtocol,
        token_counter: TokenCounterProtocol | None = None,
        search: SearchCoordinatorProtocol | None = None,
    ) -> None:
        self._repo = repo
        self._tokens = token_counter
        self._search = search

    def create(
        self,
        session_id: str,
        selected_text: str,
        source_role: str,
        note: str = "",
    ) -> Note:
        """
        Create a new note.

        Args:
            session_id:    The session this note belongs to.
            selected_text: The text the user selected.
            source_role:   Which role produced the text ("user" or "assistant").
            note:          Optional annotation.

        Returns:
            The created Note domain object.

        Raises:
            ValueError: If selected_text is empty or session not found.
        """
        if not selected_text.strip():
            raise ValueError("selected_text must not be empty.")

        raw = self._repo.add_note(
            session_id=session_id,
            selected_text=selected_text,
            source_role=source_role,
            note=note,
        )
        return Note(
            id=raw["id"],
            session_id=raw["session_id"],
            selected_text=raw["selected_text"],
            note=raw.get("note", ""),
            source_role=raw["source_role"],
            created_at=raw.get("created_at", ""),
        )

    def list_notes(self, session_id: str) -> list[Note]:
        """List all notes for a session."""
        raw_notes = self._repo.list_notes(session_id)
        return [
            Note(
                id=n["id"],
                session_id=n["session_id"],
                selected_text=n["selected_text"],
                note=n.get("note", ""),
                source_role=n["source_role"],
                created_at=n.get("created_at", ""),
            )
            for n in raw_notes
        ]

    def delete(self, note_id: str, session_id: str) -> bool:
        """
        Delete a note.

        Returns True if deleted, False if not found.
        """
        return self._repo.delete_note(note_id, session_id)

    def get_for_context(
        self,
        session_id: str,
        max_tokens: int = 2000,
    ) -> str:
        """
        Get notes formatted for LLM context window.

        Respects token budget — if notes exceed the budget, they are
        truncated (not dropped entirely).

        Args:
            session_id: The session to get notes for.
            max_tokens: Maximum tokens to use for notes.

        Returns:
            Formatted string of notes, or empty string if no notes.
        """
        notes = self.list_notes(session_id)
        if not notes:
            return ""

        # Format notes as a block
        parts: list[str] = []
        for n in notes:
            header = f"[{n.source_role}] {n.selected_text[:50]}"
            if n.note:
                header += f" — {n.note}"
            parts.append(header)

        content = "\n".join(parts)

        # Trim if over budget
        if self._tokens:
            tokens_used = self._tokens.count(content)
            if tokens_used > max_tokens:
                # Rough trim: proportionally reduce
                ratio = max_tokens / tokens_used
                max_chars = int(len(content) * ratio * 0.9)  # 90% to be safe
                content = content[:max_chars] + "\n... (truncated)"

        return content

    def search(self, query: str, limit: int = 10) -> list[Any]:
        """
        Search notes via SearchCoordinator.

        Delegates to the search coordinator which fans out to all backends.
        """
        if not self._search:
            return []
        return self._search.search(query, limit=limit)
