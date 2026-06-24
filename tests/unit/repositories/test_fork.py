"""
tests/test_fork.py
==================
"""
import json
import pytest

from src.repositories import SQLiteConnection, SQLiteSessionRepository


def _seed_session(repo: SQLiteSessionRepository) -> tuple[str, list, list]:
    session_id = "src-session-1"
    ui_messages = [
        {"role": "user", "content": "Turn 0 user"},
        {"role": "assistant", "content": "Turn 1 assistant", "tools": []},
        {"role": "user", "content": "Turn 2 user"},
        {"role": "assistant", "content": "Turn 3 assistant", "tools": []},
    ]
    api_history = [
        {"role": "user", "parts": [{"text": "Turn 0 user"}]},
        {"role": "model", "parts": [{"text": "Turn 1 assistant"}]},
        {"role": "user", "parts": [{"text": "Turn 2 user"}]},
        {"role": "model", "parts": [{"text": "Turn 3 assistant"}]},
    ]
    repo.save_session(
        session_id=session_id,
        title="Original Title",
        api_history_json=json.dumps(api_history),
        ui_history_json=json.dumps(ui_messages),
    )
    return session_id, ui_messages, api_history


def test_fork_returns_new_unique_session_id(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    source_id, _, _ = _seed_session(repo)

    new_id = repo.fork_session(source_id, turn_index=1)

    assert new_id != source_id
    assert isinstance(new_id, str) and len(new_id) > 0


def test_fork_slices_ui_history_inclusive(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    source_id, ui_messages, _ = _seed_session(repo)

    new_id = repo.fork_session(source_id, turn_index=1)

    _, new_ui_json, _ = repo.load_session(new_id)
    assert json.loads(new_ui_json) == ui_messages[:2]


def test_fork_slices_api_history_inclusive(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    source_id, _, api_history = _seed_session(repo)

    new_id = repo.fork_session(source_id, turn_index=2)

    new_api_json, _, _ = repo.load_session(new_id)
    assert json.loads(new_api_json) == api_history[:3]


def test_fork_does_not_modify_source_session(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    source_id, ui_messages, api_history = _seed_session(repo)

    repo.fork_session(source_id, turn_index=1)

    src_api_json, src_ui_json, _ = repo.load_session(source_id)
    assert json.loads(src_ui_json) == ui_messages
    assert json.loads(src_api_json) == api_history


def test_fork_derives_title_from_source(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    source_id, _, _ = _seed_session(repo)

    new_id = repo.fork_session(source_id, turn_index=1)

    sessions = {s["id"]: s for s in repo.list_sessions()}
    assert new_id in sessions
    forked_title = sessions[new_id]["title"]
    assert "Original Title" in forked_title
    assert "fork" in forked_title.lower()


def test_fork_at_index_zero_keeps_first_turn_only(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    source_id, ui_messages, _ = _seed_session(repo)

    new_id = repo.fork_session(source_id, turn_index=0)

    _, new_ui_json, _ = repo.load_session(new_id)
    assert json.loads(new_ui_json) == ui_messages[:1]


def test_fork_index_beyond_history_is_clamped(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    source_id, ui_messages, api_history = _seed_session(repo)

    new_id = repo.fork_session(source_id, turn_index=999)

    new_api_json, new_ui_json, _ = repo.load_session(new_id)
    assert json.loads(new_ui_json) == ui_messages
    assert json.loads(new_api_json) == api_history


def test_fork_nonexistent_session_raises(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)

    with pytest.raises(ValueError):
        repo.fork_session("does-not-exist", turn_index=0)


def test_fork_negative_index_raises(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    source_id, _, _ = _seed_session(repo)

    with pytest.raises(ValueError):
        repo.fork_session(source_id, turn_index=-1)


def test_forked_session_appears_in_list(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test_chats.db"))
    repo = SQLiteSessionRepository(conn)
    source_id, _, _ = _seed_session(repo)

    new_id = repo.fork_session(source_id, turn_index=1)

    session_ids = [s["id"] for s in repo.list_sessions()]
    assert new_id in session_ids
    assert source_id in session_ids
