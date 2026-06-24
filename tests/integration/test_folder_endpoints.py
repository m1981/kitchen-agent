"""
tests/integration/test_folder_endpoints.py
==========================================
Integration tests for folder API endpoints.

Tests the HTTP contract, request validation, and response schema.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.dependencies import get_folder_service
from src.schemas import FolderListResponse, FolderResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_service() -> MagicMock:
    """Mock FolderService."""
    service = MagicMock()
    return service


@pytest.fixture
def client(mock_service: MagicMock) -> TestClient:
    """TestClient with mocked FolderService."""
    app.dependency_overrides[get_folder_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_folder_response(**kwargs) -> FolderResponse:
    """Helper to create a FolderResponse with defaults."""
    defaults = {
        "id": "test-folder-id",
        "name": "Test Folder",
        "color": "#3B82F6",
        "icon": "📁",
        "parent_id": None,
        "order_index": 0,
        "session_count": 0,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    defaults.update(kwargs)
    return FolderResponse(**defaults)


# ---------------------------------------------------------------------------
# POST /api/folders
# ---------------------------------------------------------------------------

class TestCreateFolder:
    """Test folder creation endpoint."""

    def test_returns_201_on_success(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Successful creation returns 201."""
        mock_service.create_folder.return_value = _make_folder_response()

        response = client.post(
            "/api/folders",
            json={"name": "Kitchen Projects"},
        )

        assert response.status_code == 201

    def test_returns_folder_data(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Response contains folder data."""
        mock_service.create_folder.return_value = _make_folder_response(
            id="new-id", name="My Folder"
        )

        response = client.post(
            "/api/folders",
            json={"name": "My Folder"},
        )

        data = response.json()
        assert data["id"] == "new-id"
        assert data["name"] == "My Folder"

    def test_accepts_color(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Color field is accepted."""
        mock_service.create_folder.return_value = _make_folder_response(color="#EF4444")

        response = client.post(
            "/api/folders",
            json={"name": "Red Folder", "color": "#EF4444"},
        )

        assert response.status_code == 201
        assert response.json()["color"] == "#EF4444"

    def test_accepts_icon(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Icon field is accepted."""
        mock_service.create_folder.return_value = _make_folder_response(icon="🍳")

        response = client.post(
            "/api/folders",
            json={"name": "Cooking", "icon": "🍳"},
        )

        assert response.status_code == 201
        assert response.json()["icon"] == "🍳"

    def test_missing_name_returns_422(self, client: TestClient) -> None:
        """Missing name returns 422."""
        response = client.post("/api/folders", json={})

        assert response.status_code == 422

    def test_empty_name_returns_422(self, client: TestClient) -> None:
        """Empty name returns 422."""
        response = client.post("/api/folders", json={"name": ""})

        assert response.status_code == 422

    def test_invalid_color_returns_422(self, client: TestClient) -> None:
        """Invalid color format returns 422."""
        response = client.post(
            "/api/folders",
            json={"name": "Test", "color": "red"},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/folders
# ---------------------------------------------------------------------------

class TestListFolders:
    """Test folder listing endpoint."""

    def test_returns_200(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 200 OK."""
        mock_service.list_folders.return_value = FolderListResponse(
            folders=[], total=0
        )

        response = client.get("/api/folders")

        assert response.status_code == 200

    def test_returns_empty_list(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Empty list when no folders."""
        mock_service.list_folders.return_value = FolderListResponse(
            folders=[], total=0
        )

        response = client.get("/api/folders")

        data = response.json()
        assert data["folders"] == []
        assert data["total"] == 0

    def test_returns_all_folders(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns all folders."""
        mock_service.list_folders.return_value = FolderListResponse(
            folders=[
                _make_folder_response(id="f1", name="Folder 1"),
                _make_folder_response(id="f2", name="Folder 2"),
            ],
            total=2,
        )

        response = client.get("/api/folders")

        data = response.json()
        assert data["total"] == 2
        assert len(data["folders"]) == 2


# ---------------------------------------------------------------------------
# GET /api/folders/{folder_id}
# ---------------------------------------------------------------------------

class TestGetFolder:
    """Test get folder endpoint."""

    def test_returns_200_when_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 200 when folder exists."""
        mock_service.get_folder.return_value = _make_folder_response()

        response = client.get("/api/folders/test-id")

        assert response.status_code == 200

    def test_returns_404_when_not_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 404 when folder doesn't exist."""
        mock_service.get_folder.return_value = None

        response = client.get("/api/folders/nonexistent")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/folders/{folder_id}
# ---------------------------------------------------------------------------

class TestUpdateFolder:
    """Test folder update endpoint."""

    def test_returns_200_on_success(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 200 on successful update."""
        mock_service.update_folder.return_value = _make_folder_response(name="Updated")

        response = client.patch(
            "/api/folders/test-id",
            json={"name": "Updated"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    def test_returns_404_when_not_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 404 when folder doesn't exist."""
        mock_service.update_folder.return_value = None

        response = client.patch(
            "/api/folders/nonexistent",
            json={"name": "New"},
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/folders/{folder_id}
# ---------------------------------------------------------------------------

class TestDeleteFolder:
    """Test folder deletion endpoint."""

    def test_returns_204_on_success(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 204 on successful deletion."""
        mock_service.delete_folder.return_value = True

        response = client.delete("/api/folders/test-id")

        assert response.status_code == 204

    def test_returns_404_when_not_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 404 when folder doesn't exist."""
        mock_service.delete_folder.return_value = False

        response = client.delete("/api/folders/nonexistent")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/folders/{folder_id}/sessions/{session_id}
# ---------------------------------------------------------------------------

class TestAssignSession:
    """Test session assignment endpoint."""

    def test_returns_201_on_success(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 201 on successful assignment."""
        mock_service.assign_session.return_value = True

        response = client.post("/api/folders/f1/sessions/s1")

        assert response.status_code == 201
        data = response.json()
        assert data["assigned"] is True
        assert data["folder_id"] == "f1"
        assert data["session_id"] == "s1"


# ---------------------------------------------------------------------------
# DELETE /api/folders/{folder_id}/sessions/{session_id}
# ---------------------------------------------------------------------------

class TestUnassignSession:
    """Test session unassignment endpoint."""

    def test_returns_204_on_success(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 204 on successful unassignment."""
        mock_service.unassign_session.return_value = True

        response = client.delete("/api/folders/f1/sessions/s1")

        assert response.status_code == 204

    def test_returns_404_when_not_assigned(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 404 when session wasn't assigned."""
        mock_service.unassign_session.return_value = False

        response = client.delete("/api/folders/f1/sessions/s1")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/folders/{folder_id}/sessions
# ---------------------------------------------------------------------------

class TestGetFolderSessions:
    """Test get folder sessions endpoint."""

    def test_returns_200_with_sessions(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns sessions in folder."""
        mock_service.get_folder.return_value = _make_folder_response()
        mock_service.get_folder_sessions.return_value = [
            {"id": "s1", "title": "Session 1"},
            {"id": "s2", "title": "Session 2"},
        ]

        response = client.get("/api/folders/f1/sessions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_returns_404_when_folder_not_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 404 when folder doesn't exist."""
        mock_service.get_folder.return_value = None

        response = client.get("/api/folders/nonexistent/sessions")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/folders/move-session
# ---------------------------------------------------------------------------


class TestMoveSession:
    """Test atomic session move between folders."""

    def test_returns_200_on_success(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 200 on successful move."""
        mock_service.move_session.return_value = True

        response = client.patch(
            "/api/folders/move-session",
            json={
                "session_id": "s1",
                "from_folder": "src-id",
                "to_folder": "dst-id",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["moved"] is True
        assert data["from_folder"] == "src-id"
        assert data["to_folder"] == "dst-id"

    def test_returns_404_when_not_in_source(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Returns 404 when session is not in source folder."""
        mock_service.move_session.return_value = False

        response = client.patch(
            "/api/folders/move-session",
            json={
                "session_id": "s1",
                "from_folder": "src-id",
                "to_folder": "dst-id",
            },
        )

        assert response.status_code == 404

    def test_missing_fields_returns_422(self, client: TestClient) -> None:
        """Missing required fields returns 422."""
        response = client.patch(
            "/api/folders/move-session",
            json={"session_id": "s1"},
        )

        assert response.status_code == 422

    def test_delegates_to_service(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Endpoint delegates to service with correct args."""
        mock_service.move_session.return_value = True

        client.patch(
            "/api/folders/move-session",
            json={
                "session_id": "s1",
                "from_folder": "src",
                "to_folder": "dst",
            },
        )

        mock_service.move_session.assert_called_once_with("src", "dst", "s1")
