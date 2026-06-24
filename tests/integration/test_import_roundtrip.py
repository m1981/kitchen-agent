"""
tests/integration/test_import_roundtrip.py
===========================================
Integration tests for import → export round-trip.

Verifies that:
1. Imported sessions are persisted correctly
2. Imported sessions can be listed via GET /api/sessions
3. Imported sessions can be exported via existing export endpoints
4. Imported sessions work with existing session operations (fork, delete, etc.)

Uses real SQLite database (no mocks) for full integration verification.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.dependencies import get_session_repo, get_import_service
from src.repositories import SQLiteConnection, SQLiteSessionRepository
from src.import_service import ImportService
from src.token_counter import TokenCounter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> SQLiteConnection:
    """Temporary SQLite database."""
    return SQLiteConnection(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def session_repo(tmp_db: SQLiteConnection) -> SQLiteSessionRepository:
    """Session repository backed by temporary database."""
    return SQLiteSessionRepository(tmp_db)


@pytest.fixture
def token_counter() -> TokenCounter:
    """Real token counter (not mocked)."""
    return TokenCounter()


@pytest.fixture
def import_service(
    session_repo: SQLiteSessionRepository,
    token_counter: TokenCounter,
) -> ImportService:
    """Real ImportService with real dependencies."""
    return ImportService(session_repo=session_repo, token_counter=token_counter)


@pytest.fixture
def client(
    session_repo: SQLiteSessionRepository,
    import_service: ImportService,
) -> TestClient:
    """TestClient with real services."""
    app.dependency_overrides[get_session_repo] = lambda: session_repo
    app.dependency_overrides[get_import_service] = lambda: import_service
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Import → List round-trip
# ---------------------------------------------------------------------------

class TestImportThenList:
    """Verify imported sessions appear in session list."""

    def test_imported_session_appears_in_list(
        self, client: TestClient, session_repo: SQLiteSessionRepository
    ) -> None:
        """Imported session is visible in GET /api/sessions."""
        # Import a session
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ]
            },
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]

        # List sessions
        list_response = client.get("/api/sessions")
        assert list_response.status_code == 200

        sessions = list_response.json()
        session_ids = [s["id"] for s in sessions]
        assert session_id in session_ids

    def test_imported_session_has_correct_title(
        self, client: TestClient
    ) -> None:
        """Imported session has the auto-generated title."""
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Kitchen design tips"},
                    {"role": "assistant", "content": "Here are some tips..."},
                ]
            },
        )
        session_id = response.json()["session_id"]

        # Get title from sessions list
        list_response = client.get("/api/sessions")
        sessions = list_response.json()
        session = next(s for s in sessions if s["id"] == session_id)
        assert session["title"] == "Kitchen design tips"

    def test_imported_session_with_custom_title(
        self, client: TestClient
    ) -> None:
        """Imported session uses custom title when provided."""
        response = client.post(
            "/api/sessions/import",
            json={
                "title": "My Custom Title",
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ],
            },
        )
        session_id = response.json()["session_id"]

        # Get title from sessions list
        list_response = client.get("/api/sessions")
        sessions = list_response.json()
        session = next(s for s in sessions if s["id"] == session_id)
        assert session["title"] == "My Custom Title"


# ---------------------------------------------------------------------------
# Import → Export round-trip
# ---------------------------------------------------------------------------

class TestImportThenExport:
    """Verify imported sessions can be exported."""

    def test_import_then_markdown_export(
        self, client: TestClient
    ) -> None:
        """Imported session can be exported as markdown."""
        # Import
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "What are good materials?"},
                    {"role": "assistant", "content": "Consider granite and quartz."},
                ]
            },
        )
        session_id = response.json()["session_id"]

        # Export as markdown
        export_response = client.get(f"/api/sessions/{session_id}/export")
        assert export_response.status_code == 200

        markdown = export_response.text
        assert "What are good materials?" in markdown
        assert "Consider granite and quartz." in markdown

    def test_import_then_llm_export(
        self, client: TestClient
    ) -> None:
        """Imported session can be exported as LLM JSON."""
        # Import
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ]
            },
        )
        session_id = response.json()["session_id"]

        # Export as LLM JSON
        export_response = client.get(f"/api/sessions/{session_id}/export/llm")
        assert export_response.status_code == 200

        data = export_response.json()
        assert "metadata" in data
        assert "turns" in data
        assert len(data["turns"]) == 2

    def test_import_preserves_all_messages_in_export(
        self, client: TestClient
    ) -> None:
        """All imported messages are present in export."""
        messages = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
            {"role": "assistant", "content": "Second answer"},
        ]
        response = client.post(
            "/api/sessions/import",
            json={"messages": messages},
        )
        session_id = response.json()["session_id"]

        # Export as markdown
        export_response = client.get(f"/api/sessions/{session_id}/export")
        markdown = export_response.text

        assert "First question" in markdown
        assert "First answer" in markdown
        assert "Second question" in markdown
        assert "Second answer" in markdown


# ---------------------------------------------------------------------------
# Import → Session operations
# ---------------------------------------------------------------------------

class TestImportThenOperations:
    """Verify imported sessions work with session operations."""

    def test_import_then_delete(
        self, client: TestClient
    ) -> None:
        """Imported session can be deleted."""
        # Import
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ]
            },
        )
        session_id = response.json()["session_id"]

        # Delete
        delete_response = client.delete(f"/api/sessions/{session_id}")
        assert delete_response.status_code == 204

        # Verify gone
        get_response = client.get(f"/api/sessions/{session_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data == {} or "id" not in data

    def test_import_then_update_title(
        self, client: TestClient
    ) -> None:
        """Imported session title can be updated."""
        # Import
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Original title source"},
                    {"role": "assistant", "content": "Response"},
                ]
            },
        )
        session_id = response.json()["session_id"]

        # Update title
        update_response = client.patch(
            f"/api/sessions/{session_id}/title",
            json={"title": "New Custom Title"},
        )
        assert update_response.status_code == 200

        # Verify update via sessions list
        list_response = client.get("/api/sessions")
        sessions = list_response.json()
        session = next(s for s in sessions if s["id"] == session_id)
        assert session["title"] == "New Custom Title"

    def test_import_then_archive(
        self, client: TestClient
    ) -> None:
        """Imported session can be archived."""
        # Import
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ]
            },
        )
        session_id = response.json()["session_id"]

        # Archive (PATCH method)
        archive_response = client.patch(f"/api/sessions/{session_id}/archive")
        assert archive_response.status_code == 200

        # Verify archived (not in default list)
        list_response = client.get("/api/sessions")
        sessions = list_response.json()
        session_ids = [s["id"] for s in sessions]
        assert session_id not in session_ids

        # Verify in archived list
        archived_response = client.get("/api/sessions?include_archived=true")
        archived_sessions = archived_response.json()
        archived_ids = [s["id"] for s in archived_sessions]
        assert session_id in archived_ids

    def test_import_then_unarchive(
        self, client: TestClient
    ) -> None:
        """Archived imported session can be unarchived."""
        # Import
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ]
            },
        )
        session_id = response.json()["session_id"]

        # Archive (PATCH) then unarchive (DELETE)
        client.patch(f"/api/sessions/{session_id}/archive")
        unarchive_response = client.delete(f"/api/sessions/{session_id}/archive")
        assert unarchive_response.status_code == 200

        # Verify back in default list
        list_response = client.get("/api/sessions")
        sessions = list_response.json()
        session_ids = [s["id"] for s in sessions]
        assert session_id in session_ids


# ---------------------------------------------------------------------------
# Import → Fork
# ---------------------------------------------------------------------------

class TestImportThenFork:
    """Verify imported sessions can be forked."""

    def test_import_then_fork(
        self, client: TestClient
    ) -> None:
        """Imported session can be forked at a turn index."""
        # Import a multi-turn session
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Turn 0"},
                    {"role": "assistant", "content": "Response 0"},
                    {"role": "user", "content": "Turn 1"},
                    {"role": "assistant", "content": "Response 1"},
                    {"role": "user", "content": "Turn 2"},
                    {"role": "assistant", "content": "Response 2"},
                ]
            },
        )
        session_id = response.json()["session_id"]

        # Fork at turn 1 (fork slices to turn_index + 1)
        fork_response = client.post(
            f"/api/sessions/{session_id}/fork",
            json={"turn_index": 1},
        )
        assert fork_response.status_code == 200

        fork_data = fork_response.json()
        new_session_id = fork_data["new_session_id"]
        assert new_session_id != session_id

        # Verify forked session exists and is in the list
        list_response = client.get("/api/sessions")
        sessions = list_response.json()
        session_ids = [s["id"] for s in sessions]
        assert new_session_id in session_ids


# ---------------------------------------------------------------------------
# Import with system prompt
# ---------------------------------------------------------------------------

class TestImportWithSystemPrompt:
    """Verify system prompt is preserved in imports."""

    def test_system_prompt_persisted(
        self, client: TestClient
    ) -> None:
        """System prompt is saved and retrievable."""
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ],
                "system_prompt": "You are a kitchen design expert.",
            },
        )
        session_id = response.json()["session_id"]

        # Get system prompt
        prompt_response = client.get(f"/api/sessions/{session_id}/system-prompt")
        assert prompt_response.status_code == 200

        data = prompt_response.json()
        assert data["system_prompt"] == "You are a kitchen design expert."

    def test_system_prompt_null_when_not_provided(
        self, client: TestClient
    ) -> None:
        """System prompt is null when not provided."""
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ],
            },
        )
        session_id = response.json()["session_id"]

        prompt_response = client.get(f"/api/sessions/{session_id}/system-prompt")
        assert prompt_response.status_code == 200

        data = prompt_response.json()
        assert data["system_prompt"] is None

    def test_system_prompt_exported_in_llm_json(
        self, client: TestClient
    ) -> None:
        """System prompt appears in LLM export config."""
        response = client.post(
            "/api/sessions/import",
            json={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ],
                "system_prompt": "Expert system prompt",
            },
        )
        session_id = response.json()["session_id"]

        export_response = client.get(f"/api/sessions/{session_id}/export/llm")
        data = export_response.json()

        assert data["config"]["system_instruction"] == "Expert system prompt"


# ---------------------------------------------------------------------------
# Multiple imports
# ---------------------------------------------------------------------------

class TestMultipleImports:
    """Verify multiple imports create separate sessions."""

    def test_two_imports_create_two_sessions(
        self, client: TestClient
    ) -> None:
        """Each import creates a unique session."""
        response1 = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user", "content": "Chat 1"}]},
        )
        response2 = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user", "content": "Chat 2"}]},
        )

        assert response1.status_code == 201
        assert response2.status_code == 201

        id1 = response1.json()["session_id"]
        id2 = response2.json()["session_id"]

        assert id1 != id2

        # Both should be in list
        list_response = client.get("/api/sessions")
        sessions = list_response.json()
        session_ids = [s["id"] for s in sessions]

        assert id1 in session_ids
        assert id2 in session_ids

    def test_imports_have_independent_content(
        self, client: TestClient
    ) -> None:
        """Each imported session has its own content."""
        response1 = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user", "content": "First chat"}]},
        )
        response2 = client.post(
            "/api/sessions/import",
            json={"messages": [{"role": "user", "content": "Second chat"}]},
        )

        id1 = response1.json()["session_id"]
        id2 = response2.json()["session_id"]

        # Export both
        export1 = client.get(f"/api/sessions/{id1}/export")
        export2 = client.get(f"/api/sessions/{id2}/export")

        assert "First chat" in export1.text
        assert "Second chat" not in export1.text

        assert "Second chat" in export2.text
        assert "First chat" not in export2.text
