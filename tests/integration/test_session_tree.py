"""
tests/test_session_tree.py
==========================
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.config as main_module
from src import config as config_module
from src.main import app
from src.dependencies import get_session_repo
from src.repositories import SQLiteConnection, SQLiteSessionRepository


# ===========================================================================
# Helpers
# ===========================================================================

def _make_conn(tmp_path: Path) -> SQLiteConnection:
    return SQLiteConnection(db_path=str(tmp_path / "test.db"))


def _seed(repo: SQLiteSessionRepository, session_id: str, title: str = "Root") -> str:
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

class TestLineageColumns:
    def test_root_session_has_null_lineage(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")

        rows = repo.list_sessions()
        assert len(rows) == 1
        row = rows[0]
        assert row["parent_id"] is None
        assert row["fork_turn_index"] is None

    def test_root_session_root_id_is_none_before_fork(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")

        rows = repo.list_sessions()
        assert rows[0]["root_id"] is None

    def test_list_sessions_exposes_lineage_fields(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "s1")
        row = repo.list_sessions()[0]
        for field in ("parent_id", "fork_turn_index", "root_id"):
            assert field in row, f"Missing field: {field}"

    def test_upsert_does_not_overwrite_lineage(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "parent-1")
        child_id = repo.fork_session("parent-1", turn_index=0)

        repo.save_session(
            session_id=child_id,
            title="Updated title",
            api_history_json="[]",
            ui_history_json="[]",
        )

        rows = {r["id"]: r for r in repo.list_sessions()}
        assert rows[child_id]["parent_id"] == "parent-1"
        assert rows[child_id]["fork_turn_index"] == 0



class TestForkLineage:
    def test_fork_sets_parent_id(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "parent-1")
        child_id = repo.fork_session("parent-1", turn_index=2)

        rows = {r["id"]: r for r in repo.list_sessions()}
        assert rows[child_id]["parent_id"] == "parent-1"

    def test_fork_sets_fork_turn_index(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "parent-1")
        child_id = repo.fork_session("parent-1", turn_index=3)

        rows = {r["id"]: r for r in repo.list_sessions()}
        assert rows[child_id]["fork_turn_index"] == 3

    def test_first_fork_root_id_equals_parent(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_id = repo.fork_session("root-1", turn_index=0)

        rows = {r["id"]: r for r in repo.list_sessions()}
        assert rows[child_id]["root_id"] == "root-1"

    def test_grandchild_inherits_root_id(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_id = repo.fork_session("root-1", turn_index=0)
        grandchild_id = repo.fork_session(child_id, turn_index=0)

        rows = {r["id"]: r for r in repo.list_sessions()}
        assert rows[grandchild_id]["root_id"] == "root-1"

    def test_sibling_forks_share_root_id(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_a = repo.fork_session("root-1", turn_index=0)
        child_b = repo.fork_session("root-1", turn_index=1)

        rows = {r["id"]: r for r in repo.list_sessions()}
        assert rows[child_a]["root_id"] == "root-1"
        assert rows[child_b]["root_id"] == "root-1"

    def test_independent_trees_have_different_roots(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "tree-A")
        _seed(repo, "tree-B")
        child_a = repo.fork_session("tree-A", turn_index=0)
        child_b = repo.fork_session("tree-B", turn_index=0)

        rows = {r["id"]: r for r in repo.list_sessions()}
        assert rows[child_a]["root_id"] == "tree-A"
        assert rows[child_b]["root_id"] == "tree-B"
        assert rows[child_a]["root_id"] != rows[child_b]["root_id"]

    def test_parent_lineage_unchanged_after_fork(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "parent-1")
        repo.fork_session("parent-1", turn_index=0)

        rows = {r["id"]: r for r in repo.list_sessions()}
        assert rows["parent-1"]["parent_id"] is None
        assert rows["parent-1"]["fork_turn_index"] is None


class TestGetSessionTreeRepository:
    def test_empty_db_returns_empty_list(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        assert repo.get_session_tree() == []

    def test_single_root_no_children(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1", "My Chat")
        tree = repo.get_session_tree()

        assert len(tree) == 1
        assert tree[0]["id"] == "root-1"
        assert tree[0]["children"] == []

    def test_fork_appears_as_child_not_root(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_id = repo.fork_session("root-1", turn_index=1)

        tree = repo.get_session_tree()

        assert len(tree) == 1
        assert tree[0]["id"] == "root-1"

        children = tree[0]["children"]
        assert len(children) == 1
        assert children[0]["id"] == child_id

    def test_multiple_forks_all_appear_as_children(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_a = repo.fork_session("root-1", turn_index=0)
        child_b = repo.fork_session("root-1", turn_index=1)

        tree = repo.get_session_tree()
        assert len(tree) == 1

        child_ids = {c["id"] for c in tree[0]["children"]}
        assert child_a in child_ids
        assert child_b in child_ids

    def test_grandchild_nested_correctly(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_id = repo.fork_session("root-1", turn_index=0)
        grandchild_id = repo.fork_session(child_id, turn_index=0)

        tree = repo.get_session_tree()
        assert len(tree) == 1

        child_node = tree[0]["children"][0]
        assert child_node["id"] == child_id
        assert len(child_node["children"]) == 1
        assert child_node["children"][0]["id"] == grandchild_id

    def test_independent_trees_produce_multiple_roots(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "tree-A")
        _seed(repo, "tree-B")
        repo.fork_session("tree-A", turn_index=0)

        tree = repo.get_session_tree()
        root_ids = {node["id"] for node in tree}

        assert "tree-A" in root_ids
        assert "tree-B" in root_ids
        tree_b_node = next(n for n in tree if n["id"] == "tree-B")
        assert tree_b_node["children"] == []

    def test_node_contains_lineage_fields(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        child_id = repo.fork_session("root-1", turn_index=2)

        tree = repo.get_session_tree()
        child_node = tree[0]["children"][0]

        assert child_node["parent_id"] == "root-1"
        assert child_node["fork_turn_index"] == 2
        assert child_node["root_id"] == "root-1"
        assert child_node["id"] == child_id

    def test_node_contains_children_key(self, tmp_path: Path) -> None:
        repo = SQLiteSessionRepository(_make_conn(tmp_path))
        _seed(repo, "root-1")
        tree = repo.get_session_tree()
        assert "children" in tree[0]


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


class TestGetSessionsFlat:
    def test_returns_lineage_fields(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "s1")
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        item = resp.json()[0]
        assert "parent_id" in item
        assert "fork_turn_index" in item
        assert "root_id" in item

    def test_root_session_has_null_lineage(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "s1")
        resp = client.get("/api/sessions")
        item = resp.json()[0]
        assert item["parent_id"] is None
        assert item["fork_turn_index"] is None
        assert item["root_id"] is None

    def test_forked_session_has_lineage_populated(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "root-1")
        child_id = session_repo.fork_session("root-1", turn_index=3)

        resp = client.get("/api/sessions")
        rows = {r["id"]: r for r in resp.json()}
        assert rows[child_id]["parent_id"] == "root-1"
        assert rows[child_id]["fork_turn_index"] == 3
        assert rows[child_id]["root_id"] == "root-1"


class TestGetSessionTree:
    def test_empty_returns_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/sessions/tree")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_single_root_in_tree(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "root-1", "My chat")
        resp = client.get("/api/sessions/tree")
        assert resp.status_code == 200
        tree = resp.json()
        assert len(tree) == 1
        assert tree[0]["id"] == "root-1"
        assert tree[0]["children"] == []

    def test_fork_is_child_not_root(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "root-1")
        child_id = session_repo.fork_session("root-1", turn_index=1)

        resp = client.get("/api/sessions/tree")
        tree = resp.json()
        assert len(tree) == 1
        assert tree[0]["id"] == "root-1"
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["id"] == child_id

    def test_grandchild_nested(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "root-1")
        child_id = session_repo.fork_session("root-1", turn_index=0)
        grandchild_id = session_repo.fork_session(child_id, turn_index=0)

        resp = client.get("/api/sessions/tree")
        tree = resp.json()

        child_node = tree[0]["children"][0]
        assert child_node["id"] == child_id
        assert child_node["children"][0]["id"] == grandchild_id

    def test_node_schema_has_all_fields(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "root-1")
        child_id = session_repo.fork_session("root-1", turn_index=2)

        tree = client.get("/api/sessions/tree").json()
        child_node = tree[0]["children"][0]

        for field in ("id", "title", "updated_at", "parent_id", "fork_turn_index", "root_id", "children"):
            assert field in child_node, f"Missing field: {field}"

        assert child_node["parent_id"] == "root-1"
        assert child_node["fork_turn_index"] == 2

    def test_multiple_independent_trees(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        _seed(session_repo, "tree-A")
        _seed(session_repo, "tree-B")

        resp = client.get("/api/sessions/tree")
        root_ids = {n["id"] for n in resp.json()}
        assert "tree-A" in root_ids
        assert "tree-B" in root_ids

    def test_tree_endpoint_distinct_from_session_id_route(self, client: TestClient, session_repo: SQLiteSessionRepository) -> None:
        resp = client.get("/api/sessions/tree")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)