"""
tests/test_notes.py
===================
"""
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import src.config as main_module
from src import config as config_module
from src.repositories import SQLiteConnection, SQLiteSessionRepository, SQLiteNoteRepository
from src.content.note_manager import Note, NoteManager
from src.main import app
from src.dependencies import get_session_repo, get_note_repo, get_note_manager


# ===========================================================================
# Shared helpers
# ===========================================================================

def _make_conn(tmp_path: Path) -> SQLiteConnection:
    return SQLiteConnection(db_path=str(tmp_path / "test.db"))


def _seed_session(repo: SQLiteSessionRepository, session_id: str = "sess-1") -> str:
    repo.save_session(
        session_id=session_id,
        title="Test session",
        api_history_json="[]",
        ui_history_json="[]",
    )
    return session_id


# ===========================================================================
# Section 1 — Repositories
# ===========================================================================

class TestAddNote:
    def test_returns_dict_with_all_fields(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)

        result = note_repo.add_note(
            session_id="sess-1",
            selected_text="18mm birch plywood",
            source_role="assistant",
            note="Check supplier pricing.",
        )

        assert result["session_id"] == "sess-1"
        assert result["selected_text"] == "18mm birch plywood"
        assert result["source_role"] == "assistant"
        assert result["note"] == "Check supplier pricing."
        assert "id" in result
        assert "created_at" in result

    def test_note_annotation_defaults_to_empty_string(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)

        result = note_repo.add_note(
            session_id="sess-1",
            selected_text="Blum hinge",
            source_role="user",
        )

        assert result["note"] == ""

    def test_note_is_persisted_and_retrievable(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)
        note_repo.add_note("sess-1", "Some text", "assistant")

        notes = note_repo.list_notes("sess-1")
        assert len(notes) == 1
        assert notes[0]["selected_text"] == "Some text"

    def test_raises_value_error_for_missing_session(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        note_repo = SQLiteNoteRepository(conn)

        with pytest.raises(ValueError, match="Session not found"):
            note_repo.add_note("ghost-session", "text", "user")

    def test_raises_value_error_for_empty_selected_text(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)

        with pytest.raises(ValueError, match="selected_text must not be empty"):
            note_repo.add_note("sess-1", "", "user")

    def test_raises_value_error_for_whitespace_only_text(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)

        with pytest.raises(ValueError, match="selected_text must not be empty"):
            note_repo.add_note("sess-1", "   \n\t  ", "user")

    def test_generated_ids_are_unique(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)

        r1 = note_repo.add_note("sess-1", "text one", "user")
        r2 = note_repo.add_note("sess-1", "text two", "user")

        assert r1["id"] != r2["id"]


class TestListNotes:
    def test_empty_list_for_session_with_no_notes(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)

        assert note_repo.list_notes("sess-1") == []

    def test_empty_list_for_nonexistent_session(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        note_repo = SQLiteNoteRepository(conn)

        assert note_repo.list_notes("ghost") == []

    def test_returns_notes_in_chronological_order(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)

        note_repo.add_note("sess-1", "first note", "user")
        time.sleep(0.01)
        note_repo.add_note("sess-1", "second note", "assistant")

        notes = note_repo.list_notes("sess-1")
        assert len(notes) == 2
        assert notes[0]["selected_text"] == "first note"
        assert notes[1]["selected_text"] == "second note"

    def test_notes_are_isolated_between_sessions(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo, "sess-A")
        _seed_session(session_repo, "sess-B")

        note_repo.add_note("sess-A", "note for A", "user")
        note_repo.add_note("sess-B", "note for B", "assistant")

        assert len(note_repo.list_notes("sess-A")) == 1
        assert note_repo.list_notes("sess-A")[0]["selected_text"] == "note for A"

        assert len(note_repo.list_notes("sess-B")) == 1
        assert note_repo.list_notes("sess-B")[0]["selected_text"] == "note for B"

    def test_all_expected_fields_present_in_row(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)
        note_repo.add_note("sess-1", "field check", "assistant", note="annotation")

        note = note_repo.list_notes("sess-1")[0]
        for field in ("id", "session_id", "selected_text", "note", "source_role", "created_at"):
            assert field in note, f"Missing field: {field}"


class TestDeleteNote:
    def test_returns_true_when_note_deleted(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)
        created = note_repo.add_note("sess-1", "to delete", "user")

        result = note_repo.delete_note(note_id=created["id"], session_id="sess-1")

        assert result is True
        assert note_repo.list_notes("sess-1") == []

    def test_returns_false_for_nonexistent_note_id(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)

        result = note_repo.delete_note(note_id="no-such-id", session_id="sess-1")

        assert result is False

    def test_cross_session_delete_is_rejected(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo, "sess-A")
        _seed_session(session_repo, "sess-B")
        created = note_repo.add_note("sess-A", "private note", "user")

        result = note_repo.delete_note(note_id=created["id"], session_id="sess-B")

        assert result is False
        assert len(note_repo.list_notes("sess-A")) == 1

    def test_deleting_one_note_leaves_others_intact(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)
        _seed_session(session_repo)
        keep = note_repo.add_note("sess-1", "keep me", "user")
        remove = note_repo.add_note("sess-1", "remove me", "assistant")

        note_repo.delete_note(note_id=remove["id"], session_id="sess-1")

        remaining = note_repo.list_notes("sess-1")
        assert len(remaining) == 1
        assert remaining[0]["id"] == keep["id"]


# ===========================================================================
# Section 2 — FastAPI HTTP endpoints
# ===========================================================================

@pytest.fixture
def conn(tmp_path: Path) -> SQLiteConnection:
    return _make_conn(tmp_path)

@pytest.fixture
def session_repo(conn: SQLiteConnection) -> SQLiteSessionRepository:
    return SQLiteSessionRepository(conn)

@pytest.fixture
def note_repo(conn: SQLiteConnection) -> SQLiteNoteRepository:
    return SQLiteNoteRepository(conn)

@pytest.fixture
def note_manager(note_repo: SQLiteNoteRepository) -> NoteManager:
    """Real NoteManager backed by SQLite repo — for integration tests."""
    return NoteManager(repo=note_repo)

@pytest.fixture
def client(session_repo: SQLiteSessionRepository, note_manager: NoteManager, tmp_path: Path, monkeypatch) -> TestClient:
    """TestClient wired through NoteManager (not repo directly)."""
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    app.dependency_overrides[get_session_repo] = lambda: session_repo
    app.dependency_overrides[get_note_manager] = lambda: note_manager
    yield TestClient(app)
    app.dependency_overrides.pop(get_session_repo, None)
    app.dependency_overrides.pop(get_note_manager, None)


@pytest.fixture
def session_id(session_repo: SQLiteSessionRepository) -> str:
    return _seed_session(session_repo)


# ---------------------------------------------------------------------------
# POST /api/sessions/{session_id}/notes
# ---------------------------------------------------------------------------

class TestCreateNoteEndpoint:
    def test_returns_201_with_note_payload(self, client: TestClient, session_id: str) -> None:
        resp = client.post(
            f"/api/sessions/{session_id}/notes",
            json={
                "selected_text": "Blum 71B3550 hinge",
                "source_role": "assistant",
                "note": "Order 50 units.",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["selected_text"] == "Blum 71B3550 hinge"
        assert body["source_role"] == "assistant"
        assert body["note"] == "Order 50 units."
        assert body["session_id"] == session_id
        assert "id" in body
        assert "created_at" in body

    def test_note_field_defaults_to_empty_string(self, client: TestClient, session_id: str) -> None:
        resp = client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "18mm board", "source_role": "user"},
        )
        assert resp.status_code == 201
        assert resp.json()["note"] == ""

    def test_returns_404_for_unknown_session(self, client: TestClient) -> None:
        resp = client.post(
            "/api/sessions/ghost-session/notes",
            json={"selected_text": "anything", "source_role": "user"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_returns_400_for_blank_selected_text(self, client: TestClient, session_id: str) -> None:
        resp = client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "   ", "source_role": "user"},
        )
        assert resp.status_code == 400

    def test_returns_422_when_selected_text_missing(self, client: TestClient, session_id: str) -> None:
        resp = client.post(
            f"/api/sessions/{session_id}/notes",
            json={"source_role": "user"},
        )
        assert resp.status_code == 422

    def test_returns_422_when_source_role_missing(self, client: TestClient, session_id: str) -> None:
        resp = client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "some text"},
        )
        assert resp.status_code == 422

    def test_api_uses_note_manager_not_repo_directly(
        self, session_repo: SQLiteSessionRepository, session_id: str, tmp_path: Path, monkeypatch,
    ) -> None:
        """Prove the route goes through NoteManager, not NoteRepository directly."""
        mock_manager = MagicMock(spec=NoteManager)
        mock_manager.create.return_value = Note(
            id="mock-id",
            session_id=session_id,
            selected_text="test text",
            note="",
            source_role="user",
            created_at="2026-01-01T00:00:00",
        )
        mock_manager.list_notes.return_value = []
        mock_manager.delete.return_value = True

        monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
        monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
        app.dependency_overrides[get_session_repo] = lambda: session_repo
        app.dependency_overrides[get_note_manager] = lambda: mock_manager
        try:
            client = TestClient(app)
            resp = client.post(
                f"/api/sessions/{session_id}/notes",
                json={"selected_text": "test text", "source_role": "user"},
            )
            assert resp.status_code == 201
            mock_manager.create.assert_called_once_with(
                session_id=session_id,
                selected_text="test text",
                source_role="user",
                note="",
            )
        finally:
            app.dependency_overrides.pop(get_session_repo, None)
            app.dependency_overrides.pop(get_note_manager, None)


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}/notes
# ---------------------------------------------------------------------------

class TestListNotesEndpoint:
    def test_returns_empty_list_when_no_notes(self, client: TestClient, session_id: str) -> None:
        resp = client.get(f"/api/sessions/{session_id}/notes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_created_notes(self, client: TestClient, session_id: str) -> None:
        client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "first", "source_role": "user"},
        )
        client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "second", "source_role": "assistant"},
        )

        resp = client.get(f"/api/sessions/{session_id}/notes")
        assert resp.status_code == 200
        notes = resp.json()
        assert len(notes) == 2
        assert notes[0]["selected_text"] == "first"
        assert notes[1]["selected_text"] == "second"

    def test_notes_scoped_to_session(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed_session(session_repo, "sess-A")
        _seed_session(session_repo, "sess-B")
        client.post(
            "/api/sessions/sess-A/notes",
            json={"selected_text": "only for A", "source_role": "user"},
        )

        resp = client.get("/api/sessions/sess-B/notes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_response_schema_is_valid(self, client: TestClient, session_id: str) -> None:
        client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "schema check", "source_role": "assistant", "note": "yes"},
        )
        note = client.get(f"/api/sessions/{session_id}/notes").json()[0]
        for field in ("id", "session_id", "selected_text", "note", "source_role", "created_at"):
            assert field in note, f"Missing field in response: {field}"

    def test_returns_200_for_unknown_session_with_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/sessions/ghost-session/notes")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{session_id}/notes/{note_id}
# ---------------------------------------------------------------------------

class TestDeleteNoteEndpoint:
    def test_returns_204_on_success(self, client: TestClient, session_id: str) -> None:
        created = client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "delete me", "source_role": "user"},
        ).json()

        resp = client.delete(f"/api/sessions/{session_id}/notes/{created['id']}")
        assert resp.status_code == 204

    def test_note_is_removed_after_delete(self, client: TestClient, session_id: str) -> None:
        created = client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "gone soon", "source_role": "user"},
        ).json()

        client.delete(f"/api/sessions/{session_id}/notes/{created['id']}")

        remaining = client.get(f"/api/sessions/{session_id}/notes").json()
        assert remaining == []

    def test_returns_404_for_unknown_note_id(self, client: TestClient, session_id: str) -> None:
        resp = client.delete(f"/api/sessions/{session_id}/notes/no-such-id")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_cross_session_delete_returns_404(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed_session(session_repo, "sess-owner")
        _seed_session(session_repo, "sess-other")
        created = client.post(
            "/api/sessions/sess-owner/notes",
            json={"selected_text": "mine", "source_role": "assistant"},
        ).json()

        resp = client.delete(f"/api/sessions/sess-other/notes/{created['id']}")
        assert resp.status_code == 404

    def test_only_target_note_is_deleted(self, client: TestClient, session_id: str) -> None:
        keep = client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "keep me", "source_role": "user"},
        ).json()
        remove = client.post(
            f"/api/sessions/{session_id}/notes",
            json={"selected_text": "remove me", "source_role": "user"},
        ).json()

        client.delete(f"/api/sessions/{session_id}/notes/{remove['id']}")

        remaining = client.get(f"/api/sessions/{session_id}/notes").json()
        assert len(remaining) == 1
        assert remaining[0]["id"] == keep["id"]