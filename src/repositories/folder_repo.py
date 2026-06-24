"""
src/repositories/folder_repo.py
================================
SQLite-backed implementation of FolderRepository.

Handles:
  - Folder CRUD (create, list, get, update, delete)
  - Session-to-folder assignment (many-to-many)
  - Folder session listing
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from src.repositories.connection import SQLiteConnection


class SQLiteFolderRepository:
    """SQLite implementation of folder operations."""

    def __init__(self, db: SQLiteConnection) -> None:
        self.db = db

    # ── Folder CRUD ──────────────────────────────────────────────────

    def create_folder(
        self,
        name: str,
        color: str = "#6B7280",
        icon: str = "📁",
        parent_id: str | None = None,
        order_index: int = 0,
    ) -> dict[str, Any]:
        """Create a new folder. Returns the created folder dict."""
        folder_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO folders (id, name, color, icon, parent_id, order_index, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (folder_id, name, color, icon, parent_id, order_index, now, now),
            )
            conn.commit()

        return {
            "id": folder_id,
            "name": name,
            "color": color,
            "icon": icon,
            "parent_id": parent_id,
            "order_index": order_index,
            "created_at": now,
            "updated_at": now,
        }

    def list_folders(self) -> list[dict[str, Any]]:
        """List all folders with session counts, ordered by order_index."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    f.id, f.name, f.color, f.icon, f.parent_id,
                    f.order_index, f.created_at, f.updated_at,
                    COUNT(sf.session_id) as session_count
                FROM folders f
                LEFT JOIN session_folders sf ON f.id = sf.folder_id
                GROUP BY f.id
                ORDER BY f.order_index ASC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_folder(self, folder_id: str) -> dict[str, Any] | None:
        """Get a single folder by ID. Returns None if not found."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    f.id, f.name, f.color, f.icon, f.parent_id,
                    f.order_index, f.created_at, f.updated_at,
                    COUNT(sf.session_id) as session_count
                FROM folders f
                LEFT JOIN session_folders sf ON f.id = sf.folder_id
                WHERE f.id = ?
                GROUP BY f.id
                """,
                (folder_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_folder(
        self,
        folder_id: str,
        name: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        order_index: int | None = None,
    ) -> dict[str, Any] | None:
        """Update folder fields. Returns updated folder or None if not found."""
        # Check if folder exists
        existing = self.get_folder(folder_id)
        if existing is None:
            return None

        # Build update query dynamically
        updates = []
        params: list[Any] = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if color is not None:
            updates.append("color = ?")
            params.append(color)
        if icon is not None:
            updates.append("icon = ?")
            params.append(icon)
        if order_index is not None:
            updates.append("order_index = ?")
            params.append(order_index)

        if not updates:
            return existing  # Nothing to update

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(folder_id)

        with self.db.get_connection() as conn:
            conn.execute(
                f"UPDATE folders SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

        return self.get_folder(folder_id)

    def delete_folder(self, folder_id: str) -> bool:
        """Delete a folder. Returns True if deleted, False if not found."""
        with self.db.get_connection() as conn:
            # First check if folder exists
            cursor = conn.execute(
                "SELECT 1 FROM folders WHERE id = ?", (folder_id,)
            )
            if cursor.fetchone() is None:
                return False

            # Delete folder (CASCADE will remove session_folders entries)
            conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
            conn.commit()

        return True

    def reorder_folders(self, folder_ids: list[str]) -> int:
        """Assign order_index 0, 1, 2, … to the given folder IDs atomically.

        Returns the number of folders reordered.
        """
        now = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            for index, folder_id in enumerate(folder_ids):
                conn.execute(
                    "UPDATE folders SET order_index = ?, updated_at = ? WHERE id = ?",
                    (index, now, folder_id),
                )
            conn.commit()
        return len(folder_ids)

    def move_session(
        self, from_folder: str, to_folder: str, session_id: str
    ) -> bool:
        """Atomically move a session from one folder to another.

        Both the DELETE (from source) and INSERT (into target) happen in a
        single transaction — there is no intermediate state where the session
        is in neither folder.

        Returns True on success, False if the session is not in the source
        folder or if source == target.
        """
        if from_folder == to_folder:
            return False

        with self.db.get_connection() as conn:
            # Check the session is actually in the source folder
            cursor = conn.execute(
                "SELECT 1 FROM session_folders WHERE folder_id = ? AND session_id = ?",
                (from_folder, session_id),
            )
            if cursor.fetchone() is None:
                return False

            # Atomic: delete from source + insert into target
            now = datetime.now().isoformat()
            conn.execute(
                "DELETE FROM session_folders WHERE folder_id = ? AND session_id = ?",
                (from_folder, session_id),
            )
            conn.execute(
                "INSERT OR IGNORE INTO session_folders (folder_id, session_id, assigned_at) "
                "VALUES (?, ?, ?)",
                (to_folder, session_id, now),
            )
            conn.commit()

        return True

    # ── Session Assignment ───────────────────────────────────────────

    def assign_session(self, folder_id: str, session_id: str) -> bool:
        """Assign a session to a folder. Returns True on success."""
        with self.db.get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO session_folders (folder_id, session_id, assigned_at)
                    VALUES (?, ?, ?)
                    """,
                    (folder_id, session_id, datetime.now().isoformat()),
                )
                conn.commit()
                return True
            except Exception:
                return False

    def unassign_session(self, folder_id: str, session_id: str) -> bool:
        """Remove session from folder. Returns True if removed, False if not assigned."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM session_folders WHERE folder_id = ? AND session_id = ?",
                (folder_id, session_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_folder_sessions(self, folder_id: str) -> list[dict[str, Any]]:
        """Get all sessions in a folder, ordered by updated_at DESC."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT s.id, s.title, s.updated_at
                FROM sessions s
                INNER JOIN session_folders sf ON s.id = sf.session_id
                WHERE sf.folder_id = ?
                ORDER BY s.updated_at DESC
                """,
                (folder_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_session_folders(self, session_id: str) -> list[dict[str, Any]]:
        """Get all folders a session belongs to."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT f.id, f.name, f.color, f.icon, f.parent_id,
                       f.order_index, f.created_at, f.updated_at
                FROM folders f
                INNER JOIN session_folders sf ON f.id = sf.folder_id
                WHERE sf.session_id = ?
                ORDER BY f.order_index ASC
                """,
                (session_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ── Tree Assignment ────────────────────────────────────────────────

    def assign_tree(self, folder_id: str, session_id: str, include_children: bool = False) -> list[str]:
        """
        Assign session (and optionally children) to folder.
        Returns list of assigned session IDs.
        """
        ids_to_assign = [session_id]

        if include_children:
            # Get children from session repository
            # We need to import here to avoid circular dependency
            from src.repositories.session_repo import SQLiteSessionRepository
            session_repo = SQLiteSessionRepository(self.db)
            ids_to_assign.extend(session_repo.get_children(session_id))

        with self.db.get_connection() as conn:
            for sid in ids_to_assign:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO session_folders (folder_id, session_id, assigned_at)
                    VALUES (?, ?, ?)
                    """,
                    (folder_id, sid, datetime.now().isoformat()),
                )
            conn.commit()

        return ids_to_assign

    def unassign_tree(self, folder_id: str, session_id: str, include_children: bool = False) -> list[str]:
        """
        Remove session (and optionally children) from folder.
        Returns list of unassigned session IDs.
        """
        ids_to_unassign = [session_id]

        if include_children:
            from src.repositories.session_repo import SQLiteSessionRepository
            session_repo = SQLiteSessionRepository(self.db)
            ids_to_unassign.extend(session_repo.get_children(session_id))

        with self.db.get_connection() as conn:
            for sid in ids_to_unassign:
                conn.execute(
                    "DELETE FROM session_folders WHERE folder_id = ? AND session_id = ?",
                    (folder_id, sid),
                )
            conn.commit()

        return ids_to_unassign
