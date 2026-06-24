"""
tests/test_token_routes.py
==========================
FastAPI integration tests for the token-counting endpoints.

Endpoints under test
--------------------
GET  /api/sessions/{session_id}/tokens
    → returns token count for all turns stored in the session so far
    → 404 when session not found

POST /api/tokens/estimate
    → returns heuristic TokenEstimate for a pending (not-yet-sent) context
    → works when images / context_files / system_prompt are absent (optional)

All Gemini API calls and filesystem reads are mocked.
The test client uses the FastAPI dependency-injection override pattern
consistent with the rest of the test suite.
"""
from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.repositories import SQLiteConnection, SQLiteSessionRepository


# ---------------------------------------------------------------------------
# Minimal in-memory session fixture
# ---------------------------------------------------------------------------

def _make_session_repo(tmp_path) -> SQLiteSessionRepository:
    db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    return SQLiteSessionRepository(db)


def _seed_session(repo: SQLiteSessionRepository, session_id: str, turns: int = 2) -> None:
    """Persist a session with *turns* user+model turn pairs."""
    api_items: list[dict] = []
    ui_items: list[dict] = []
    for i in range(turns):
        api_items.append({"role": "user", "type": "text", "data": f"User message {i}", "turn_id": f"u{i}"})
        api_items.append({"role": "model", "type": "text", "data": f"Model answer {i}", "turn_id": f"a{i}"})
        ui_items.append({"role": "user", "content": f"User message {i}", "turn_id": f"u{i}"})
        ui_items.append({"role": "assistant", "content": f"Model answer {i}", "turn_id": f"a{i}"})

    repo.save_session(
        session_id=session_id,
        title="Test session",
        api_history_json=json.dumps(api_items),
        ui_history_json=json.dumps(ui_items),
        system_prompt="You are a kitchen designer.",
    )


# ---------------------------------------------------------------------------
# Route: GET /api/sessions/{session_id}/tokens
# ---------------------------------------------------------------------------

class TestSessionTokensRoute:

    @pytest.fixture()
    def client_with_session(self, tmp_path):
        repo = _make_session_repo(tmp_path)
        _seed_session(repo, session_id="sess-abc", turns=2)

        app.dependency_overrides[
            __import__("src.dependencies", fromlist=["get_session_repo"]).get_session_repo
        ] = lambda: repo

        with patch("src.token_counter._client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.total_tokens = 312
            mock_client.models.count_tokens.return_value = mock_resp
            yield TestClient(app), mock_client

        app.dependency_overrides.clear()

    def test_returns_200_with_token_fields(self, client_with_session) -> None:
        client, _ = client_with_session
        resp = client.get("/api/sessions/sess-abc/tokens")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tokens" in data
        assert "fallback_used" in data
        assert "session_id" in data
        assert data["session_id"] == "sess-abc"

    def test_token_count_positive(self, client_with_session) -> None:
        client, _ = client_with_session
        resp = client.get("/api/sessions/sess-abc/tokens")
        assert resp.status_code == 200
        assert resp.json()["total_tokens"] > 0

    def test_api_count_tokens_called_once(self, client_with_session) -> None:
        client, mock_client = client_with_session
        client.get("/api/sessions/sess-abc/tokens")
        mock_client.models.count_tokens.assert_called_once()

    def test_unknown_session_returns_zero_tokens(self, tmp_path) -> None:
        """
        The repository returns ("[]", "[]", None) for missing sessions
        (same as empty).  The token endpoint follows the same convention:
        200 with total_tokens=0 rather than 404 — consistent with GET
        /api/sessions/{id} which also returns 200+empty for unknown IDs.
        """
        repo = _make_session_repo(tmp_path)
        app.dependency_overrides[
            __import__("src.dependencies", fromlist=["get_session_repo"]).get_session_repo
        ] = lambda: repo
        try:
            with patch("src.token_counter._client"):  # no API call expected
                client = TestClient(app)
                resp = client.get("/api/sessions/nonexistent-id/tokens")
            assert resp.status_code == 200
            assert resp.json()["total_tokens"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_empty_session_returns_zero_tokens(self, tmp_path) -> None:
        repo = _make_session_repo(tmp_path)
        repo.save_session(
            session_id="empty-sess",
            title="empty",
            api_history_json="[]",
            ui_history_json="[]",
        )
        app.dependency_overrides[
            __import__("src.dependencies", fromlist=["get_session_repo"]).get_session_repo
        ] = lambda: repo

        try:
            with patch("src.token_counter._client") as mock_client:
                client = TestClient(app)
                resp = client.get("/api/sessions/empty-sess/tokens")
            assert resp.status_code == 200
            assert resp.json()["total_tokens"] == 0
            mock_client.models.count_tokens.assert_not_called()
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Route: POST /api/tokens/estimate
# ---------------------------------------------------------------------------

class TestTokensEstimateRoute:

    def test_plain_message_returns_estimate(self, tmp_path) -> None:
        """Minimal payload — only user_message required."""
        client = TestClient(app)
        payload = {"user_message": "How thick should the shelf be?"}
        resp = client.post("/api/tokens/estimate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["text_tokens"] > 0
        assert data["total_tokens"] > 0
        assert data["fallback_used"] is True  # heuristic, no API call

    def test_with_image_increases_token_count(self) -> None:
        small_png = base64.b64encode(b"\x89PNG" + b"\x00" * 2000).decode()
        client = TestClient(app)
        payload_text = {"user_message": "Look at this image"}
        payload_with_img = {
            "user_message": "Look at this image",
            "images": [{"mime_type": "image/png", "data": small_png}],
        }
        resp_text = client.post("/api/tokens/estimate", json=payload_text)
        resp_img = client.post("/api/tokens/estimate", json=payload_with_img)

        assert resp_text.status_code == 200
        assert resp_img.status_code == 200
        assert resp_img.json()["image_tokens"] > 0
        assert resp_img.json()["total_tokens"] > resp_text.json()["total_tokens"]

    @patch("src.api.chat.read_file")
    def test_with_context_files_increases_token_count(self, mock_rf: MagicMock) -> None:
        mock_rf.return_value = {"content": "Wood 18mm plywood " * 80}
        client = TestClient(app)
        payload = {
            "user_message": "Check the materials",
            "context_files": ["data/materials.md"],
        }
        resp = client.post("/api/tokens/estimate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["context_file_tokens"] > 0

    def test_with_system_prompt_increases_token_count(self) -> None:
        client = TestClient(app)
        payload_no_prompt = {"user_message": "hi"}
        payload_with_prompt = {
            "user_message": "hi",
            "system_prompt": "You are an expert kitchen cabinet designer in Wrocław, Poland.",
        }
        resp_no = client.post("/api/tokens/estimate", json=payload_no_prompt)
        resp_with = client.post("/api/tokens/estimate", json=payload_with_prompt)

        assert resp_no.status_code == 200
        assert resp_with.status_code == 200
        assert resp_with.json()["system_prompt_tokens"] > 0
        assert resp_with.json()["total_tokens"] > resp_no.json()["total_tokens"]

    def test_with_history_token_count_forwarded(self) -> None:
        client = TestClient(app)
        payload = {
            "user_message": "next question",
            "history_token_count": 800,
        }
        resp = client.post("/api/tokens/estimate", json=payload)
        assert resp.status_code == 200
        assert resp.json()["history_tokens"] == 800

    def test_total_is_sum_of_parts(self) -> None:
        client = TestClient(app)
        payload = {
            "user_message": "what is 18mm birch ply",
            "system_prompt": "You are helpful.",
            "history_token_count": 50,
        }
        resp = client.post("/api/tokens/estimate", json=payload)
        assert resp.status_code == 200
        d = resp.json()
        expected = (
            d["text_tokens"]
            + d["image_tokens"]
            + d["context_file_tokens"]
            + d["system_prompt_tokens"]
            + d["history_tokens"]
        )
        assert d["total_tokens"] == expected

    def test_all_optional_fields_absent(self) -> None:
        """Request with only user_message must not crash."""
        client = TestClient(app)
        resp = client.post("/api/tokens/estimate", json={"user_message": "ok"})
        assert resp.status_code == 200

    def test_missing_user_message_returns_422(self) -> None:
        client = TestClient(app)
        resp = client.post("/api/tokens/estimate", json={})
        assert resp.status_code == 422
