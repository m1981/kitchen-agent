"""
tests/unit/services/test_folder_service.py
==========================================
Unit tests for FolderService — the business-logic layer for folders.

All external I/O (DB) is mocked so these tests run instantly.
"""

from unittest.mock import MagicMock

import pytest

from src.folder_service import FolderService
from src.schemas import FolderCreateRequest, FolderUpdateRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_repo() -> MagicMock:
    """Mock FolderRepository."""
    repo = MagicMock()
    return repo


@pytest.fixture
def service(mock_repo: MagicMock) -> FolderService:
    """FolderService with mocked repository."""
    return FolderService(folder_repo=mock_repo)


# ---------------------------------------------------------------------------
# create_folder
# ---------------------------------------------------------------------------

class TestCreateFolder:
    """Test folder creation."""

    def test_create_folder_calls_repo(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service delegates to repository."""
        mock_repo.create_folder.return_value = {
            "id": "test-id",
            "name": "Test",
            "color": "#3B82F6",
            "icon": "📁",
            "parent_id": None,
            "order_index": 0,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }

        request = FolderCreateRequest(name="Test", color="#3B82F6")
        result = service.create_folder(request)

        mock_repo.create_folder.assert_called_once_with(
            name="Test",
            color="#3B82F6",
            icon="📁",
            parent_id=None,
            order_index=0,
        )

    def test_create_folder_returns_response(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service returns FolderResponse."""
        mock_repo.create_folder.return_value = {
            "id": "test-id",
            "name": "Test",
            "color": "#3B82F6",
            "icon": "📁",
            "parent_id": None,
            "order_index": 0,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }

        request = FolderCreateRequest(name="Test")
        result = service.create_folder(request)

        assert result.id == "test-id"
        assert result.name == "Test"
        assert result.color == "#3B82F6"

    def test_create_folder_with_parent(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service passes parent_id to repository."""
        mock_repo.create_folder.return_value = {
            "id": "child-id",
            "name": "Child",
            "color": "#6B7280",
            "icon": "📁",
            "parent_id": "parent-id",
            "order_index": 0,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }

        request = FolderCreateRequest(name="Child", parent_id="parent-id")
        result = service.create_folder(request)

        assert result.parent_id == "parent-id"


# ---------------------------------------------------------------------------
# list_folders
# ---------------------------------------------------------------------------

class TestListFolders:
    """Test folder listing."""

    def test_list_folders_calls_repo(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service delegates to repository."""
        mock_repo.list_folders.return_value = []

        result = service.list_folders()

        mock_repo.list_folders.assert_called_once()

    def test_list_folders_returns_empty(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Returns empty list when no folders."""
        mock_repo.list_folders.return_value = []

        result = service.list_folders()

        assert result.folders == []
        assert result.total == 0

    def test_list_folders_returns_all(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Returns all folders from repository."""
        mock_repo.list_folders.return_value = [
            {
                "id": "f1", "name": "Folder 1", "color": "#3B82F6", "icon": "📁",
                "parent_id": None, "order_index": 0, "session_count": 0,
                "created_at": "2026-01-01", "updated_at": "2026-01-01",
            },
            {
                "id": "f2", "name": "Folder 2", "color": "#22C55E", "icon": "🍳",
                "parent_id": None, "order_index": 1, "session_count": 3,
                "created_at": "2026-01-01", "updated_at": "2026-01-01",
            },
        ]

        result = service.list_folders()

        assert result.total == 2
        assert len(result.folders) == 2


# ---------------------------------------------------------------------------
# get_folder
# ---------------------------------------------------------------------------

class TestGetFolder:
    """Test getting a single folder."""

    def test_get_folder_calls_repo(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service delegates to repository."""
        mock_repo.get_folder.return_value = {
            "id": "test-id",
            "name": "Test",
            "color": "#3B82F6",
            "icon": "📁",
            "parent_id": None,
            "order_index": 0,
            "session_count": 0,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }

        result = service.get_folder("test-id")

        mock_repo.get_folder.assert_called_once_with("test-id")

    def test_get_folder_not_found(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Returns None when folder doesn't exist."""
        mock_repo.get_folder.return_value = None

        result = service.get_folder("nonexistent")

        assert result is None


# ---------------------------------------------------------------------------
# update_folder
# ---------------------------------------------------------------------------

class TestUpdateFolder:
    """Test folder updates."""

    def test_update_folder_calls_repo(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service delegates to repository."""
        mock_repo.update_folder.return_value = {
            "id": "test-id",
            "name": "Updated",
            "color": "#3B82F6",
            "icon": "📁",
            "parent_id": None,
            "order_index": 0,
            "session_count": 0,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }

        request = FolderUpdateRequest(name="Updated")
        result = service.update_folder("test-id", request)

        mock_repo.update_folder.assert_called_once_with(
            "test-id",
            name="Updated",
            color=None,
            icon=None,
            order_index=None,
        )

    def test_update_folder_partial(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Only specified fields are passed to repository."""
        mock_repo.update_folder.return_value = {
            "id": "test-id",
            "name": "Test",
            "color": "#22C55E",
            "icon": "📁",
            "parent_id": None,
            "order_index": 0,
            "session_count": 0,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }

        request = FolderUpdateRequest(color="#22C55E")
        result = service.update_folder("test-id", request)

        mock_repo.update_folder.assert_called_once_with(
            "test-id",
            name=None,
            color="#22C55E",
            icon=None,
            order_index=None,
        )

    def test_update_folder_not_found(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Returns None when folder doesn't exist."""
        mock_repo.update_folder.return_value = None

        request = FolderUpdateRequest(name="New")
        result = service.update_folder("nonexistent", request)

        assert result is None


# ---------------------------------------------------------------------------
# delete_folder
# ---------------------------------------------------------------------------

class TestDeleteFolder:
    """Test folder deletion."""

    def test_delete_folder_calls_repo(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service delegates to repository."""
        mock_repo.delete_folder.return_value = True

        result = service.delete_folder("test-id")

        mock_repo.delete_folder.assert_called_once_with("test-id")

    def test_delete_folder_returns_true(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Returns True when folder is deleted."""
        mock_repo.delete_folder.return_value = True

        result = service.delete_folder("test-id")

        assert result is True

    def test_delete_folder_not_found(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Returns False when folder doesn't exist."""
        mock_repo.delete_folder.return_value = False

        result = service.delete_folder("nonexistent")

        assert result is False


# ---------------------------------------------------------------------------
# assign_session / unassign_session
# ---------------------------------------------------------------------------

class TestSessionAssignment:
    """Test session-to-folder assignment."""

    def test_assign_session_calls_repo(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service delegates to repository."""
        mock_repo.assign_session.return_value = True

        result = service.assign_session("folder-id", "session-id")

        mock_repo.assign_session.assert_called_once_with("folder-id", "session-id")

    def test_unassign_session_calls_repo(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service delegates to repository."""
        mock_repo.unassign_session.return_value = True

        result = service.unassign_session("folder-id", "session-id")

        mock_repo.unassign_session.assert_called_once_with("folder-id", "session-id")

    def test_move_session_calls_repo(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service delegates to repository."""
        mock_repo.move_session.return_value = True

        result = service.move_session("src-folder", "dst-folder", "session-id")

        mock_repo.move_session.assert_called_once_with(
            "src-folder", "dst-folder", "session-id"
        )

    def test_move_session_returns_true(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Returns True on successful move."""
        mock_repo.move_session.return_value = True

        result = service.move_session("src", "dst", "s1")

        assert result is True

    def test_move_session_returns_false_when_not_in_source(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Returns False when session not in source folder."""
        mock_repo.move_session.return_value = False

        result = service.move_session("src", "dst", "s1")

        assert result is False


# ---------------------------------------------------------------------------
# get_folder_sessions
# ---------------------------------------------------------------------------

class TestGetFolderSessions:
    """Test getting sessions in a folder."""

    def test_get_folder_sessions_calls_repo(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Service delegates to repository."""
        mock_repo.get_folder_sessions.return_value = []

        result = service.get_folder_sessions("folder-id")

        mock_repo.get_folder_sessions.assert_called_once_with("folder-id")

    def test_get_folder_sessions_returns_list(
        self, service: FolderService, mock_repo: MagicMock
    ) -> None:
        """Returns list of sessions."""
        mock_repo.get_folder_sessions.return_value = [
            {"id": "s1", "title": "Session 1"},
            {"id": "s2", "title": "Session 2"},
        ]

        result = service.get_folder_sessions("folder-id")

        assert len(result) == 2
