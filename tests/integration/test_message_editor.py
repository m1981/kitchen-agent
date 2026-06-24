"""
tests/test_message_editor.py
============================
TDD tests for the message editing / deleting feature.

Refactor — Decision 1: turn_id identity
-----------------------------------------
All edit and delete operations now use ``turn_id`` (stable UUID) rather than
``ui_index`` (positional integer).  The fixture data is updated to include
``turn_id`` on every ui_message and api item.

Test groups
-----------
1.  MessageEditService unit tests (pure business logic, no HTTP)
2.  HTTP endpoint integration tests via TestClient

Scenarios covered
-----------------
A. Edit a user message content  (by turn_id)
B. Delete a single message      (by turn_id, with optional pair)
C. Delete last N turns          (truncate — tail-based)
D. Update the session-scoped system prompt override
E. Validation: unknown turn_id, empty content, etc.
"""

import json
import pytest
from fastapi.testclient import TestClient

from src.repositories import SQLiteConnection, SQLiteSessionRepository
from src.message_editor import MessageEditService, EditError
from src.main import app
from src.dependencies import get_session_repo


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return SQLiteConnection(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def repo(db):
    return SQLiteSessionRepository(db)


# Stable UUIDs used across fixtures and tests for predictability.
U0 = "aaaaaaaa-0000-0000-0000-000000000000"  # user turn 0
A0 = "aaaaaaaa-0000-0000-0000-000000000001"  # assistant turn 0
U1 = "aaaaaaaa-0000-0000-0000-000000000002"  # user turn 1
A1 = "aaaaaaaa-0000-0000-0000-000000000003"  # assistant turn 1
U2 = "aaaaaaaa-0000-0000-0000-000000000004"  # user turn 2
A2 = "aaaaaaaa-0000-0000-0000-000000000005"  # assistant turn 2


@pytest.fixture
def populated_repo(repo):
    """
    A repo with one session that has 3 complete turns.

    Both ui_history and api_history carry turn_ids stamped at write time,
    exactly as chat_service.py now produces them.

    ui_history (6 items, 3 pairs):
      [U0] user:      "Turn 0 user"
      [A0] assistant: "Turn 0 assistant"   (no tools)
      [U1] user:      "Turn 1 user"
      [A1] assistant: "Turn 1 assistant"   (no tools)
      [U2] user:      "Turn 2 user"
      [A2] assistant: "Turn 2 assistant"   (no tools)

    api_history (6 items, each stamped with its turn_id):
      {user/text/Turn 0 user,       turn_id=U0}
      {model/text/Turn 0 assistant, turn_id=A0}
      {user/text/Turn 1 user,       turn_id=U1}
      {model/text/Turn 1 assistant, turn_id=A1}
      {user/text/Turn 2 user,       turn_id=U2}
      {model/text/Turn 2 assistant, turn_id=A2}
    """
    ui = [
        {"role": "user",      "content": "Turn 0 user",      "turn_id": U0},
        {"role": "assistant", "content": "Turn 0 assistant",  "turn_id": A0, "tools": []},
        {"role": "user",      "content": "Turn 1 user",      "turn_id": U1},
        {"role": "assistant", "content": "Turn 1 assistant",  "turn_id": A1, "tools": []},
        {"role": "user",      "content": "Turn 2 user",      "turn_id": U2},
        {"role": "assistant", "content": "Turn 2 assistant",  "turn_id": A2, "tools": []},
    ]
    api = [
        {"role": "user",  "type": "text", "data": "Turn 0 user",      "turn_id": U0},
        {"role": "model", "type": "text", "data": "Turn 0 assistant",  "turn_id": A0},
        {"role": "user",  "type": "text", "data": "Turn 1 user",      "turn_id": U1},
        {"role": "model", "type": "text", "data": "Turn 1 assistant",  "turn_id": A1},
        {"role": "user",  "type": "text", "data": "Turn 2 user",      "turn_id": U2},
        {"role": "model", "type": "text", "data": "Turn 2 assistant",  "turn_id": A2},
    ]
    repo.save_session(
        session_id="sess-edit",
        title="Edit test session",
        api_history_json=json.dumps(api),
        ui_history_json=json.dumps(ui),
        system_prompt="Original system prompt",
    )
    return repo


@pytest.fixture
def service(populated_repo):
    return MessageEditService(populated_repo)


# ===========================================================================
# 1. MessageEditService — edit message by turn_id
# ===========================================================================

class TestEditUserMessage:
    def test_edit_user_message_updates_ui_content(self, service, populated_repo):
        """Editing by turn_id updates the matching ui_message content."""
        service.edit_message(session_id="sess-edit", turn_id=U0, new_content="EDITED")
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        assert ui[0]["content"] == "EDITED"

    def test_edit_user_message_updates_api_content(self, service, populated_repo):
        """Editing by turn_id also syncs the api_history text data."""
        service.edit_message(session_id="sess-edit", turn_id=U1, new_content="Turn 1 EDITED")
        api_json, _, _ = populated_repo.load_session("sess-edit")
        api = json.loads(api_json)
        edited = next(i for i in api if i.get("turn_id") == U1)
        assert edited["data"] == "Turn 1 EDITED"

    def test_edit_preserves_other_messages(self, service, populated_repo):
        """Only the targeted message is modified; others stay intact."""
        service.edit_message("sess-edit", U0, "ONLY THIS")
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        assert ui[1]["content"] == "Turn 0 assistant"
        assert ui[2]["content"] == "Turn 1 user"

    def test_edit_assistant_message(self, service, populated_repo):
        """Assistant messages can also be edited."""
        service.edit_message("sess-edit", A0, "Assistant EDITED")
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        edited = next(m for m in ui if m["turn_id"] == A0)
        assert edited["content"] == "Assistant EDITED"

    def test_edit_api_item_for_assistant_turn(self, service, populated_repo):
        """Editing an assistant turn also updates its api_history text item."""
        service.edit_message("sess-edit", A1, "New assistant text")
        api_json, _, _ = populated_repo.load_session("sess-edit")
        api = json.loads(api_json)
        edited = next(i for i in api if i.get("turn_id") == A1 and i["type"] == "text")
        assert edited["data"] == "New assistant text"

    def test_edit_nonexistent_session_raises(self, service):
        with pytest.raises(EditError, match="not found"):
            service.edit_message("no-such-session", U0, "x")

    def test_edit_unknown_turn_id_raises(self, service):
        with pytest.raises(EditError, match="turn_id"):
            service.edit_message("sess-edit", "turn-does-not-exist", "x")

    def test_edit_empty_content_raises(self, service):
        with pytest.raises(EditError, match="content"):
            service.edit_message("sess-edit", U0, "   ")


# ===========================================================================
# 2. MessageEditService — delete message by turn_id
# ===========================================================================

class TestDeleteMessage:
    def test_delete_removes_message_from_ui(self, service, populated_repo):
        """Deleting by turn_id removes the matching ui_message."""
        service.delete_message("sess-edit", turn_id=U2)
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        assert len(ui) == 5
        assert not any(m.get("turn_id") == U2 for m in ui)

    def test_delete_with_pair_removes_both(self, service, populated_repo):
        """delete_pair=True removes the targeted message and the next one."""
        service.delete_message("sess-edit", turn_id=U2, delete_pair=True)
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        assert len(ui) == 4
        assert not any(m.get("turn_id") in {U2, A2} for m in ui)

    def test_delete_assistant_message_standalone(self, service, populated_repo):
        """Can delete an assistant message standalone."""
        service.delete_message("sess-edit", turn_id=A0)
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        assert len(ui) == 5
        assert not any(m.get("turn_id") == A0 for m in ui)

    def test_delete_syncs_api_history(self, service, populated_repo):
        """Deleting removes all api items sharing the same turn_id."""
        service.delete_message("sess-edit", turn_id=U0, delete_pair=True)
        api_json, _, _ = populated_repo.load_session("sess-edit")
        api = json.loads(api_json)
        assert len(api) == 4
        assert not any(i.get("turn_id") in {U0, A0} for i in api)

    def test_delete_only_removes_matching_turn_id_from_api(self, service, populated_repo):
        """api items with different turn_ids are untouched."""
        service.delete_message("sess-edit", turn_id=U1)
        api_json, _, _ = populated_repo.load_session("sess-edit")
        api = json.loads(api_json)
        remaining_ids = {i.get("turn_id") for i in api}
        assert U0 in remaining_ids
        assert A0 in remaining_ids
        assert U1 not in remaining_ids
        assert A1 in remaining_ids  # pair NOT removed

    def test_delete_unknown_turn_id_raises(self, service):
        with pytest.raises(EditError, match="turn_id"):
            service.delete_message("sess-edit", turn_id="unknown-id")

    def test_delete_nonexistent_session_raises(self, service):
        with pytest.raises(EditError, match="not found"):
            service.delete_message("no-such", turn_id=U0)


# ===========================================================================
# 3. MessageEditService — truncate (tail-based, no turn_id needed)
# ===========================================================================

class TestTruncateTurns:
    def test_truncate_removes_last_turn_pair(self, service, populated_repo):
        """truncate_turns(n=1) removes the last user+assistant pair."""
        service.truncate_turns("sess-edit", n=1)
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        assert len(ui) == 4
        assert not any(m.get("turn_id") in {U2, A2} for m in ui)

    def test_truncate_removes_multiple_pairs(self, service, populated_repo):
        """truncate_turns(n=2) removes last 2 user+assistant pairs."""
        service.truncate_turns("sess-edit", n=2)
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        assert len(ui) == 2
        assert ui[0]["turn_id"] == U0
        assert ui[1]["turn_id"] == A0

    def test_truncate_syncs_api_history_via_turn_ids(self, service, populated_repo):
        """Truncating removes the correct api items using turn_id filtering."""
        service.truncate_turns("sess-edit", n=2)
        api_json, _, _ = populated_repo.load_session("sess-edit")
        api = json.loads(api_json)
        assert len(api) == 2
        remaining = {i["turn_id"] for i in api}
        assert remaining == {U0, A0}

    def test_truncate_zero_raises(self, service):
        with pytest.raises(EditError, match="n must be"):
            service.truncate_turns("sess-edit", n=0)

    def test_truncate_exceeds_history_raises(self, service):
        with pytest.raises(EditError, match="exceeds"):
            service.truncate_turns("sess-edit", n=10)

    def test_truncate_nonexistent_session_raises(self, service):
        with pytest.raises(EditError, match="not found"):
            service.truncate_turns("no-such", n=1)


# ===========================================================================
# 4. MessageEditService — system prompt override
# ===========================================================================

class TestUpdateSystemPrompt:
    def test_update_system_prompt_persists(self, service, populated_repo):
        service.update_system_prompt("sess-edit", "Custom prompt override")
        _, _, prompt = populated_repo.load_session("sess-edit")
        assert prompt == "Custom prompt override"

    def test_update_system_prompt_empty_allowed(self, service, populated_repo):
        service.update_system_prompt("sess-edit", "")
        _, _, prompt = populated_repo.load_session("sess-edit")
        assert prompt == ""

    def test_update_system_prompt_on_new_session_creates_row(self, repo):
        """
        Setting a system prompt on a brand-new session (no messages yet)
        must NOT raise 404.  The session row is upserted on the spot.
        This is the fix for the 'new chat + open prompt editor' bug.
        """
        svc = MessageEditService(repo)
        new_id = "brand-new-session-id"
        # No row exists for new_id in the DB yet.
        svc.update_system_prompt(new_id, "Pre-flight prompt")
        _, _, prompt = repo.load_session(new_id)
        assert prompt == "Pre-flight prompt"

    def test_update_system_prompt_nonexistent_no_longer_raises(self, repo):
        """
        update_system_prompt never raises EditError for unknown IDs —
        it upserts instead.  Only edit/delete/truncate require existing rows.
        """
        svc = MessageEditService(repo)
        # Should not raise:
        svc.update_system_prompt("any-unknown-id", "some prompt")

    def test_get_system_prompt_new_session_returns_none(self, repo):
        """
        get_system_prompt on a brand-new session returns None instead of
        raising — matching the GET /system-prompt 200 behaviour.
        """
        svc = MessageEditService(repo)
        result = svc.get_system_prompt("never-seen-before")
        assert result is None


# ===========================================================================
# 5. HTTP endpoint integration tests
# ===========================================================================

@pytest.fixture
def client(populated_repo):
    app.dependency_overrides[get_session_repo] = lambda: populated_repo
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestMessageEditorEndpoints:
    # ── PATCH /api/sessions/{id}/messages/{turn_id} ────────────────────────

    def test_http_edit_message_200(self, client):
        resp = client.patch(
            f"/api/sessions/sess-edit/messages/{U0}",
            json={"new_content": "Edited via HTTP"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] is True
        assert body["turn_id"] == U0

    def test_http_edit_message_updates_content(self, client, populated_repo):
        client.patch(
            f"/api/sessions/sess-edit/messages/{U0}",
            json={"new_content": "HTTP updated content"},
        )
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        updated = next(m for m in ui if m["turn_id"] == U0)
        assert updated["content"] == "HTTP updated content"

    def test_http_edit_message_404_bad_session(self, client):
        resp = client.patch(
            f"/api/sessions/bad-session/messages/{U0}",
            json={"new_content": "x"},
        )
        assert resp.status_code == 404

    def test_http_edit_message_400_empty_content(self, client):
        resp = client.patch(
            f"/api/sessions/sess-edit/messages/{U0}",
            json={"new_content": "   "},
        )
        assert resp.status_code == 400

    def test_http_edit_message_400_unknown_turn_id(self, client):
        resp = client.patch(
            "/api/sessions/sess-edit/messages/turn-does-not-exist",
            json={"new_content": "x"},
        )
        assert resp.status_code == 400

    # ── DELETE /api/sessions/{id}/messages/{turn_id} ───────────────────────

    def test_http_delete_message_200(self, client):
        resp = client.delete(f"/api/sessions/sess-edit/messages/{U0}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"] is True
        assert body["turn_id"] == U0

    def test_http_delete_message_with_pair(self, client, populated_repo):
        resp = client.delete(
            f"/api/sessions/sess-edit/messages/{U2}?delete_pair=true"
        )
        assert resp.status_code == 200
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        assert len(ui) == 4
        assert not any(m.get("turn_id") in {U2, A2} for m in ui)

    def test_http_delete_message_404_bad_session(self, client):
        resp = client.delete(f"/api/sessions/bad-session/messages/{U0}")
        assert resp.status_code == 404

    def test_http_delete_message_400_unknown_turn_id(self, client):
        resp = client.delete("/api/sessions/sess-edit/messages/unknown-id")
        assert resp.status_code == 400

    # ── POST /api/sessions/{id}/messages/truncate ──────────────────────────

    def test_http_truncate_200(self, client):
        resp = client.post(
            "/api/sessions/sess-edit/messages/truncate",
            json={"n": 1},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["truncated"] is True
        assert body["turns_removed"] == 1

    def test_http_truncate_removes_messages(self, client, populated_repo):
        client.post(
            "/api/sessions/sess-edit/messages/truncate",
            json={"n": 2},
        )
        _, ui_json, _ = populated_repo.load_session("sess-edit")
        ui = json.loads(ui_json)
        assert len(ui) == 2

    def test_http_truncate_400_zero_n(self, client):
        resp = client.post(
            "/api/sessions/sess-edit/messages/truncate",
            json={"n": 0},
        )
        assert resp.status_code == 400

    def test_http_truncate_404_bad_session(self, client):
        resp = client.post(
            "/api/sessions/bad-session/messages/truncate",
            json={"n": 1},
        )
        assert resp.status_code == 404

    # ── PATCH /api/sessions/{id}/system-prompt ─────────────────────────────

    def test_http_update_system_prompt_200(self, client):
        resp = client.patch(
            "/api/sessions/sess-edit/system-prompt",
            json={"system_prompt": "New custom prompt"},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_http_update_system_prompt_persists(self, client, populated_repo):
        client.patch(
            "/api/sessions/sess-edit/system-prompt",
            json={"system_prompt": "Persisted override"},
        )
        _, _, prompt = populated_repo.load_session("sess-edit")
        assert prompt == "Persisted override"

    def test_http_update_system_prompt_200_on_new_session(self, client):
        """
        PATCH system-prompt on an unknown (brand-new) session ID must return
        200, not 404.  This is the fix for the 'new chat prompt editor' bug.
        """
        resp = client.patch(
            "/api/sessions/brand-new-id/system-prompt",
            json={"system_prompt": "pre-flight override"},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_http_get_system_prompt_200(self, client):
        resp = client.get("/api/sessions/sess-edit/system-prompt")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "sess-edit"
        assert body["system_prompt"] == "Original system prompt"

    def test_http_get_system_prompt_200_returns_null_for_new_session(self, client):
        """
        GET system-prompt on a brand-new session returns null, not 404.
        """
        resp = client.get("/api/sessions/never-saved/system-prompt")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "never-saved"
        assert body["system_prompt"] is None
