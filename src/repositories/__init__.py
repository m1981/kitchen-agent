"""
src/repositories
================
Data access layer using the Repository Pattern.

This package re-exports all public names so that existing imports
like ``from src.repositories import SQLiteConnection`` continue
to work without changes.

Submodules:
  base.py          — SessionRepository, NoteRepository Protocols
  connection.py    — SQLiteConnection (schema DDL, migrations)
  session_repo.py  — SQLiteSessionRepository
  note_repo.py     — SQLiteNoteRepository
"""
from src.repositories.base import NoteRepository, SessionRepository
from src.repositories.connection import SQLiteConnection
from src.repositories.folder_repo import SQLiteFolderRepository
from src.repositories.note_repo import SQLiteNoteRepository
from src.repositories.session_repo import SQLiteSessionRepository

__all__ = [
    "SessionRepository",
    "NoteRepository",
    "SQLiteConnection",
    "SQLiteSessionRepository",
    "SQLiteNoteRepository",
]
