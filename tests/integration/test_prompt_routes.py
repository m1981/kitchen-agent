"""
tests/test_prompt_routes.py
============================
TDD tests for F05 backend-prompt endpoints and the updated /api/chat flow.

Coverage contract:
  GET  /api/prompts/modes           — returns list[{id, label, eyebrow}]
  GET  /api/prompts/modes/{mode_id} — returns full content for one mode (200 / 404)
  POST /api/prompts/reload          — hot-reloads files; returns {success: true}
  POST /api/chat with mode_id       — resolves mode_id → system_instruction via PromptManager
  POST /api/chat backward compat    — system_prompt field still accepted (legacy)
  Dependency override ensures PromptManager is isolated from real disk
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import src.config as main_module
from src import config as config_module
from src.main import app
from src.dependencies import get_chat_service, get_prompt_manager
from src.chat_service import ChatTurnResponse
from src.prompt_manager import PromptManager, PromptMode


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_KITCHEN_MODES = [
    {"id": "general",  "label": "General",  "eyebrow": "Workspace help",       "file": "general.md"},
    {"id": "design",   "label": "Design",   "eyebrow": "Ergonomics and layout", "file": "design.md"},
    {"id": "assembly", "label": "Assembly", "eyebrow": "Build and fitting",     "file": "assembly.md"},
]


def _make_prompt_manager(tmp_path: Path) -> PromptManager:
    """Create an isolated PromptManager backed by tmp_path prompt files."""
    (tmp_path / "modes.json").write_text(json.dumps(_KITCHEN_MODES), encoding="utf-8")
    (tmp_path / "base_agent_rules.md").write_text("BASE RULES\n", encoding="utf-8")
    (tmp_path / "general.md").write_text("GENERAL CONTENT\n", encoding="utf-8")
    (tmp_path / "design.md").write_text("DESIGN CONTENT\n", encoding="utf-8")
    (tmp_path / "assembly.md").write_text("ASSEMBLY CONTENT\n", encoding="utf-8")
    return PromptManager(prompts_dir=str(tmp_path))


def _stub_chat_service(text: str = "ok", tools: list | None = None):
    """Returns a FastAPI dependency override that yields a stubbed ChatService."""
    svc = MagicMock()
    svc.handle_turn.return_value = ChatTurnResponse(session_id="test-session", assistant_message=text, ui_history=[], user_turn_id="test-user-id", assistant_turn_id="test-assistant-id", tool_calls_made=tools or [])
    return lambda: svc


# ---------------------------------------------------------------------------
# GET /api/prompts/modes
# ---------------------------------------------------------------------------

def test_get_prompt_modes_returns_200(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).get("/api/prompts/modes")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_get_prompt_modes_returns_list(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).get("/api/prompts/modes")
        assert isinstance(resp.json(), list)
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_get_prompt_modes_has_three_modes(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        modes = TestClient(app).get("/api/prompts/modes").json()
        ids = {m["id"] for m in modes}
        assert ids == {"general", "design", "assembly"}
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_get_prompt_modes_shape(tmp_path: Path, monkeypatch) -> None:
    """Each item must have id, label, eyebrow — never content."""
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        modes = TestClient(app).get("/api/prompts/modes").json()
        for m in modes:
            assert "id" in m
            assert "label" in m
            assert "eyebrow" in m
            assert "content" not in m, "content must NOT be exposed in the list response"
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_get_prompt_modes_correct_labels(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        modes = TestClient(app).get("/api/prompts/modes").json()
        by_id = {m["id"]: m for m in modes}
        assert by_id["general"]["label"]    == "General"
        assert by_id["design"]["label"]     == "Design"
        assert by_id["assembly"]["label"]   == "Assembly"
        assert by_id["general"]["eyebrow"]  == "Workspace help"
        assert by_id["design"]["eyebrow"]   == "Ergonomics and layout"
        assert by_id["assembly"]["eyebrow"] == "Build and fitting"
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


# ---------------------------------------------------------------------------
# GET /api/prompts/modes/{mode_id}  — detail with content
# ---------------------------------------------------------------------------

def test_get_prompt_mode_detail_returns_200(tmp_path: Path, monkeypatch) -> None:
    """Returns 200 for a known mode_id."""
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).get("/api/prompts/modes/design")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_get_prompt_mode_detail_includes_content(tmp_path: Path, monkeypatch) -> None:
    """Response must include the full combined prompt content."""
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        body = TestClient(app).get("/api/prompts/modes/design").json()
        assert "content" in body
        assert "DESIGN CONTENT" in body["content"]
        assert "BASE RULES" in body["content"]
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_get_prompt_mode_detail_has_all_fields(tmp_path: Path, monkeypatch) -> None:
    """Response must have id, label, eyebrow, and content."""
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        body = TestClient(app).get("/api/prompts/modes/general").json()
        assert body["id"]      == "general"
        assert body["label"]   == "General"
        assert body["eyebrow"] == "Workspace help"
        assert "GENERAL CONTENT" in body["content"]
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_get_prompt_mode_detail_assembly(tmp_path: Path, monkeypatch) -> None:
    """Works for all three built-in modes."""
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        body = TestClient(app).get("/api/prompts/modes/assembly").json()
        assert "ASSEMBLY CONTENT" in body["content"]
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_get_prompt_mode_detail_unknown_returns_404(tmp_path: Path, monkeypatch) -> None:
    """Returns 404 for an unregistered mode_id."""
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).get("/api/prompts/modes/nonexistent")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_get_prompt_mode_detail_404_has_detail_field(tmp_path: Path, monkeypatch) -> None:
    """404 response must include a detail field explaining what was not found."""
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        body = TestClient(app).get("/api/prompts/modes/ghost").json()
        assert "detail" in body
        assert "ghost" in body["detail"]
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


# ---------------------------------------------------------------------------
# POST /api/prompts/reload
# ---------------------------------------------------------------------------

def test_reload_endpoint_returns_200(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/prompts/reload")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_reload_endpoint_returns_success_true(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        body = TestClient(app).post("/api/prompts/reload").json()
        assert body.get("success") is True
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


def test_reload_endpoint_calls_reload_prompts(tmp_path: Path, monkeypatch) -> None:
    pm = MagicMock(spec=PromptManager)
    pm.reload_prompts.return_value = None
    app.dependency_overrides[get_prompt_manager] = lambda: pm
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        TestClient(app).post("/api/prompts/reload")
        pm.reload_prompts.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)


# ---------------------------------------------------------------------------
# POST /api/chat — mode_id resolves to system_instruction
# ---------------------------------------------------------------------------

def test_chat_with_mode_id_resolves_instruction(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    captured: dict = {}

    class CaptureSvc:
        def handle_turn(self, request):
            captured.update({"user_message": request.user_message, "system_prompt": request.system_prompt, "mode": request.mode, "use_tools": request.use_tools})
            return ChatTurnResponse(session_id=request.session_id, assistant_message="done", ui_history=[], user_turn_id="test-user-id", assistant_turn_id="test-assistant-id", tool_calls_made=[])

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: CaptureSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id": "s1",
            "message":    "test",
            "mode_id":    "design",
        })
        assert resp.status_code == 200
        passed_prompt = captured.get("system_prompt", "")
        assert "DESIGN CONTENT" in passed_prompt
        assert "BASE RULES" in passed_prompt
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


def test_chat_mode_id_defaults_to_general(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    captured: dict = {}

    class CaptureSvc:
        def handle_turn(self, request):
            captured.update({"user_message": request.user_message, "system_prompt": request.system_prompt, "mode": request.mode, "use_tools": request.use_tools})
            return ChatTurnResponse(session_id=request.session_id, assistant_message="done", ui_history=[], user_turn_id="test-user-id", assistant_turn_id="test-assistant-id", tool_calls_made=[])

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: CaptureSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id": "s2",
            "message":    "hello",
        })
        assert resp.status_code == 200
        assert "GENERAL CONTENT" in captured.get("system_prompt", "")
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


def test_chat_unknown_mode_id_falls_back_to_base(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    captured: dict = {}

    class CaptureSvc:
        def handle_turn(self, request):
            captured.update({"user_message": request.user_message, "system_prompt": request.system_prompt, "mode": request.mode, "use_tools": request.use_tools})
            return ChatTurnResponse(session_id=request.session_id, assistant_message="done", ui_history=[], user_turn_id="test-user-id", assistant_turn_id="test-assistant-id", tool_calls_made=[])

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: CaptureSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id": "s3",
            "message":    "hello",
            "mode_id":    "nonexistent_mode",
        })
        assert resp.status_code == 200
        assert "BASE RULES" in captured.get("system_prompt", "")
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


def test_chat_assembly_mode_resolves_correctly(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    captured: dict = {}

    class CaptureSvc:
        def handle_turn(self, request):
            captured.update({"user_message": request.user_message, "system_prompt": request.system_prompt, "mode": request.mode, "use_tools": request.use_tools})
            return ChatTurnResponse(session_id=request.session_id, assistant_message="done", ui_history=[], user_turn_id="test-user-id", assistant_turn_id="test-assistant-id", tool_calls_made=[])

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: CaptureSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id": "s4",
            "message":    "how do I mount hinges?",
            "mode_id":    "assembly",
        })
        assert resp.status_code == 200
        assert "ASSEMBLY CONTENT" in captured.get("system_prompt", "")
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


def test_chat_legacy_system_prompt_still_accepted(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    captured: dict = {}

    class CaptureSvc:
        def handle_turn(self, request):
            captured.update({"user_message": request.user_message, "system_prompt": request.system_prompt, "mode": request.mode, "use_tools": request.use_tools})
            return ChatTurnResponse(session_id=request.session_id, assistant_message="done", ui_history=[], user_turn_id="test-user-id", assistant_turn_id="test-assistant-id", tool_calls_made=[])

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: CaptureSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id":    "s5",
            "message":       "legacy call",
            "system_prompt": "MY CUSTOM LEGACY PROMPT",
        })
        assert resp.status_code == 200
        assert captured.get("system_prompt") == "MY CUSTOM LEGACY PROMPT"
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


def test_chat_system_prompt_overrides_mode_id(tmp_path: Path, monkeypatch) -> None:
    pm = _make_prompt_manager(tmp_path)
    captured: dict = {}

    class CaptureSvc:
        def handle_turn(self, request):
            captured.update({"user_message": request.user_message, "system_prompt": request.system_prompt, "mode": request.mode, "use_tools": request.use_tools})
            return ChatTurnResponse(session_id=request.session_id, assistant_message="done", ui_history=[], user_turn_id="test-user-id", assistant_turn_id="test-assistant-id", tool_calls_made=[])

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: CaptureSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id":    "s6",
            "message":       "override test",
            "mode_id":       "design",
            "system_prompt": "EXPLICIT OVERRIDE PROMPT",
        })
        assert resp.status_code == 200
        assert captured.get("system_prompt") == "EXPLICIT OVERRIDE PROMPT"
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


# ---------------------------------------------------------------------------
# POST /api/chat — turn_ids in response
# ---------------------------------------------------------------------------

def test_chat_response_includes_turn_ids(tmp_path: Path, monkeypatch) -> None:
    """ChatResponse must include user_turn_id and assistant_turn_id."""
    pm = _make_prompt_manager(tmp_path)

    class TurnIdSvc:
        def handle_turn(self, request):
            return ChatTurnResponse(
                session_id=request.session_id,
                assistant_message="response",
                ui_history=[],
                user_turn_id="user-uuid-123",
                assistant_turn_id="assistant-uuid-456",
                tool_calls_made=[],
            )

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: TurnIdSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id": "s-turn-ids",
            "message":    "hello",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["text"] == "response"
        assert body["user_turn_id"] == "user-uuid-123"
        assert body["assistant_turn_id"] == "assistant-uuid-456"
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


# ---------------------------------------------------------------------------
# POST /api/chat — provider routing
# ---------------------------------------------------------------------------

def test_chat_passes_provider_and_model(tmp_path: Path, monkeypatch) -> None:
    """provider and model from request must be forwarded to ChatTurnRequest."""
    pm = _make_prompt_manager(tmp_path)
    captured: dict = {}

    class ProviderCaptureSvc:
        def handle_turn(self, request):
            captured["provider"] = request.provider
            captured["model"] = request.model
            return ChatTurnResponse(
                session_id=request.session_id,
                assistant_message="ok",
                ui_history=[],
                user_turn_id="uid",
                assistant_turn_id="aid",
                tool_calls_made=[],
            )

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: ProviderCaptureSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id": "s-provider",
            "message":    "hello",
            "provider":   "anthropic",
            "model":      "claude-sonnet-4-20250514",
        })
        assert resp.status_code == 200
        assert captured["provider"] == "anthropic"
        assert captured["model"] == "claude-sonnet-4-20250514"
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


def test_chat_no_provider_uses_none(tmp_path: Path, monkeypatch) -> None:
    """When provider/model omitted, ChatTurnRequest fields should be None."""
    pm = _make_prompt_manager(tmp_path)
    captured: dict = {}

    class DefaultCaptureSvc:
        def handle_turn(self, request):
            captured["provider"] = request.provider
            captured["model"] = request.model
            return ChatTurnResponse(
                session_id=request.session_id,
                assistant_message="ok",
                ui_history=[],
                user_turn_id="uid",
                assistant_turn_id="aid",
                tool_calls_made=[],
            )

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: DefaultCaptureSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id": "s-default",
            "message":    "hello",
        })
        assert resp.status_code == 200
        assert captured["provider"] is None
        assert captured["model"] is None
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


# ---------------------------------------------------------------------------
# POST /api/chat — provider/model in response
# ---------------------------------------------------------------------------

def test_chat_response_includes_provider_and_model(tmp_path: Path, monkeypatch) -> None:
    """ChatResponse must include provider and model from the orchestrator."""
    pm = _make_prompt_manager(tmp_path)

    class ProviderModelSvc:
        def handle_turn(self, request):
            return ChatTurnResponse(
                session_id=request.session_id,
                assistant_message="response",
                ui_history=[],
                user_turn_id="uid",
                assistant_turn_id="aid",
                tool_calls_made=[],
                provider_name="anthropic",
                model_name="claude-sonnet-4-20250514",
            )

    app.dependency_overrides[get_prompt_manager] = lambda: pm
    app.dependency_overrides[get_chat_service] = lambda: ProviderModelSvc()
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    try:
        resp = TestClient(app).post("/api/chat", json={
            "session_id": "s-provider-model",
            "message":    "hello",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "anthropic"
        assert body["model"] == "claude-sonnet-4-20250514"
    finally:
        app.dependency_overrides.pop(get_prompt_manager, None)
        app.dependency_overrides.pop(get_chat_service, None)


# ---------------------------------------------------------------------------
# DI factory
# ---------------------------------------------------------------------------

def test_get_prompt_manager_dependency_returns_instance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main_module.settings, "data_dir", tmp_path)
    from src.dependencies import get_prompt_manager as gpm
    result = gpm()
    assert isinstance(result, PromptManager)
