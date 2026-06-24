"""
src/repositories/base.py
========================
Repository Protocol interfaces — the contracts that concrete
implementations must satisfy.

Separated from implementations so that:
  - Service layer depends on abstractions, not SQLite
  - Tests can use in-memory fakes
  - Future backends (Postgres, HTTP) can implement the same protocols
"""
from __future__ import annotations

from typing import Protocol


class SessionRepository(Protocol):
    def save_session(
        self,
        session_id: str,
        title: str,
        api_history_json: str,
        ui_history_json: str,
        parent_id: str | None = None,
        fork_turn_index: int | None = None,
        root_id: str | None = None,
        system_prompt: str | None = None,
    ) -> None: ...

    def load_session(self, session_id: str) -> tuple[str, str, str | None]: ...

    def list_sessions(self, include_archived: bool = False) -> list[dict]: ...
    def get_session_tree(self, include_archived: bool = True) -> list[dict]: ...
    def archive_session(self, session_id: str) -> bool: ...
    def unarchive_session(self, session_id: str) -> bool: ...
    def delete_session(self, session_id: str) -> None: ...
    def fork_session(self, source_session_id: str, turn_index: int) -> str: ...
    def get_export_data(self, session_id: str) -> dict: ...


class NoteRepository(Protocol):
    def add_note(self, session_id: str, selected_text: str, source_role: str, note: str = "") -> dict: ...
    def list_notes(self, session_id: str) -> list[dict]: ...
    def delete_note(self, note_id: str, session_id: str) -> bool: ...
