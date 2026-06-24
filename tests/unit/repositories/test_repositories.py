"""
tests/test_repositories.py
==========================
Basic lifecycle tests for the Repository pattern.
"""
import pytest
from src.repositories import SQLiteConnection, SQLiteSessionRepository


def test_database_lifecycle(tmp_path):
    """Tests initializing, saving, loading, and listing chat sessions."""

    # 1. Arrange: Set up a temporary database connection and repository
    db_path = tmp_path / "test_chats.db"
    conn = SQLiteConnection(db_path=str(db_path))
    repo = SQLiteSessionRepository(conn)

    # 2. Act: Save a new session
    session_id = "chat_123"
    fake_json_history = '[{"role": "user", "type": "text", "data": "Hello"}]'
    fake_ui_history = '[{"role": "user", "content": "Hello"}]'

    repo.save_session(
        session_id=session_id,
        title="My First Chat",
        api_history_json=fake_json_history,
        ui_history_json=fake_ui_history
    )

    # 3. Assert: Load the session back — now returns 3-tuple (api, ui, system_prompt)
    loaded_api, loaded_ui, loaded_prompt = repo.load_session(session_id)
    assert loaded_api == fake_json_history
    assert loaded_ui == fake_ui_history
    assert loaded_prompt is None  # not set

    # 4. Assert: List sessions
    sessions = repo.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == "chat_123"
    assert sessions[0]["title"] == "My First Chat"

    # 5. Act: Update the existing session (Upsert)
    updated_json = '[{"role": "user", "type": "text", "data": "Hello Updated"}]'
    repo.save_session(
        session_id=session_id,
        title="My First Chat",
        api_history_json=updated_json,
        ui_history_json=fake_ui_history
    )

    # 6. Assert: Ensure it updated, not duplicated
    loaded_api, _, _ = repo.load_session(session_id)
    assert loaded_api == updated_json
    assert len(repo.list_sessions()) == 1
