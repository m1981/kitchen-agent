"""
tests/integration/test_import_endpoint.py
==========================================
Integration tests for POST /api/sessions/import endpoint.

Tests the HTTP contract, request validation, and response schema.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.dependencies import get_import_service
from src.schemas import ImportResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_service() -> MagicMock:
    """Mock ImportService."""
    service = MagicMock()
    return service


@pytest.fixture
def client(mock_service: MagicMock) -> TestClient:
    """TestClient with mocked ImportService."""
    app.dependency_overrides[get_import_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------

class TestRequestValidation:
    """Test request body validation."""

    def test_missing_messages_returns_422(self, client: TestClient) -> None:
        """Missing messages field returns 422 Unprocessable Entity."""
        response = client.post("/api/sessions/import", json={})
        assert response.status_code == 422

    def test_empty_messages_list_accepted(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Empty messages list is accepted (service will validate)."""
        mock_service.import_chat.side_effect = ValueError("Messages list cannot be empty.")
        response = client.post("/api/sessions/import", json={"messages": []})
        assert response.status_code == 400

    def test_missing_role_returns_422(self, client: TestClient) -> None:
        """Message without role returns 422."""
        response = client.post(
            "/api/sessions/import",
            json={"messages": [{"content": "Hello"}]},
        )
        assert response.status_code == 422

    def test_missing_content_returns_422(self, client: TestClient) -> None:
        """Message without content returns 422."""
        response = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user"}]},
        )
        assert response.status_code == 422

    def test_valid_minimal_request(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Valid minimal request returns 201."""
        mock_service.import_chat.return_value = ImportResponse(
            session_id="test-id",
            title="Hello",
            message_count=1,
            turn_count=1,
        )
        response = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert response.status_code == 201

    def test_valid_full_request(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Valid full request with all optional fields returns 201."""
        mock_service.import_chat.return_value = ImportResponse(
            session_id="test-id",
            title="Custom Title",
            message_count=2,
            turn_count=2,
        )
        response = client.post(
            "/api/sessions/import",
            json={
                "title": "Custom Title",
                "messages": [
                    {"role": "user", "content": "Hello", "provider": "openai", "model": "gpt-4"},
                    {"role": "assistant", "content": "Hi!", "provider": "openai", "model": "gpt-4"},
                ],
                "system_prompt": "You are helpful.",
            },
        )
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class TestResponseSchema:
    """Test response body schema."""

    def test_has_required_fields(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Response contains all required fields."""
        mock_service.import_chat.return_value = ImportResponse(
            session_id="test-session-id",
            title="Test Title",
            message_count=2,
            turn_count=2,
        )
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ]
            },
        )

        data = response.json()
        assert "session_id" in data
        assert "title" in data
        assert "message_count" in data
        assert "turn_count" in data

    def test_session_id_is_string(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """session_id is a string."""
        mock_service.import_chat.return_value = ImportResponse(
            session_id="abc-123",
            title="Test",
            message_count=1,
            turn_count=1,
        )
        response = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )

        data = response.json()
        assert isinstance(data["session_id"], str)

    def test_message_count_is_integer(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """message_count is an integer."""
        mock_service.import_chat.return_value = ImportResponse(
            session_id="test-id",
            title="Test",
            message_count=5,
            turn_count=5,
        )
        response = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )

        data = response.json()
        assert isinstance(data["message_count"], int)

    def test_turn_count_is_integer(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """turn_count is an integer."""
        mock_service.import_chat.return_value = ImportResponse(
            session_id="test-id",
            title="Test",
            message_count=2,
            turn_count=2,
        )
        response = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )

        data = response.json()
        assert isinstance(data["turn_count"], int)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test error scenarios."""

    def test_service_value_error_returns_400(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Service ValueError returns 400 Bad Request."""
        mock_service.import_chat.side_effect = ValueError("Messages list cannot be empty.")
        response = client.post(
            "/api/sessions/import",
            json={"messages": []},
        )

        assert response.status_code == 400
        assert "Messages list cannot be empty" in response.json()["detail"]

    def test_service_unexpected_error_returns_500(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Service unexpected error returns 500 Internal Server Error."""
        mock_service.import_chat.side_effect = RuntimeError("Database connection failed")
        response = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )

        assert response.status_code == 500
        assert "Failed to import chat session" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Provider/model metadata
# ---------------------------------------------------------------------------

class TestProviderModelMetadata:
    """Test provider/model fields in request."""

    def test_provider_field_accepted(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Provider field is accepted in request messages."""
        mock_service.import_chat.return_value = ImportResponse(
            session_id="test-id",
            title="Test",
            message_count=1,
            turn_count=1,
        )
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello", "provider": "openai"},
                ]
            },
        )

        assert response.status_code == 201

    def test_model_field_accepted(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Model field is accepted in request messages."""
        mock_service.import_chat.return_value = ImportResponse(
            session_id="test-id",
            title="Test",
            message_count=1,
            turn_count=1,
        )
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello", "model": "gpt-4"},
                ]
            },
        )

        assert response.status_code == 201

    def test_provider_model_optional(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Provider and model fields are optional."""
        mock_service.import_chat.return_value = ImportResponse(
            session_id="test-id",
            title="Test",
            message_count=1,
            turn_count=1,
        )
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                ]
            },
        )

        assert response.status_code == 201
