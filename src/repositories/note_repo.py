"""
src/repositories/note_repo.py
==============================
SQLite-backed implementation of NoteRepository.

Handles:
  - Note CRUD (add, list, delete)
  - Session-scoped isolation
"""
from __future__ import annotations

import uuid
from datetime import datetime

from src.repositories.connection import SQLiteConnection


class SQLiteNoteRepository:
    def __init__(self, db: SQLiteConnection):
        self.db = db

    def add_note(
        self,
        session_id: str,
        selected_text: str,
        source_role: str,
        note: str = "",
    ) -> dict:
        if not selected_text.strip():
            raise ValueError("selected_text must not be empty.")

        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()

        if row is None:
            raise ValueError(f"Session not found: {session_id}")

        note_id = str(uuid.uuid4())
        created_at = datetime.now()

        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO notes "
                "(id, session_id, selected_text, note, source_role, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (note_id, session_id, selected_text, note, source_role, created_at),
            )
            conn.commit()

        return {
            "id": note_id,
            "session_id": session_id,
            "selected_text": selected_text,
            "note": note,
            "source_role": source_role,
            "created_at": created_at.isoformat(),
        }

    def list_notes(self, session_id: str) -> list[dict]:
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, session_id, selected_text, note, source_role, created_at "
                "FROM notes WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def delete_note(self, note_id: str, session_id: str) -> bool:
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM notes WHERE id = ? AND session_id = ?",
                (note_id, session_id),
            )
            conn.commit()
        return cursor.rowcount > 0
