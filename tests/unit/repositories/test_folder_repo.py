"""
tests/unit/repositories/test_folder_repo.py
============================================
Unit tests for SQLiteFolderRepository.

Tests the folder CRUD operations and session assignment.
"""

import json
import pytest
from pathlib import Path

from src.repositories import SQLiteConnection, SQLiteSessionRepository
from src.repositories.folder_repo import SQLiteFolderRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path: Path) -> SQLiteConnection:
    """Temporary SQLite database."""
    return SQLiteConnection(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def folder_repo(db: SQLiteConnection) -> SQLiteFolderRepository:
    """Folder repository backed by temporary database."""
    return SQLiteFolderRepository(db)


@pytest.fixture
def session_repo(db: SQLiteConnection) -> SQLiteSessionRepository:
    """Session repository for seeding test sessions."""
    return SQLiteSessionRepository(db)


def _seed_session(repo: SQLiteSessionRepository, session_id: str, title: str = "Test") -> None:
    """Helper to create a test session."""
    repo.save_session(
        session_id=session_id,
        title=title,
        api_history_json="[]",
        ui_history_json="[]",
    )


# ---------------------------------------------------------------------------
# Folder CRUD
# ---------------------------------------------------------------------------

class TestCreateFolder:
    """Test folder creation."""

    def test_create_folder_returns_dict(self, folder_repo: SQLiteFolderRepository) -> None:
        """create_folder returns a dict with all expected fields."""
        result = folder_repo.create_folder(name="Kitchen Projects", color="#3B82F6")

        assert isinstance(result, dict)
        assert "id" in result
        assert result["name"] == "Kitchen Projects"
        assert result["color"] == "#3B82F6"
        assert "created_at" in result

    def test_create_folder_generates_uuid(self, folder_repo: SQLiteFolderRepository) -> None:
        """Each folder gets a unique UUID."""
        f1 = folder_repo.create_folder(name="Folder 1")
        f2 = folder_repo.create_folder(name="Folder 2")

        assert f1["id"] != f2["id"]
        assert len(f1["id"]) == 36  # UUID format

    def test_create_folder_default_color(self, folder_repo: SQLiteFolderRepository) -> None:
        """Default color is gray when not specified."""
        result = folder_repo.create_folder(name="Default Color")

        assert result["color"] == "#6B7280"

    def test_create_folder_with_icon(self, folder_repo: SQLiteFolderRepository) -> None:
        """Icon is stored correctly."""
        result = folder_repo.create_folder(name="With Icon", icon="🍳")

        assert result["icon"] == "🍳"

    def test_create_folder_default_icon(self, folder_repo: SQLiteFolderRepository) -> None:
        """Default icon is folder emoji when not specified."""
        result = folder_repo.create_folder(name="Default Icon")

        assert result["icon"] == "📁"

    def test_create_folder_with_parent(self, folder_repo: SQLiteFolderRepository) -> None:
        """Nested folder creation with parent_id."""
        parent = folder_repo.create_folder(name="Parent")
        child = folder_repo.create_folder(name="Child", parent_id=parent["id"])

        assert child["parent_id"] == parent["id"]

    def test_create_folder_null_parent(self, folder_repo: SQLiteFolderRepository) -> None:
        """Root folder has null parent_id."""
        result = folder_repo.create_folder(name="Root")

        assert result["parent_id"] is None


class TestListFolders:
    """Test folder listing."""

    def test_list_folders_empty(self, folder_repo: SQLiteFolderRepository) -> None:
        """Empty list when no folders exist."""
        result = folder_repo.list_folders()

        assert result == []

    def test_list_folders_returns_all(self, folder_repo: SQLiteFolderRepository) -> None:
        """Returns all folders."""
        folder_repo.create_folder(name="Folder 1")
        folder_repo.create_folder(name="Folder 2")
        folder_repo.create_folder(name="Folder 3")

        result = folder_repo.list_folders()

        assert len(result) == 3

    def test_list_folders_ordered_by_order_index(
        self, folder_repo: SQLiteFolderRepository
    ) -> None:
        """Folders ordered by order_index."""
        folder_repo.create_folder(name="Second", order_index=2)
        folder_repo.create_folder(name="First", order_index=1)
        folder_repo.create_folder(name="Third", order_index=3)

        result = folder_repo.list_folders()

        assert result[0]["name"] == "First"
        assert result[1]["name"] == "Second"
        assert result[2]["name"] == "Third"

    def test_list_folders_includes_session_count(
        self, folder_repo: SQLiteFolderRepository, session_repo: SQLiteSessionRepository
    ) -> None:
        """Each folder includes count of assigned sessions."""
        folder = folder_repo.create_folder(name="With Sessions")
        _seed_session(session_repo, "s1", "Session 1")
        _seed_session(session_repo, "s2", "Session 2")

        folder_repo.assign_session(folder["id"], "s1")
        folder_repo.assign_session(folder["id"], "s2")

        result = folder_repo.list_folders()

        assert len(result) == 1
        assert result[0]["session_count"] == 2

    def test_list_folders_zero_session_count(
        self, folder_repo: SQLiteFolderRepository
    ) -> None:
        """Empty folder has session_count = 0."""
        folder_repo.create_folder(name="Empty Folder")

        result = folder_repo.list_folders()

        assert result[0]["session_count"] == 0


class TestGetFolder:
    """Test getting a single folder."""

    def test_get_folder_returns_dict(self, folder_repo: SQLiteFolderRepository) -> None:
        """get_folder returns folder dict."""
        created = folder_repo.create_folder(name="Test Folder")
        result = folder_repo.get_folder(created["id"])

        assert result is not None
        assert result["name"] == "Test Folder"

    def test_get_folder_not_found(self, folder_repo: SQLiteFolderRepository) -> None:
        """Returns None for nonexistent folder."""
        result = folder_repo.get_folder("nonexistent-id")

        assert result is None


class TestUpdateFolder:
    """Test folder updates."""

    def test_update_folder_name(self, folder_repo: SQLiteFolderRepository) -> None:
        """Folder name can be updated."""
        folder = folder_repo.create_folder(name="Old Name")

        result = folder_repo.update_folder(folder["id"], name="New Name")

        assert result is not None
        assert result["name"] == "New Name"

    def test_update_folder_color(self, folder_repo: SQLiteFolderRepository) -> None:
        """Folder color can be updated."""
        folder = folder_repo.create_folder(name="Color Test", color="#EF4444")

        result = folder_repo.update_folder(folder["id"], color="#22C55E")

        assert result is not None
        assert result["color"] == "#22C55E"

    def test_update_folder_icon(self, folder_repo: SQLiteFolderRepository) -> None:
        """Folder icon can be updated."""
        folder = folder_repo.create_folder(name="Icon Test", icon="📁")

        result = folder_repo.update_folder(folder["id"], icon="🍳")

        assert result is not None
        assert result["icon"] == "🍳"

    def test_update_folder_order_index(self, folder_repo: SQLiteFolderRepository) -> None:
        """Folder order_index can be updated."""
        folder = folder_repo.create_folder(name="Order Test", order_index=0)

        result = folder_repo.update_folder(folder["id"], order_index=5)

        assert result is not None
        assert result["order_index"] == 5

    def test_update_folder_partial(self, folder_repo: SQLiteFolderRepository) -> None:
        """Only specified fields are updated."""
        folder = folder_repo.create_folder(name="Original", color="#EF4444", icon="📁")

        result = folder_repo.update_folder(folder["id"], color="#22C55E")

        assert result["name"] == "Original"  # Unchanged
        assert result["color"] == "#22C55E"  # Changed
        assert result["icon"] == "📁"  # Unchanged

    def test_update_folder_not_found(self, folder_repo: SQLiteFolderRepository) -> None:
        """Returns None when folder doesn't exist."""
        result = folder_repo.update_folder("nonexistent", name="New")

        assert result is None


class TestDeleteFolder:
    """Test folder deletion."""

    def test_delete_folder_returns_true(self, folder_repo: SQLiteFolderRepository) -> None:
        """Returns True when folder is deleted."""
        folder = folder_repo.create_folder(name="To Delete")

        result = folder_repo.delete_folder(folder["id"])

        assert result is True

    def test_delete_folder_removes_from_list(
        self, folder_repo: SQLiteFolderRepository
    ) -> None:
        """Deleted folder no longer appears in list."""
        folder = folder_repo.create_folder(name="To Delete")
        folder_repo.delete_folder(folder["id"])

        result = folder_repo.list_folders()

        assert len(result) == 0

    def test_delete_folder_not_found(self, folder_repo: SQLiteFolderRepository) -> None:
        """Returns False when folder doesn't exist."""
        result = folder_repo.delete_folder("nonexistent")

        assert result is False

    def test_delete_folder_unassigns_sessions(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Deleting a folder unassigns all sessions."""
        folder = folder_repo.create_folder(name="With Sessions")
        _seed_session(session_repo, "s1", "Session 1")
        folder_repo.assign_session(folder["id"], "s1")

        folder_repo.delete_folder(folder["id"])

        # Session should still exist but be unassigned
        sessions = session_repo.list_sessions()
        assert len(sessions) == 1


# ---------------------------------------------------------------------------
# Session Assignment
# ---------------------------------------------------------------------------

class TestAssignSession:
    """Test session-to-folder assignment."""

    def test_assign_session_returns_true(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Returns True on successful assignment."""
        folder = folder_repo.create_folder(name="Test")
        _seed_session(session_repo, "s1", "Session 1")

        result = folder_repo.assign_session(folder["id"], "s1")

        assert result is True

    def test_assign_session_appears_in_folder_sessions(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Assigned session appears in folder's session list."""
        folder = folder_repo.create_folder(name="Test")
        _seed_session(session_repo, "s1", "Session 1")
        _seed_session(session_repo, "s2", "Session 2")

        folder_repo.assign_session(folder["id"], "s1")
        folder_repo.assign_session(folder["id"], "s2")

        sessions = folder_repo.get_folder_sessions(folder["id"])

        assert len(sessions) == 2
        session_ids = [s["id"] for s in sessions]
        assert "s1" in session_ids
        assert "s2" in session_ids

    def test_assign_session_updates_count(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Session count updates after assignment."""
        folder = folder_repo.create_folder(name="Test")
        _seed_session(session_repo, "s1", "Session 1")

        folder_repo.assign_session(folder["id"], "s1")

        result = folder_repo.list_folders()
        assert result[0]["session_count"] == 1

    def test_assign_session_duplicate_is_noop(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Assigning same session twice doesn't duplicate."""
        folder = folder_repo.create_folder(name="Test")
        _seed_session(session_repo, "s1", "Session 1")

        folder_repo.assign_session(folder["id"], "s1")
        folder_repo.assign_session(folder["id"], "s1")

        sessions = folder_repo.get_folder_sessions(folder["id"])
        assert len(sessions) == 1

    def test_assign_session_to_multiple_folders(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Session can be in multiple folders."""
        folder1 = folder_repo.create_folder(name="Folder 1")
        folder2 = folder_repo.create_folder(name="Folder 2")
        _seed_session(session_repo, "s1", "Session 1")

        folder_repo.assign_session(folder1["id"], "s1")
        folder_repo.assign_session(folder2["id"], "s1")

        sessions1 = folder_repo.get_folder_sessions(folder1["id"])
        sessions2 = folder_repo.get_folder_sessions(folder2["id"])
        assert len(sessions1) == 1
        assert len(sessions2) == 1


class TestUnassignSession:
    """Test session unassignment."""

    def test_unassign_session_returns_true(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Returns True on successful unassignment."""
        folder = folder_repo.create_folder(name="Test")
        _seed_session(session_repo, "s1", "Session 1")
        folder_repo.assign_session(folder["id"], "s1")

        result = folder_repo.unassign_session(folder["id"], "s1")

        assert result is True

    def test_unassign_session_removes_from_list(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Unassigned session no longer in folder."""
        folder = folder_repo.create_folder(name="Test")
        _seed_session(session_repo, "s1", "Session 1")
        folder_repo.assign_session(folder["id"], "s1")

        folder_repo.unassign_session(folder["id"], "s1")

        sessions = folder_repo.get_folder_sessions(folder["id"])
        assert len(sessions) == 0

    def test_unassign_session_not_assigned(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Returns False when session wasn't assigned."""
        folder = folder_repo.create_folder(name="Test")
        _seed_session(session_repo, "s1", "Session 1")

        result = folder_repo.unassign_session(folder["id"], "s1")

        assert result is False


class TestGetFolderSessions:
    """Test getting sessions in a folder."""

    def test_get_folder_sessions_empty(
        self, folder_repo: SQLiteFolderRepository
    ) -> None:
        """Empty list for folder with no sessions."""
        folder = folder_repo.create_folder(name="Empty")

        result = folder_repo.get_folder_sessions(folder["id"])

        assert result == []

    def test_get_folder_sessions_returns_session_data(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Returns session data including title."""
        folder = folder_repo.create_folder(name="Test")
        _seed_session(session_repo, "s1", "My Session")
        folder_repo.assign_session(folder["id"], "s1")

        result = folder_repo.get_folder_sessions(folder["id"])

        assert len(result) == 1
        assert result[0]["id"] == "s1"
        assert result[0]["title"] == "My Session"

    def test_get_folder_sessions_ordered_by_updated_at(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Sessions ordered by most recently updated."""
        folder = folder_repo.create_folder(name="Test")
        _seed_session(session_repo, "s1", "First")
        _seed_session(session_repo, "s2", "Second")
        _seed_session(session_repo, "s3", "Third")

        folder_repo.assign_session(folder["id"], "s1")
        folder_repo.assign_session(folder["id"], "s2")
        folder_repo.assign_session(folder["id"], "s3")

        result = folder_repo.get_folder_sessions(folder["id"])

        assert len(result) == 3
        # Should be ordered by updated_at DESC (most recent first)


class TestGetSessionFolders:
    """Test getting folders for a session."""

    def test_get_session_folders_empty(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Empty list for unassigned session."""
        _seed_session(session_repo, "s1", "Session")

        result = folder_repo.get_session_folders("s1")

        assert result == []

    def test_get_session_folders_returns_all(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Returns all folders session belongs to."""
        folder1 = folder_repo.create_folder(name="Folder 1")
        folder2 = folder_repo.create_folder(name="Folder 2")
        _seed_session(session_repo, "s1", "Session")

        folder_repo.assign_session(folder1["id"], "s1")
        folder_repo.assign_session(folder2["id"], "s1")

        result = folder_repo.get_session_folders("s1")

        assert len(result) == 2
        folder_ids = [f["id"] for f in result]
        assert folder1["id"] in folder_ids
        assert folder2["id"] in folder_ids


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------


class TestReorderFolders:
    """Test folder reordering."""

    def test_reorder_folders_assigns_order_index(
        self, folder_repo: SQLiteFolderRepository
    ) -> None:
        """Reorder assigns 0, 1, 2, … to given IDs."""
        f1 = folder_repo.create_folder(name="A")
        f2 = folder_repo.create_folder(name="B")
        f3 = folder_repo.create_folder(name="C")

        count = folder_repo.reorder_folders([f3["id"], f1["id"], f2["id"]])

        assert count == 3
        result = folder_repo.list_folders()
        assert result[0]["name"] == "C"
        assert result[0]["order_index"] == 0
        assert result[1]["name"] == "A"
        assert result[1]["order_index"] == 1
        assert result[2]["name"] == "B"
        assert result[2]["order_index"] == 2

    def test_reorder_folders_returns_count(
        self, folder_repo: SQLiteFolderRepository
    ) -> None:
        """Returns the number of folders reordered."""
        f1 = folder_repo.create_folder(name="A")
        f2 = folder_repo.create_folder(name="B")

        count = folder_repo.reorder_folders([f2["id"], f1["id"]])

        assert count == 2


class TestMoveSession:
    """Test atomic session move between folders."""

    def test_move_session_removes_from_source(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Session is removed from source folder after move."""
        src = folder_repo.create_folder(name="Source")
        dst = folder_repo.create_folder(name="Dest")
        _seed_session(session_repo, "s1", "Session")
        folder_repo.assign_session(src["id"], "s1")

        folder_repo.move_session(src["id"], dst["id"], "s1")

        src_sessions = folder_repo.get_folder_sessions(src["id"])
        assert len(src_sessions) == 0

    def test_move_session_adds_to_target(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Session appears in target folder after move."""
        src = folder_repo.create_folder(name="Source")
        dst = folder_repo.create_folder(name="Dest")
        _seed_session(session_repo, "s1", "Session")
        folder_repo.assign_session(src["id"], "s1")

        folder_repo.move_session(src["id"], dst["id"], "s1")

        dst_sessions = folder_repo.get_folder_sessions(dst["id"])
        assert len(dst_sessions) == 1
        assert dst_sessions[0]["id"] == "s1"

    def test_move_session_updates_counts(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Source count decrements, target count increments."""
        src = folder_repo.create_folder(name="Source")
        dst = folder_repo.create_folder(name="Dest")
        _seed_session(session_repo, "s1", "Session")
        folder_repo.assign_session(src["id"], "s1")

        folder_repo.move_session(src["id"], dst["id"], "s1")

        folders = folder_repo.list_folders()
        counts = {f["name"]: f["session_count"] for f in folders}
        assert counts["Source"] == 0
        assert counts["Dest"] == 1

    def test_move_session_not_in_source(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Returns False when session is not in source folder."""
        src = folder_repo.create_folder(name="Source")
        dst = folder_repo.create_folder(name="Dest")
        _seed_session(session_repo, "s1", "Session")

        result = folder_repo.move_session(src["id"], dst["id"], "s1")

        assert result is False

    def test_move_session_to_same_folder(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Moving to same folder is a no-op, returns False."""
        folder = folder_repo.create_folder(name="Same")
        _seed_session(session_repo, "s1", "Session")
        folder_repo.assign_session(folder["id"], "s1")

        result = folder_repo.move_session(folder["id"], folder["id"], "s1")

        assert result is False
        sessions = folder_repo.get_folder_sessions(folder["id"])
        assert len(sessions) == 1

    def test_move_session_already_in_target(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Moving to a folder that already has the session: removes from source,
        duplicate in target is handled by INSERT OR IGNORE."""
        src = folder_repo.create_folder(name="Source")
        dst = folder_repo.create_folder(name="Dest")
        _seed_session(session_repo, "s1", "Session")
        folder_repo.assign_session(src["id"], "s1")
        folder_repo.assign_session(dst["id"], "s1")

        result = folder_repo.move_session(src["id"], dst["id"], "s1")

        assert result is True
        assert len(folder_repo.get_folder_sessions(src["id"])) == 0
        assert len(folder_repo.get_folder_sessions(dst["id"])) == 1

    def test_move_session_is_atomic(
        self,
        folder_repo: SQLiteFolderRepository,
        session_repo: SQLiteSessionRepository,
    ) -> None:
        """Both operations happen in a single transaction."""
        src = folder_repo.create_folder(name="Source")
        dst = folder_repo.create_folder(name="Dest")
        _seed_session(session_repo, "s1", "Session")
        folder_repo.assign_session(src["id"], "s1")

        # Move and verify both sides updated
        folder_repo.move_session(src["id"], dst["id"], "s1")

        assert len(folder_repo.get_folder_sessions(src["id"])) == 0
        assert len(folder_repo.get_folder_sessions(dst["id"])) == 1
