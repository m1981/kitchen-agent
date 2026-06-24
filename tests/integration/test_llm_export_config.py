"""
tests/test_llm_export_config.py
================================
TDD suite for F04: embedding GenerateContentConfig into the LLM debug export.

Feature extension: GET /api/sessions/{session_id}/export/llm now returns a
top-level ``"config"`` block placed BEFORE ``"turns"``, containing exactly
what the Gemini API received as its GenerateContentConfig envelope:

    {
      "metadata": { ... },
      "config": {
        "model":              "gemini-2.5-flash",
        "temperature":        0.2,
        "system_instruction": "You are a …" | null,
        "tools": [ { "function_declarations": [ … ] } ]
      },
      "turns": [ … ]
    }

Key design insight
------------------
GenerateContentConfig is NOT part of the stored api_history_json — it is a
stateless envelope rebuilt per-turn from:
  • DECLARATIONS  (registry.py — compile-time constant)
  • settings.gemini_temperature  (config.py)
  • ChatRequest.system_prompt    (← NOT persisted — gap fixed in F04)

F04 adds a ``system_prompt`` column to the ``sessions`` table and persists it
at ``save_session()`` time.  The export then reconstructs the full config by
combining the persisted system_prompt with the live registry/settings values.

Test IDs
--------
 ── Pure function layer (src/exporter.py) ───────────────────────────────────
  [C01]  build_config_block() with system_instruction returns correct shape
  [C02]  build_config_block() without system_instruction has null field
  [C03]  build_config_block() model name comes from settings
  [C04]  build_config_block() temperature comes from settings
  [C05]  build_config_block() tools list contains all 5 function declarations
  [C06]  build_config_block() each declaration has name, description, parameters
  [C07]  build_config_block() required fields preserved inside declaration
  [C08]  export_session_to_llm_json() result has "config" key BEFORE "turns"
  [C09]  export_session_to_llm_json() config block is identical to build_config_block()
  [C10]  export_session_to_llm_json() config present even for empty history
  [C11]  JSON key order: metadata → config → turns

 ── Repository layer (src/repositories.py) ──────────────────────────────────
  [C12]  save_session() accepts new system_prompt kwarg (default None)
  [C13]  load_session() returns system_prompt as third element
  [C14]  Existing sessions without system_prompt column return None gracefully
  [C15]  export_session_llm_json() passes persisted system_prompt into config block
  [C16]  export_session_llm_json() config.system_instruction is null when none was saved
  [C17]  fork_session() copies system_prompt to the forked child

 ── HTTP layer (src/main.py) ────────────────────────────────────────────────
  [C18]  GET export/llm response has "config" key in JSON body
  [C19]  "config" block appears before "turns" in serialised JSON string
  [C20]  config.tools list is non-empty in HTTP response
  [C21]  config.system_instruction is null when session has no system_prompt
  [C22]  config.system_instruction reflects persisted system_prompt
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Pure-function imports
from src.exporter import build_config_block, export_session_to_llm_json
from src.repositories import SQLiteConnection, SQLiteSessionRepository
from src.config import settings


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_text_item(role: str, text: str) -> dict:
    return {"role": role, "type": "text", "data": text}


def _seed(
    repo: SQLiteSessionRepository,
    session_id: str,
    title: str = "Test",
    api_items: list | None = None,
    system_prompt: str | None = None,
) -> None:
    repo.save_session(
        session_id=session_id,
        title=title,
        api_history_json=json.dumps(api_items or []),
        ui_history_json="[]",
        system_prompt=system_prompt,
    )


# ──────────────────────────────────────────────────────────────────────────────
# [C01] build_config_block() with system_instruction
# ──────────────────────────────────────────────────────────────────────────────

def test_c01_config_block_with_system_instruction() -> None:
    block = build_config_block(system_instruction="You are a kitchen expert.")
    assert block["system_instruction"] == "You are a kitchen expert."


# ──────────────────────────────────────────────────────────────────────────────
# [C02] build_config_block() without system_instruction → null
# ──────────────────────────────────────────────────────────────────────────────

def test_c02_config_block_system_instruction_null_when_absent() -> None:
    block = build_config_block(system_instruction=None)
    assert block["system_instruction"] is None


# ──────────────────────────────────────────────────────────────────────────────
# [C03] model name comes from settings
# ──────────────────────────────────────────────────────────────────────────────

def test_c03_config_block_model_from_settings() -> None:
    block = build_config_block(system_instruction=None)
    assert block["model"] == settings.gemini_model


# ──────────────────────────────────────────────────────────────────────────────
# [C04] temperature comes from settings
# ──────────────────────────────────────────────────────────────────────────────

def test_c04_config_block_temperature_from_settings() -> None:
    block = build_config_block(system_instruction=None)
    assert block["temperature"] == settings.gemini_temperature


# ──────────────────────────────────────────────────────────────────────────────
# [C05] tools list contains all 5 function declarations
# ──────────────────────────────────────────────────────────────────────────────

def test_c05_config_block_has_all_five_tools() -> None:
    from src.tools.registry import build_default_registry
    registry = build_default_registry()
    expected_count = len(registry.tool_names)
    block = build_config_block(system_instruction=None)
    # tools is a list with one Tool object containing function_declarations
    assert "tools" in block
    assert len(block["tools"]) == 1
    decls = block["tools"][0]["function_declarations"]
    assert len(decls) == expected_count


# ──────────────────────────────────────────────────────────────────────────────
# [C06] each declaration has name, description, parameters
# ──────────────────────────────────────────────────────────────────────────────

def test_c06_each_declaration_has_required_fields() -> None:
    block = build_config_block(system_instruction=None)
    for decl in block["tools"][0]["function_declarations"]:
        assert "name" in decl, f"Missing 'name' in {decl}"
        assert "description" in decl, f"Missing 'description' in {decl}"
        assert "parameters" in decl, f"Missing 'parameters' in {decl}"


# ──────────────────────────────────────────────────────────────────────────────
# [C07] required fields preserved inside each declaration
# ──────────────────────────────────────────────────────────────────────────────

def test_c07_required_fields_preserved_in_declarations() -> None:
    block = build_config_block(system_instruction=None)
    decls_by_name = {
        d["name"]: d for d in block["tools"][0]["function_declarations"]
    }

    # read_file requires 'filepath'
    assert "filepath" in decls_by_name["read_file"]["parameters"]["required"]

    # edit_file requires all three params
    edit_required = decls_by_name["edit_file"]["parameters"]["required"]
    assert "filepath" in edit_required
    assert "search_text" in edit_required
    assert "replace_text" in edit_required

    # get_repo_map requires nothing
    assert decls_by_name["get_repo_map"]["parameters"]["required"] == []


# ──────────────────────────────────────────────────────────────────────────────
# [C08] export_session_to_llm_json() result has "config" key BEFORE "turns"
# ──────────────────────────────────────────────────────────────────────────────

def test_c08_export_has_config_key() -> None:
    result = export_session_to_llm_json(
        api_items=[_make_text_item("user", "hello")],
        title="T",
        session_id="s1",
        system_instruction=None,
    )
    assert "config" in result


# ──────────────────────────────────────────────────────────────────────────────
# [C09] export config block is identical to build_config_block()
# ──────────────────────────────────────────────────────────────────────────────

def test_c09_export_config_matches_build_config_block() -> None:
    prompt = "You are a woodworker."
    result = export_session_to_llm_json(
        api_items=[],
        title="T",
        session_id="s9",
        system_instruction=prompt,
    )
    expected_block = build_config_block(system_instruction=prompt)
    assert result["config"]["model"] == expected_block["model"]
    assert result["config"]["temperature"] == expected_block["temperature"]
    assert result["config"]["system_instruction"] == expected_block["system_instruction"]
    assert len(result["config"]["tools"]) == len(expected_block["tools"])


# ──────────────────────────────────────────────────────────────────────────────
# [C10] config block present even for empty history
# ──────────────────────────────────────────────────────────────────────────────

def test_c10_config_present_for_empty_history() -> None:
    result = export_session_to_llm_json(
        api_items=[],
        title="Empty",
        session_id="s10",
        system_instruction=None,
    )
    assert "config" in result
    assert "tools" in result["config"]


# ──────────────────────────────────────────────────────────────────────────────
# [C11] JSON key order: metadata → config → turns
# ──────────────────────────────────────────────────────────────────────────────

def test_c11_key_order_metadata_config_turns() -> None:
    result = export_session_to_llm_json(
        api_items=[_make_text_item("user", "hi")],
        title="T",
        session_id="s11",
        system_instruction=None,
    )
    keys = list(result.keys())
    assert keys.index("metadata") < keys.index("config"), \
        "metadata must come before config"
    assert keys.index("config") < keys.index("turns"), \
        "config must come before turns"


# ──────────────────────────────────────────────────────────────────────────────
# [C12] save_session() accepts system_prompt kwarg
# ──────────────────────────────────────────────────────────────────────────────

def test_c12_save_session_accepts_system_prompt(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(conn)
    # Must not raise
    repo.save_session(
        session_id="c12",
        title="C12",
        api_history_json="[]",
        ui_history_json="[]",
        system_prompt="You are a kitchen expert.",
    )
    api_json, ui_json, system_prompt = repo.load_session("c12")
    assert system_prompt == "You are a kitchen expert."


# ──────────────────────────────────────────────────────────────────────────────
# [C13] load_session() returns system_prompt as third element
# ──────────────────────────────────────────────────────────────────────────────

def test_c13_load_session_returns_three_tuple(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(conn)
    _seed(repo, "c13", system_prompt="Hello system")
    result = repo.load_session("c13")
    assert len(result) == 3
    api_json, ui_json, system_prompt = result
    assert system_prompt == "Hello system"


# ──────────────────────────────────────────────────────────────────────────────
# [C14] Missing/NULL system_prompt column → returns None gracefully
# ──────────────────────────────────────────────────────────────────────────────

def test_c14_missing_system_prompt_returns_none(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(conn)
    # Save without providing system_prompt (defaults to None)
    repo.save_session(
        session_id="c14",
        title="C14",
        api_history_json="[]",
        ui_history_json="[]",
    )
    _, _, system_prompt = repo.load_session("c14")
    assert system_prompt is None


# ──────────────────────────────────────────────────────────────────────────────
# [C15] export_session_llm_json() passes persisted system_prompt into config
# ──────────────────────────────────────────────────────────────────────────────

def test_c15_export_uses_persisted_system_prompt(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(conn)
    _seed(repo, "c15", system_prompt="You are a cabinet specialist.")
    from src.export_service import ExportService
    svc = ExportService(repo)
    result = svc.export_llm_json("c15")
    assert result["config"]["system_instruction"] == "You are a cabinet specialist."


# ──────────────────────────────────────────────────────────────────────────────
# [C16] system_instruction null when none was saved
# ──────────────────────────────────────────────────────────────────────────────

def test_c16_export_config_instruction_null_when_none_saved(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(conn)
    _seed(repo, "c16", system_prompt=None)
    from src.export_service import ExportService
    svc = ExportService(repo)
    result = svc.export_llm_json("c16")
    assert result["config"]["system_instruction"] is None


# ──────────────────────────────────────────────────────────────────────────────
# [C17] fork_session() copies system_prompt to forked child
# ──────────────────────────────────────────────────────────────────────────────

def test_c17_fork_copies_system_prompt(tmp_path: Path) -> None:
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(conn)
    _seed(
        repo, "parent-c17",
        api_items=[_make_text_item("user", "Hello"), _make_text_item("model", "Hi")],
        system_prompt="You are a master woodworker.",
    )
    child_id = repo.fork_session("parent-c17", turn_index=0)
    _, _, child_prompt = repo.load_session(child_id)
    assert child_prompt == "You are a master woodworker."


# ──────────────────────────────────────────────────────────────────────────────
# HTTP layer helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_client(tmp_path: Path) -> tuple[TestClient, SQLiteSessionRepository]:
    from src.main import app
    from src import dependencies as main_module

    test_db = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    test_repo = SQLiteSessionRepository(test_db)

    def _override():
        return test_repo

    app.dependency_overrides[main_module.get_session_repo] = _override
    client = TestClient(app)
    return client, test_repo


# ──────────────────────────────────────────────────────────────────────────────
# [C18] GET export/llm response has "config" key in JSON body
# ──────────────────────────────────────────────────────────────────────────────

def test_c18_http_response_has_config_key(tmp_path: Path) -> None:
    from src.main import app

    client, repo = _make_client(tmp_path)
    try:
        _seed(repo, "http-c18")
        resp = client.get("/api/sessions/http-c18/export/llm")
        assert resp.status_code == 200
        assert "config" in resp.json()
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────────────
# [C19] "config" appears before "turns" in raw serialised JSON string
# ──────────────────────────────────────────────────────────────────────────────

def test_c19_config_before_turns_in_raw_json(tmp_path: Path) -> None:
    from src.main import app

    client, repo = _make_client(tmp_path)
    try:
        _seed(repo, "http-c19")
        resp = client.get("/api/sessions/http-c19/export/llm")
        raw = resp.text
        config_pos = raw.index('"config"')
        turns_pos = raw.index('"turns"')
        assert config_pos < turns_pos, \
            '"config" must appear before "turns" in the serialised JSON'
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────────────
# [C20] config.tools list is non-empty in HTTP response
# ──────────────────────────────────────────────────────────────────────────────

def test_c20_config_tools_non_empty_in_http_response(tmp_path: Path) -> None:
    from src.main import app

    client, repo = _make_client(tmp_path)
    try:
        _seed(repo, "http-c20")
        resp = client.get("/api/sessions/http-c20/export/llm")
        data = resp.json()
        assert len(data["config"]["tools"]) > 0
        assert len(data["config"]["tools"][0]["function_declarations"]) == 5
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────────────
# [C21] config.system_instruction null when session has no system_prompt
# ──────────────────────────────────────────────────────────────────────────────

def test_c21_http_system_instruction_null_when_not_set(tmp_path: Path) -> None:
    from src.main import app

    client, repo = _make_client(tmp_path)
    try:
        _seed(repo, "http-c21", system_prompt=None)
        resp = client.get("/api/sessions/http-c21/export/llm")
        data = resp.json()
        assert data["config"]["system_instruction"] is None
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────────────
# [C22] config.system_instruction reflects persisted system_prompt
# ──────────────────────────────────────────────────────────────────────────────

def test_c22_http_system_instruction_reflects_persisted_prompt(tmp_path: Path) -> None:
    from src.main import app

    client, repo = _make_client(tmp_path)
    try:
        _seed(repo, "http-c22", system_prompt="You are a Blum hinge specialist.")
        resp = client.get("/api/sessions/http-c22/export/llm")
        data = resp.json()
        assert data["config"]["system_instruction"] == "You are a Blum hinge specialist."
    finally:
        app.dependency_overrides.clear()
