"""
tests/test_context_files_ui.py
================================
TDD tests for persisting context_files on the UI message layer so that:

  1. The user bubble in ChatMessageList can show which files were attached.
  2. The attachment info survives session reload (loadSession after refresh).

Feature spec
------------
When a user sends a message with context_files the backend must store
the **display names** (basename of each resolved path) on the user
``ui_messages`` entry under the key ``"context_files"``.

Example stored entry::

    {
        "role": "user",
        "content": "What materials?",
        "turn_id": "<uuid>",
        "context_files": ["kuchnia-kroki.md", "materials.md"]
    }

The display name is the basename only (no absolute path, no data_dir prefix)
so the frontend can render it without knowing the server's filesystem layout.

Layers tested
-------------
A. ChatService — ``handle_turn`` persists ``context_files`` on ui_message
B. GET /api/sessions/{id} — returns ``context_files`` in ``ui_messages``
C. Regression — no ``context_files`` on message when none were sent
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.config as config_module
import src.dependencies as main_module
from src import config
from src.main import app
from src.dependencies import get_session_repo, get_chat_service
from src.repositories import SQLiteConnection, SQLiteSessionRepository
from src.chat_service import ChatService
from src.agent.turn_orchestrator import TurnInput
from tests.helpers import FakeOrchestrator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path: Path) -> SQLiteConnection:
    return SQLiteConnection(tmp_path / "chats.db")


@pytest.fixture()
def repo(tmp_db: SQLiteConnection) -> SQLiteSessionRepository:
    return SQLiteSessionRepository(tmp_db)


@pytest.fixture()
def service(repo: SQLiteSessionRepository) -> ChatService:
    return ChatService(
        session_repo=repo,
        turn_orchestrator=FakeOrchestrator(),
    )


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    (d / "materials.md").write_text("# Materials\n18mm Birch.\n", encoding="utf-8")
    (d / "kuchnia-kroki.md").write_text("# Steps\nStep 1.\n", encoding="utf-8")
    return d


@pytest.fixture()
def client(repo: SQLiteSessionRepository, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(config_module.settings, "data_dir", data_dir)
    monkeypatch.setattr(config.settings, "data_dir", data_dir)
    app.dependency_overrides[get_session_repo] = lambda: repo
    app.dependency_overrides[get_chat_service] = lambda: ChatService(
        session_repo=repo,
        turn_orchestrator=FakeOrchestrator(),
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# A. ChatService unit tests
# ---------------------------------------------------------------------------

class TestChatServiceContextFilesOnUiMessage:

    def test_context_files_stored_on_user_ui_message(
        self, service: ChatService, repo: SQLiteSessionRepository
    ) -> None:
        """
        When handle_turn is called with context_files, the user entry in
        ui_messages must contain a 'context_files' key with the basenames.
        """
        service.handle_turn(TurnInput(
            session_id="sess-1", user_message="What materials?", context_files=["/abs/path/data/materials.md"]
        ))

        _, ui_json, _ = repo.load_session("sess-1")
        ui = json.loads(ui_json)
        user_msg = next(m for m in ui if m["role"] == "user")
        assert "context_files" in user_msg
        assert user_msg["context_files"] == ["materials.md"]

    def test_context_files_basenames_only(
        self, service: ChatService, repo: SQLiteSessionRepository
    ) -> None:
        """Stored values must be basenames, not full paths."""
        service.handle_turn(TurnInput(
            session_id="sess-2", user_message="Help", context_files=[
        "/long/path/to/data/kuchnia-kroki.md",
        "/long/path/to/data/materials.md",
        ]
        ))

        _, ui_json, _ = repo.load_session("sess-2")
        ui = json.loads(ui_json)
        user_msg = next(m for m in ui if m["role"] == "user")
        assert user_msg["context_files"] == ["kuchnia-kroki.md", "materials.md"]

    def test_multiple_context_files_all_stored(
        self, service: ChatService, repo: SQLiteSessionRepository
    ) -> None:
        """All files in the list must be stored, not just the first."""
        service.handle_turn(TurnInput(
            session_id="sess-3", user_message="Help", context_files=["/data/a.md", "/data/b.md", "/data/c.md"]
        ))

        _, ui_json, _ = repo.load_session("sess-3")
        ui = json.loads(ui_json)
        user_msg = next(m for m in ui if m["role"] == "user")
        assert len(user_msg["context_files"]) == 3
        assert set(user_msg["context_files"]) == {"a.md", "b.md", "c.md"}

    def test_no_context_files_key_absent_when_none_sent(
        self, service: ChatService, repo: SQLiteSessionRepository
    ) -> None:
        """When no context_files are passed the key must NOT appear on ui_message."""
        service.handle_turn(TurnInput(
            session_id="sess-4", user_message="Hello", context_files=None
        ))

        _, ui_json, _ = repo.load_session("sess-4")
        ui = json.loads(ui_json)
        user_msg = next(m for m in ui if m["role"] == "user")
        assert "context_files" not in user_msg

    def test_no_context_files_key_absent_when_empty_list(
        self, service: ChatService, repo: SQLiteSessionRepository
    ) -> None:
        """Empty list behaves the same as None — key absent on ui_message."""
        service.handle_turn(TurnInput(
            session_id="sess-5", user_message="Hello", context_files=[]
        ))

        _, ui_json, _ = repo.load_session("sess-5")
        ui = json.loads(ui_json)
        user_msg = next(m for m in ui if m["role"] == "user")
        assert "context_files" not in user_msg

    def test_assistant_message_has_no_context_files(
        self, service: ChatService, repo: SQLiteSessionRepository
    ) -> None:
        """The assistant ui_message must never have a context_files key."""
        service.handle_turn(TurnInput(
            session_id="sess-6", user_message="Help", context_files=["/data/materials.md"]
        ))

        _, ui_json, _ = repo.load_session("sess-6")
        ui = json.loads(ui_json)
        asst_msg = next(m for m in ui if m["role"] == "assistant")
        assert "context_files" not in asst_msg

    def test_context_files_survives_second_turn(
        self, service: ChatService, repo: SQLiteSessionRepository
    ) -> None:
        """
        After a second turn without context_files, the first turn's
        context_files entry must still be present in ui_messages.
        """
        service.handle_turn(TurnInput(
            session_id="sess-7", user_message="Turn 1", context_files=["/data/materials.md"]
        ))
        service.handle_turn(TurnInput(
            session_id="sess-7", user_message="Turn 2", context_files=None
        ))

        _, ui_json, _ = repo.load_session("sess-7")
        ui = json.loads(ui_json)
        user_msgs = [m for m in ui if m["role"] == "user"]
        assert len(user_msgs) == 2
        # First turn has context_files
        assert user_msgs[0]["context_files"] == ["materials.md"]
        # Second turn does NOT
        assert "context_files" not in user_msgs[1]

    def test_bare_relative_filename_stored_as_basename(
        self, service: ChatService, repo: SQLiteSessionRepository
    ) -> None:
        """
        Even if the path is already just 'materials.md' (no dir component),
        the stored value must be 'materials.md'.
        """
        service.handle_turn(TurnInput(
            session_id="sess-8", user_message="Help", context_files=["materials.md"]
        ))

        _, ui_json, _ = repo.load_session("sess-8")
        ui = json.loads(ui_json)
        user_msg = next(m for m in ui if m["role"] == "user")
        assert user_msg["context_files"] == ["materials.md"]


# ---------------------------------------------------------------------------
# B. HTTP endpoint tests — GET /api/sessions/{id} returns context_files
# ---------------------------------------------------------------------------

class TestGetSessionContextFilesInResponse:

    def test_context_files_in_ui_messages_via_api(
        self, client: TestClient, data_dir: Path
    ) -> None:
        """
        After sending a chat with context_files, GET /api/sessions/{id}
        must return the context_files on the user message.
        """
        resp = client.post("/api/chat", json={
            "session_id": "sess-api-1",
            "message": "What files do you see?",
            "context_files": ["materials.md"],
        })
        assert resp.status_code == 200

        session_resp = client.get("/api/sessions/sess-api-1")
        assert session_resp.status_code == 200
        ui_messages = session_resp.json()["ui_messages"]

        user_msg = next(m for m in ui_messages if m["role"] == "user")
        assert "context_files" in user_msg
        assert user_msg["context_files"] == ["materials.md"]

    def test_context_files_absent_when_not_sent(
        self, client: TestClient
    ) -> None:
        """
        When no context_files are attached, the user message returned by
        GET /api/sessions/{id} must not have the context_files key.
        """
        client.post("/api/chat", json={
            "session_id": "sess-api-2",
            "message": "Hello",
        })

        session_resp = client.get("/api/sessions/sess-api-2")
        ui_messages = session_resp.json()["ui_messages"]
        user_msg = next(m for m in ui_messages if m["role"] == "user")
        assert "context_files" not in user_msg

    def test_multiple_files_all_present_in_api_response(
        self, client: TestClient, data_dir: Path
    ) -> None:
        """All attached filenames must appear in the API response."""
        (data_dir / "kuchnia-kroki.md").write_text("steps", encoding="utf-8")

        client.post("/api/chat", json={
            "session_id": "sess-api-3",
            "message": "Help",
            "context_files": ["materials.md", "kuchnia-kroki.md"],
        })

        session_resp = client.get("/api/sessions/sess-api-3")
        ui_messages = session_resp.json()["ui_messages"]
        user_msg = next(m for m in ui_messages if m["role"] == "user")
        assert set(user_msg["context_files"]) == {"materials.md", "kuchnia-kroki.md"}

    def test_context_files_on_user_message_not_assistant(
        self, client: TestClient, data_dir: Path
    ) -> None:
        """The assistant message in the API response must NOT have context_files."""
        client.post("/api/chat", json={
            "session_id": "sess-api-4",
            "message": "Help",
            "context_files": ["materials.md"],
        })

        session_resp = client.get("/api/sessions/sess-api-4")
        ui_messages = session_resp.json()["ui_messages"]
        asst_msg = next(m for m in ui_messages if m["role"] == "assistant")
        assert "context_files" not in asst_msg

    def test_two_turns_second_without_files_still_returns_first(
        self, client: TestClient, data_dir: Path
    ) -> None:
        """
        After two turns where only the first had context_files, the session
        endpoint must still show the attachment on turn 1 and nothing on turn 2.
        """
        client.post("/api/chat", json={
            "session_id": "sess-api-5",
            "message": "Turn 1",
            "context_files": ["materials.md"],
        })
        client.post("/api/chat", json={
            "session_id": "sess-api-5",
            "message": "Turn 2",
        })

        session_resp = client.get("/api/sessions/sess-api-5")
        ui_messages = session_resp.json()["ui_messages"]
        user_msgs = [m for m in ui_messages if m["role"] == "user"]
        assert user_msgs[0].get("context_files") == ["materials.md"]
        assert "context_files" not in user_msgs[1]
