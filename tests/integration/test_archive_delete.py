"""
tests/test_archive_delete.py
============================
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.config as main_module
from src import config as config_module
from src.repositories import SQLiteConnection, SQLiteSessionRepository, SQLiteNoteRepository
from src.main import app
from src.dependencies import get_session_repo, get_note_repo


# ===========================================================================
# Helpers
# ===========================================================================

def _make_conn(tmp_path: Path) -> SQLiteConnection:
    return SQLiteConnection(db_path=str(tmp_path / "test.db"))


def _seed(repo: SQLiteSessionRepository, session_id: str, title: str = "Chat") -> str:
    repo.save_session(
        session_id=session_id,
        title=title,
        api_history_json="[]",
        ui_history_json="[]",
    )
    return session_id


# ===========================================================================
# Section 1 — Repositories
# ===========================================================================

class TestArchiveSession:
    def test_returns_true_when_archived(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        assert repo.archive_session("s1") is True

    def test_archived_at_is_set(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        repo.archive_session("s1")

        rows = repo.list_sessions(include_archived=True)
        row = next(r for r in rows if r["id"] == "s1")
        assert row["archived_at"] is not None

    def test_returns_false_for_nonexistent_session(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        assert repo.archive_session("ghost") is False

    def test_returns_false_when_already_archived(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        repo.archive_session("s1")
        assert repo.archive_session("s1") is False

    def test_archived_session_disappears_from_default_list(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        _seed(repo, "s2")
        repo.archive_session("s1")

        ids = [r["id"] for r in repo.list_sessions()]
        assert "s1" not in ids
        assert "s2" in ids

    def test_archive_does_not_delete_data(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1", title="Important Chat")
        repo.archive_session("s1")

        rows = repo.list_sessions(include_archived=True)
        row = next(r for r in rows if r["id"] == "s1")
        assert row["title"] == "Important Chat"

    def test_archive_does_not_affect_sibling(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        _seed(repo, "s2")
        repo.archive_session("s1")

        rows = repo.list_sessions(include_archived=True)
        s2 = next(r for r in rows if r["id"] == "s2")
        assert s2["archived_at"] is None


class TestUnarchiveSession:
    def test_returns_true_when_unarchived(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        repo.archive_session("s1")
        assert repo.unarchive_session("s1") is True

    def test_archived_at_cleared_after_unarchive(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        repo.archive_session("s1")
        repo.unarchive_session("s1")

        rows = repo.list_sessions(include_archived=True)
        row = next(r for r in rows if r["id"] == "s1")
        assert row["archived_at"] is None

    def test_unarchived_session_reappears_in_default_list(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        repo.archive_session("s1")
        repo.unarchive_session("s1")

        ids = [r["id"] for r in repo.list_sessions()]
        assert "s1" in ids

    def test_returns_false_for_nonexistent_session(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        assert repo.unarchive_session("ghost") is False

    def test_returns_false_when_not_archived(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        assert repo.unarchive_session("s1") is False


class TestListSessionsFilter:
    def test_default_hides_archived(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "live")
        _seed(repo, "archived")
        repo.archive_session("archived")

        ids = [r["id"] for r in repo.list_sessions()]
        assert "live" in ids
        assert "archived" not in ids

    def test_include_archived_true_shows_all(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "live")
        _seed(repo, "archived")
        repo.archive_session("archived")

        ids = [r["id"] for r in repo.list_sessions(include_archived=True)]
        assert "live" in ids
        assert "archived" in ids

    def test_archived_at_field_present_in_rows(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        row = repo.list_sessions()[0]
        assert "archived_at" in row
        assert row["archived_at"] is None


class TestGetSessionTreeFilter:
    def test_tree_includes_archived_by_default(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_id = repo.fork_session("root-1", turn_index=0)
        repo.archive_session(child_id)

        tree = repo.get_session_tree()
        root = tree[0]
        child_ids = [c["id"] for c in root["children"]]
        assert child_id in child_ids

    def test_tree_excludes_archived_when_requested(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_id = repo.fork_session("root-1", turn_index=0)
        repo.archive_session(child_id)

        tree = repo.get_session_tree(include_archived=False)
        root = tree[0]
        child_ids = [c["id"] for c in root["children"]]
        assert child_id not in child_ids

    def test_archived_node_carries_archived_at(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_id = repo.fork_session("root-1", turn_index=0)
        repo.archive_session(child_id)

        tree = repo.get_session_tree(include_archived=True)
        child_node = tree[0]["children"][0]
        assert child_node["archived_at"] is not None


class TestDeleteSession:
    def test_deletes_leaf_session(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        repo.delete_session("s1")
        assert repo.list_sessions(include_archived=True) == []

    def test_raises_for_nonexistent_session(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        with pytest.raises(ValueError, match="not found"):
            repo.delete_session("ghost")

    def test_raises_when_session_has_children(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "parent")
        repo.fork_session("parent", turn_index=0)

        with pytest.raises(ValueError, match="child session"):
            repo.delete_session("parent")

    def test_parent_deletable_after_child_deleted(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "parent")
        child_id = repo.fork_session("parent", turn_index=0)

        repo.delete_session(child_id)
        repo.delete_session("parent")

        assert repo.list_sessions(include_archived=True) == []

    def test_grandchild_blocks_intermediate_delete(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root")
        child_id = repo.fork_session("root", turn_index=0)
        repo.fork_session(child_id, turn_index=0)

        with pytest.raises(ValueError, match="child session"):
            repo.delete_session(child_id)

    def test_notes_cascade_deleted(self, tmp_path: Path) -> None:
        conn = _make_conn(tmp_path)
        session_repo = SQLiteSessionRepository(conn)
        note_repo = SQLiteNoteRepository(conn)

        _seed(session_repo, "s1")
        note_repo.add_note("s1", "important note", "assistant")
        assert len(note_repo.list_notes("s1")) == 1

        session_repo.delete_session("s1")

        assert note_repo.list_notes("s1") == []

    def test_archived_child_still_blocks_parent_delete(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "parent")
        child_id = repo.fork_session("parent", turn_index=0)
        repo.archive_session(child_id)

        with pytest.raises(ValueError, match="child session"):
            repo.delete_session("parent")

    def test_sibling_unaffected_by_leaf_delete(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root")
        child_a = repo.fork_session("root", turn_index=0)
        child_b = repo.fork_session("root", turn_index=1)

        repo.delete_session(child_a)

        ids = [r["id"] for r in repo.list_sessions(include_archived=True)]
        assert child_b in ids
        assert "root" in ids
        assert child_a not in ids


# ===========================================================================
# Section 2 — FastAPI endpoints
# ===========================================================================

@pytest.fixture
def conn(tmp_path: Path) -> SQLiteConnection:
    return _make_conn(tmp_path)

@pytest.fixture
def session_repo(conn: SQLiteConnection) -> SQLiteSessionRepository:
    return SQLiteSessionRepository(conn)

@pytest.fixture
def client(session_repo: SQLiteSessionRepository, tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    app.dependency_overrides[get_session_repo] = lambda: session_repo
    yield TestClient(app)
    app.dependency_overrides.pop(get_session_repo, None)


@pytest.fixture
def session_id(session_repo: SQLiteSessionRepository) -> str:
    return _seed(session_repo, "sess-1")


class TestArchiveEndpoint:
    def test_returns_200_on_success(self, client: TestClient, session_id: str) -> None:
        resp = client.patch(f"/api/sessions/{session_id}/archive")
        assert resp.status_code == 200
        body = resp.json()
        assert body["archived"] is True
        assert body["session_id"] == session_id

    def test_session_hidden_from_default_list_after_archive(self, client: TestClient, session_id: str) -> None:
        client.patch(f"/api/sessions/{session_id}/archive")
        resp = client.get("/api/sessions")
        ids = [s["id"] for s in resp.json()]
        assert session_id not in ids

    def test_returns_404_for_unknown_session(self, client: TestClient) -> None:
        resp = client.patch("/api/sessions/ghost/archive")
        assert resp.status_code == 404

    def test_returns_404_when_already_archived(self, client: TestClient, session_id: str) -> None:
        client.patch(f"/api/sessions/{session_id}/archive")
        resp = client.patch(f"/api/sessions/{session_id}/archive")
        assert resp.status_code == 404

    def test_archived_at_appears_in_include_archived_list(self, client: TestClient, session_id: str) -> None:
        client.patch(f"/api/sessions/{session_id}/archive")
        resp = client.get("/api/sessions?include_archived=true")
        rows = {r["id"]: r for r in resp.json()}
        assert rows[session_id]["archived_at"] is not None


class TestUnarchiveEndpoint:
    def test_returns_200_on_success(self, client: TestClient, session_id: str) -> None:
        client.patch(f"/api/sessions/{session_id}/archive")
        resp = client.delete(f"/api/sessions/{session_id}/archive")
        assert resp.status_code == 200
        body = resp.json()
        assert body["archived"] is False
        assert body["session_id"] == session_id

    def test_session_reappears_in_default_list_after_unarchive(self, client: TestClient, session_id: str) -> None:
        client.patch(f"/api/sessions/{session_id}/archive")
        client.delete(f"/api/sessions/{session_id}/archive")
        resp = client.get("/api/sessions")
        ids = [s["id"] for s in resp.json()]
        assert session_id in ids

    def test_returns_404_for_unknown_session(self, client: TestClient) -> None:
        resp = client.delete("/api/sessions/ghost/archive")
        assert resp.status_code == 404

    def test_returns_404_when_not_archived(self, client: TestClient, session_id: str) -> None:
        resp = client.delete(f"/api/sessions/{session_id}/archive")
        assert resp.status_code == 404


class TestDeleteSessionEndpoint:
    def test_returns_204_for_leaf_session(self, client: TestClient, session_id: str) -> None:
        resp = client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 204

    def test_session_gone_after_delete(self, client: TestClient, session_id: str) -> None:
        client.delete(f"/api/sessions/{session_id}")
        resp = client.get("/api/sessions?include_archived=true")
        ids = [s["id"] for s in resp.json()]
        assert session_id not in ids

    def test_returns_404_for_unknown_session(self, client: TestClient) -> None:
        resp = client.delete("/api/sessions/ghost")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_returns_409_when_children_exist(self, client: TestClient, session_repo: SQLiteSessionRepository, session_id: str) -> None:
        session_repo.fork_session(session_id, turn_index=0)
        resp = client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 409
        assert "child" in resp.json()["detail"].lower()

    def test_allowed_after_child_deleted(self, client: TestClient, session_repo: SQLiteSessionRepository, session_id: str) -> None:
        child_id = session_repo.fork_session(session_id, turn_index=0)
        client.delete(f"/api/sessions/{child_id}")
        resp = client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 204

    def test_archived_child_blocks_parent_delete(self, client: TestClient, session_repo: SQLiteSessionRepository, session_id: str) -> None:
        child_id = session_repo.fork_session(session_id, turn_index=0)
        client.patch(f"/api/sessions/{child_id}/archive")
        resp = client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 409


class TestListSessionsQueryParam:
    def test_default_excludes_archived(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "live")
        _seed(session_repo, "hidden")
        session_repo.archive_session("hidden")

        resp = client.get("/api/sessions")
        ids = [s["id"] for s in resp.json()]
        assert "live" in ids
        assert "hidden" not in ids

    def test_include_archived_false_explicit(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "live")
        _seed(session_repo, "hidden")
        session_repo.archive_session("hidden")

        resp = client.get("/api/sessions?include_archived=false")
        ids = [s["id"] for s in resp.json()]
        assert "hidden" not in ids

    def test_include_archived_true_shows_all(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "live")
        _seed(session_repo, "hidden")
        session_repo.archive_session("hidden")

        resp = client.get("/api/sessions?include_archived=true")
        ids = [s["id"] for s in resp.json()]
        assert "live" in ids
        assert "hidden" in ids

    def test_archived_at_field_in_response(self, client: TestClient, session_id: str) -> None:
        resp = client.get("/api/sessions")
        item = resp.json()[0]
        assert "archived_at" in item
        assert item["archived_at"] is None


class TestTreeQueryParam:
    def test_tree_includes_archived_by_default(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "root-1")
        child_id = session_repo.fork_session("root-1", turn_index=0)
        session_repo.archive_session(child_id)

        tree = client.get("/api/sessions/tree").json()
        child_ids = [c["id"] for c in tree[0]["children"]]
        assert child_id in child_ids

    def test_tree_excludes_archived_when_false(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "root-1")
        child_id = session_repo.fork_session("root-1", turn_index=0)
        session_repo.archive_session(child_id)

        tree = client.get("/api/sessions/tree?include_archived=false").json()
        child_ids = [c["id"] for c in tree[0]["children"]]
        assert child_id not in child_ids

    def test_archived_node_has_archived_at_set(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "root-1")
        child_id = session_repo.fork_session("root-1", turn_index=0)
        session_repo.archive_session(child_id)

        tree = client.get("/api/sessions/tree").json()
        child_node = tree[0]["children"][0]
        assert child_node["archived_at"] is not None