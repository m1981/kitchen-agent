"""
tests/test_llm_export.py
========================
TDD suite for the LLM-context debug export feature.

Feature: GET /api/sessions/{session_id}/export/llm
Returns the raw conversation as the LLM actually sees it in its context
window — every Content object, every Part, thought_signature as hex,
function calls and responses intact.

Covers:
 ── Pure function layer (src/exporter.py) ──────────────────────────────────
  [T01]  Empty api_history → empty turns list, metadata present
  [T02]  Simple text turn (user) renders correctly
  [T03]  Simple text turn (model) renders correctly
  [T04]  Multi-turn conversation preserves order
  [T05]  Function-call part renders name, args, id, thought_signature
  [T06]  Function-call with NO thought_signature shows null
  [T07]  Function-response part renders name, response, id
  [T08]  Multi-part Content — ALL parts rendered (not just parts[0])
  [T09]  Unknown/unrecognised part type marked as "unknown_part"
  [T10]  Metadata block contains session_id, title, turn_count, export_ts
  [T11]  turn_count equals len(turns), not len(ui_messages)
  [T12]  Text with unicode / special chars preserved faithfully
  [T13]  thought_signature bytes round-trip cleanly through hex

 ── Repository integration (src/repositories.py) ───────────────────────────
  [T14]  export_session_to_llm_json via repo returns structured dict
  [T15]  Non-existent session raises ValueError

 ── HTTP layer (src/main.py) ───────────────────────────────────────────────
  [T16]  GET /api/sessions/{id}/export/llm → 200 JSON with correct shape
  [T17]  GET /api/sessions/unknown/export/llm → 404
  [T18]  Response Content-Type is application/json
  [T19]  Endpoint is distinct from existing Markdown export endpoint
  [T20]  Full round-trip: save session with tool calls, export, verify fidelity
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.export_service import ExportService
from src.exporter import export_session_to_llm_json, _render_llm_turn
from src.repositories import SQLiteConnection, SQLiteSessionRepository


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_text_item(role: str, text: str) -> dict:
    """Build the dehydrated dict as stored in api_history_json."""
    return {"role": role, "type": "text", "data": text}


def _make_function_call_item(
    name: str,
    args: dict,
    call_id: str,
    signature_hex: str | None = None,
) -> dict:
    return {
        "role": "model",
        "type": "function_call",
        "name": name,
        "args": args,
        "id": call_id,
        "signature": signature_hex,
    }


def _make_function_response_item(
    name: str,
    response: dict,
    call_id: str,
) -> dict:
    return {
        "role": "user",
        "type": "function_response",
        "name": name,
        "response": response,
        "id": call_id,
    }


def _seed_session(
    repo: SQLiteSessionRepository,
    session_id: str,
    title: str,
    api_items: list[dict],
    ui_messages: list[dict] | None = None,
) -> None:
    repo.save_session(
        session_id=session_id,
        title=title,
        api_history_json=json.dumps(api_items),
        ui_history_json=json.dumps(ui_messages or []),
    )


# ──────────────────────────────────────────────────────────────────────────────
# [T01] Empty api_history
# ──────────────────────────────────────────────────────────────────────────────

def test_t01_empty_history_returns_empty_turns() -> None:
    result = export_session_to_llm_json(api_items=[], title="Empty", session_id="s1")
    assert result["turns"] == []
    assert result["metadata"]["turn_count"] == 0
    assert result["metadata"]["title"] == "Empty"
    assert result["metadata"]["session_id"] == "s1"
    assert "export_timestamp" in result["metadata"]


# ──────────────────────────────────────────────────────────────────────────────
# [T02] User text turn
# ──────────────────────────────────────────────────────────────────────────────

def test_t02_user_text_turn() -> None:
    items = [_make_text_item("user", "Hello, what is MDF?")]
    result = export_session_to_llm_json(api_items=items, title="Test", session_id="s2")
    assert len(result["turns"]) == 1
    turn = result["turns"][0]
    assert turn["role"] == "user"
    assert len(turn["parts"]) == 1
    assert turn["parts"][0]["type"] == "text"
    assert turn["parts"][0]["text"] == "Hello, what is MDF?"


# ──────────────────────────────────────────────────────────────────────────────
# [T03] Model text turn
# ──────────────────────────────────────────────────────────────────────────────

def test_t03_model_text_turn() -> None:
    items = [_make_text_item("model", "MDF stands for Medium Density Fibreboard.")]
    result = export_session_to_llm_json(api_items=items, title="Test", session_id="s3")
    turn = result["turns"][0]
    assert turn["role"] == "model"
    assert turn["parts"][0]["text"] == "MDF stands for Medium Density Fibreboard."


# ──────────────────────────────────────────────────────────────────────────────
# [T04] Multi-turn preserves order
# ──────────────────────────────────────────────────────────────────────────────

def test_t04_multi_turn_preserves_order() -> None:
    items = [
        _make_text_item("user",  "First message"),
        _make_text_item("model", "First reply"),
        _make_text_item("user",  "Second message"),
        _make_text_item("model", "Second reply"),
    ]
    result = export_session_to_llm_json(api_items=items, title="T", session_id="s4")
    texts = [t["parts"][0]["text"] for t in result["turns"]]
    assert texts == ["First message", "First reply", "Second message", "Second reply"]


# ──────────────────────────────────────────────────────────────────────────────
# [T05] Function-call part with thought_signature
# ──────────────────────────────────────────────────────────────────────────────

def test_t05_function_call_part_with_signature() -> None:
    sig_hex = "deadbeef01020304"
    items = [
        _make_function_call_item(
            name="read_file",
            args={"filepath": "notes.md"},
            call_id="call-abc",
            signature_hex=sig_hex,
        )
    ]
    result = export_session_to_llm_json(api_items=items, title="T", session_id="s5")
    part = result["turns"][0]["parts"][0]
    assert part["type"] == "function_call"
    assert part["name"] == "read_file"
    assert part["args"] == {"filepath": "notes.md"}
    assert part["id"] == "call-abc"
    assert part["thought_signature_hex"] == sig_hex


# ──────────────────────────────────────────────────────────────────────────────
# [T06] Function-call with NO thought_signature → null
# ──────────────────────────────────────────────────────────────────────────────

def test_t06_function_call_without_signature_is_null() -> None:
    items = [
        _make_function_call_item(
            name="get_repo_map",
            args={},
            call_id="call-xyz",
            signature_hex=None,
        )
    ]
    result = export_session_to_llm_json(api_items=items, title="T", session_id="s6")
    part = result["turns"][0]["parts"][0]
    assert part["thought_signature_hex"] is None


# ──────────────────────────────────────────────────────────────────────────────
# [T07] Function-response part
# ──────────────────────────────────────────────────────────────────────────────

def test_t07_function_response_part() -> None:
    items = [
        _make_function_response_item(
            name="read_file",
            response={"content": "# Notes\nSome content."},
            call_id="call-abc",
        )
    ]
    result = export_session_to_llm_json(api_items=items, title="T", session_id="s7")
    part = result["turns"][0]["parts"][0]
    assert part["type"] == "function_response"
    assert part["name"] == "read_file"
    assert part["response"] == {"content": "# Notes\nSome content."}
    assert part["id"] == "call-abc"


# ──────────────────────────────────────────────────────────────────────────────
# [T08] Multi-part Content — ALL parts rendered
# Note: The current serializer only stores parts[0]. This test validates the
# export function handles a list of parts correctly, in preparation for
# future multi-part support.
# ──────────────────────────────────────────────────────────────────────────────

def test_t08_multi_part_turn_renders_all_parts() -> None:
    """
    The exporter's _render_llm_turn() must handle a turn dict that already
    has a 'parts' list (future multi-part format) rather than the flat
    dehydrated format.
    """
    turn_dict = {
        "role": "user",
        "parts": [
            {"type": "text", "text": "First part"},
            {"type": "text", "text": "Second part"},
        ],
    }
    rendered = _render_llm_turn(turn_dict, already_has_parts=True)
    assert len(rendered["parts"]) == 2
    assert rendered["parts"][0]["text"] == "First part"
    assert rendered["parts"][1]["text"] == "Second part"


# ──────────────────────────────────────────────────────────────────────────────
# [T09] Unknown part type → "unknown_part"
# ──────────────────────────────────────────────────────────────────────────────

def test_t09_unknown_part_type_marked_unknown() -> None:
    items = [{"role": "model", "type": "inline_image", "data": "base64stuff"}]
    result = export_session_to_llm_json(api_items=items, title="T", session_id="s9")
    part = result["turns"][0]["parts"][0]
    assert part["type"] == "unknown_part"
    assert "raw" in part  # preserve the raw data for debugging


# ──────────────────────────────────────────────────────────────────────────────
# [T10] Metadata block is complete
# ──────────────────────────────────────────────────────────────────────────────

def test_t10_metadata_block_complete() -> None:
    items = [_make_text_item("user", "hi")]
    result = export_session_to_llm_json(api_items=items, title="My Session", session_id="meta-1")
    meta = result["metadata"]
    assert meta["session_id"] == "meta-1"
    assert meta["title"] == "My Session"
    assert meta["turn_count"] == 1
    # export_timestamp is an ISO string
    assert isinstance(meta["export_timestamp"], str)
    assert "T" in meta["export_timestamp"]  # ISO format check


# ──────────────────────────────────────────────────────────────────────────────
# [T11] turn_count matches actual turns, not ui_messages count
# ──────────────────────────────────────────────────────────────────────────────

def test_t11_turn_count_matches_api_items_length() -> None:
    # 3 API turns (user, model-tool-call, user-tool-response)
    items = [
        _make_text_item("user", "Edit foo.md"),
        _make_function_call_item("edit_file", {"filepath": "foo.md", "search_text": "old", "replace_text": "new"}, "c1"),
        _make_function_response_item("edit_file", {"success": "ok"}, "c1"),
    ]
    result = export_session_to_llm_json(api_items=items, title="T", session_id="s11")
    assert result["metadata"]["turn_count"] == 3
    assert len(result["turns"]) == 3


# ──────────────────────────────────────────────────────────────────────────────
# [T12] Unicode / special characters preserved faithfully
# ──────────────────────────────────────────────────────────────────────────────

def test_t12_unicode_preserved() -> None:
    polish_text = "Płyta MDF 18mm — grubość standardowa. Cięcie: ≥ 150mm."
    items = [_make_text_item("user", polish_text)]
    result = export_session_to_llm_json(api_items=items, title="PL", session_id="s12")
    assert result["turns"][0]["parts"][0]["text"] == polish_text


# ──────────────────────────────────────────────────────────────────────────────
# [T13] thought_signature bytes round-trip through hex
# ──────────────────────────────────────────────────────────────────────────────

def test_t13_thought_signature_round_trip() -> None:
    original_bytes = b"\xde\xad\xbe\xef\x00\x01\x02\x03"
    hex_str = original_bytes.hex()
    items = [
        _make_function_call_item("read_file", {"filepath": "a.md"}, "c1", signature_hex=hex_str)
    ]
    result = export_session_to_llm_json(api_items=items, title="T", session_id="s13")
    recovered_hex = result["turns"][0]["parts"][0]["thought_signature_hex"]
    assert bytes.fromhex(recovered_hex) == original_bytes


# ──────────────────────────────────────────────────────────────────────────────
# [T14] Repository integration
# ──────────────────────────────────────────────────────────────────────────────

def test_t14_repo_export_llm_json_returns_structured_dict(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(conn)
    api_items = [
        _make_text_item("user", "What screws for 18mm shelf?"),
        _make_text_item("model", "Use 3.5×30mm countersunk screws."),
    ]
    _seed_session(repo, "repo-1", "Screws Q&A", api_items)

    svc = ExportService(repo)
    result = svc.export_llm_json("repo-1")
    assert isinstance(result, dict)
    assert result["metadata"]["session_id"] == "repo-1"
    assert result["metadata"]["title"] == "Screws Q&A"
    assert len(result["turns"]) == 2
    assert result["turns"][0]["parts"][0]["text"] == "What screws for 18mm shelf?"


def test_t14b_repo_export_llm_json_empty_api_history(tmp_path: Path) -> None:
    """Session exists but has no API history — should return empty turns."""
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(conn)
    _seed_session(repo, "repo-empty", "No History", api_items=[])

    svc = ExportService(repo)
    result = svc.export_llm_json("repo-empty")
    assert result["turns"] == []
    assert result["metadata"]["turn_count"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# [T15] Non-existent session raises ValueError
# ──────────────────────────────────────────────────────────────────────────────

def test_t15_nonexistent_session_raises_value_error(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(conn)
    with pytest.raises(ValueError, match="Session not found"):
        ExportService(repo).export_llm_json("does-not-exist")


# ──────────────────────────────────────────────────────────────────────────────
# HTTP layer tests — TestClient
# ──────────────────────────────────────────────────────────────────────────────

def _make_test_client(tmp_path: Path) -> tuple[TestClient, SQLiteSessionRepository]:
    """Creates an isolated TestClient with its own DB and data_dir."""
    from src.main import app
    from src.repositories import SQLiteConnection, SQLiteSessionRepository

    test_db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    test_repo = SQLiteSessionRepository(test_db)

    from src import dependencies as main_module
    from src.config import settings

    # Patch settings.data_dir so file operations don't touch real data
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    def _override_session_repo():
        return test_repo

    app.dependency_overrides[main_module.get_session_repo] = _override_session_repo

    with patch.object(settings, "data_dir", data_dir):
        client = TestClient(app)

    app.dependency_overrides.clear()
    return client, test_repo


# ──────────────────────────────────────────────────────────────────────────────
# [T16] 200 JSON response with correct shape
# ──────────────────────────────────────────────────────────────────────────────

def test_t16_endpoint_returns_200_with_correct_shape(tmp_path: Path) -> None:
    from src.main import app
    from src.repositories import SQLiteConnection, SQLiteSessionRepository

    test_db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    test_repo = SQLiteSessionRepository(test_db)

    api_items = [
        _make_text_item("user", "Describe shelf pin spacing."),
        _make_text_item("model", "Standard spacing is 32mm system."),
    ]
    _seed_session(test_repo, "http-1", "Shelf Pins", api_items)

    from src import dependencies as main_module

    def _override():
        return test_repo

    app.dependency_overrides[main_module.get_session_repo] = _override
    try:
        client = TestClient(app)
        response = client.get("/api/sessions/http-1/export/llm")
        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data
        assert "turns" in data
        assert data["metadata"]["session_id"] == "http-1"
        assert data["metadata"]["title"] == "Shelf Pins"
        assert len(data["turns"]) == 2
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────────────
# [T17] 404 for unknown session
# ──────────────────────────────────────────────────────────────────────────────

def test_t17_endpoint_returns_404_for_unknown_session(tmp_path: Path) -> None:
    from src.main import app
    from src.repositories import SQLiteConnection, SQLiteSessionRepository

    test_db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    test_repo = SQLiteSessionRepository(test_db)

    from src import dependencies as main_module

    def _override():
        return test_repo

    app.dependency_overrides[main_module.get_session_repo] = _override
    try:
        client = TestClient(app)
        response = client.get("/api/sessions/ghost-session/export/llm")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────────────
# [T18] Content-Type is application/json
# ──────────────────────────────────────────────────────────────────────────────

def test_t18_content_type_is_application_json(tmp_path: Path) -> None:
    from src.main import app
    from src.repositories import SQLiteConnection, SQLiteSessionRepository

    test_db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    test_repo = SQLiteSessionRepository(test_db)
    _seed_session(test_repo, "ct-1", "CT Test", [_make_text_item("user", "hi")])

    from src import dependencies as main_module

    def _override():
        return test_repo

    app.dependency_overrides[main_module.get_session_repo] = _override
    try:
        client = TestClient(app)
        response = client.get("/api/sessions/ct-1/export/llm")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────────────
# [T19] Distinct from existing Markdown export
# ──────────────────────────────────────────────────────────────────────────────

def test_t19_llm_export_distinct_from_markdown_export(tmp_path: Path) -> None:
    from src.main import app
    from src.repositories import SQLiteConnection, SQLiteSessionRepository

    test_db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    test_repo = SQLiteSessionRepository(test_db)
    _seed_session(
        test_repo, "dual-1", "Dual Export",
        api_items=[_make_text_item("user", "test")],
        ui_messages=[{"role": "user", "content": "test"}],
    )

    from src import dependencies as main_module

    def _override():
        return test_repo

    app.dependency_overrides[main_module.get_session_repo] = _override
    try:
        client = TestClient(app)

        md_resp = client.get("/api/sessions/dual-1/export")
        llm_resp = client.get("/api/sessions/dual-1/export/llm")

        assert md_resp.status_code == 200
        assert llm_resp.status_code == 200

        # Markdown export returns text/markdown
        assert "text/markdown" in md_resp.headers["content-type"]
        # LLM export returns JSON
        assert "application/json" in llm_resp.headers["content-type"]

        # Markdown export returns a string body; LLM returns structured JSON
        assert isinstance(llm_resp.json(), dict)
        assert "turns" in llm_resp.json()
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────────────
# [T20] Full round-trip with tool calls — fidelity test
# ──────────────────────────────────────────────────────────────────────────────

def test_t20_full_round_trip_with_tool_calls(tmp_path: Path) -> None:
    """
    Simulates a real agentic session:
      user text → model function_call → user function_response → model text
    and verifies every field survives the export cycle faithfully.
    """
    from src.main import app
    from src.repositories import SQLiteConnection, SQLiteSessionRepository

    test_db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    test_repo = SQLiteSessionRepository(test_db)

    sig_hex = "cafebabe"
    api_items = [
        _make_text_item("user", "What is in notes.md?"),
        _make_function_call_item("read_file", {"filepath": "notes.md"}, "fc-001", sig_hex),
        _make_function_response_item("read_file", {"content": "# Notes\nHello."}, "fc-001"),
        _make_text_item("model", "The notes file contains a heading 'Notes' and the word Hello."),
    ]
    _seed_session(test_repo, "rt-1", "Round Trip Test", api_items)

    from src import dependencies as main_module

    def _override():
        return test_repo

    app.dependency_overrides[main_module.get_session_repo] = _override
    try:
        client = TestClient(app)
        response = client.get("/api/sessions/rt-1/export/llm")
        assert response.status_code == 200
        data = response.json()

        turns = data["turns"]
        assert len(turns) == 4

        # Turn 0: user text
        assert turns[0]["role"] == "user"
        assert turns[0]["parts"][0]["type"] == "text"
        assert turns[0]["parts"][0]["text"] == "What is in notes.md?"

        # Turn 1: model function_call with signature
        assert turns[1]["role"] == "model"
        assert turns[1]["parts"][0]["type"] == "function_call"
        assert turns[1]["parts"][0]["name"] == "read_file"
        assert turns[1]["parts"][0]["args"] == {"filepath": "notes.md"}
        assert turns[1]["parts"][0]["id"] == "fc-001"
        assert turns[1]["parts"][0]["thought_signature_hex"] == sig_hex

        # Turn 2: user function_response
        assert turns[2]["role"] == "user"
        assert turns[2]["parts"][0]["type"] == "function_response"
        assert turns[2]["parts"][0]["name"] == "read_file"
        assert turns[2]["parts"][0]["response"]["content"] == "# Notes\nHello."
        assert turns[2]["parts"][0]["id"] == "fc-001"

        # Turn 3: model final text
        assert turns[3]["role"] == "model"
        assert turns[3]["parts"][0]["type"] == "text"
        assert "heading" in turns[3]["parts"][0]["text"]

        # Metadata
        assert data["metadata"]["turn_count"] == 4
        assert data["metadata"]["title"] == "Round Trip Test"
    finally:
        app.dependency_overrides.clear()
