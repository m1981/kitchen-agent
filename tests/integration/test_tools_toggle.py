"""
tests/test_tools_toggle.py
===========================
TDD tests for the tools_enabled toggle — Option C implementation.

Feature:  Any chat request can disable the agentic tool-calling loop and
          get a direct LLM response instead.  The flag flows through every
          layer of the stack:

  ChatRequest.tools_enabled (bool, default True)
      → ChatService.handle_turn(use_tools=...)
          → agent.process_chat_turn(use_tools=...)
              → GeminiProvider / AnthropicProvider

  Additionally, PromptMode carries a default value loaded from modes.json
  ("tools_enabled" key, default True when absent).  The ChatService resolves
  the effective flag as:

      effective = request.tools_enabled ?? mode.tools_enabled_default

  i.e. if the request omits the field entirely the mode default applies;
  if the request explicitly sets it that value wins.

Layers tested here (provider-level tests live in their own files):
  1. PromptManager / PromptMode — tools_enabled_default from modes.json
  2. ChatService — threads use_tools down to the agent
  3. POST /api/chat — serialisation + route handler wiring
  4. Integration: tools_enabled=False → agent called with use_tools=False
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.prompt_manager import PromptManager, PromptMode
from src.chat_service import ChatService, ChatTurnRequest, ChatTurnResponse
from src.repositories import SQLiteConnection, SQLiteSessionRepository
from src.main import app
from src.dependencies import get_chat_service
from tests.helpers import FakeOrchestrator


# ===========================================================================
# Helpers
# ===========================================================================

def _write(directory: Path, filename: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(text, encoding="utf-8")


def _write_modes(directory: Path, modes: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "modes.json").write_text(json.dumps(modes), encoding="utf-8")


# ===========================================================================
# 1. PromptManager / PromptMode — tools_enabled_default
# ===========================================================================

class TestPromptModeToolsEnabledDefault:
    """PromptMode must expose tools_enabled_default loaded from modes.json."""

    def test_tools_enabled_defaults_to_true_when_key_absent(self, tmp_path: Path) -> None:
        """When modes.json entry has no 'tools_enabled' key, default is True."""
        modes = [{"id": "general", "label": "General", "eyebrow": "Help", "file": "general.md"}]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "")
        _write(tmp_path, "general.md", "You are helpful.")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        mode = mgr.get_mode("general")

        assert mode is not None
        assert mode.tools_enabled_default is True

    def test_tools_enabled_false_loaded_from_modes_json(self, tmp_path: Path) -> None:
        """When modes.json entry has 'tools_enabled': false, default is False."""
        modes = [
            {
                "id": "chat",
                "label": "Chat",
                "eyebrow": "Direct conversation",
                "file": "chat.md",
                "tools_enabled": False,
            }
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "")
        _write(tmp_path, "chat.md", "You are a conversational assistant.")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        mode = mgr.get_mode("chat")

        assert mode is not None
        assert mode.tools_enabled_default is False

    def test_tools_enabled_true_explicit_in_modes_json(self, tmp_path: Path) -> None:
        """Explicitly setting 'tools_enabled': true keeps the flag True."""
        modes = [
            {
                "id": "design",
                "label": "Design",
                "eyebrow": "Layout",
                "file": "design.md",
                "tools_enabled": True,
            }
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "")
        _write(tmp_path, "design.md", "Layout mode.")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        mode = mgr.get_mode("design")

        assert mode is not None
        assert mode.tools_enabled_default is True

    def test_get_all_modes_includes_tools_enabled_default(self, tmp_path: Path) -> None:
        """get_all_modes() metadata dicts must include the tools_enabled_default."""
        modes = [
            {"id": "general", "label": "General", "eyebrow": "Help", "file": "general.md"},
            {
                "id": "chat",
                "label": "Chat",
                "eyebrow": "Direct",
                "file": "chat.md",
                "tools_enabled": False,
            },
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "")
        _write(tmp_path, "general.md", "g")
        _write(tmp_path, "chat.md", "c")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        all_modes = mgr.get_all_modes()

        by_id = {m["id"]: m for m in all_modes}
        assert by_id["general"]["tools_enabled_default"] is True
        assert by_id["chat"]["tools_enabled_default"] is False

    def test_tools_enabled_non_bool_treated_as_true(self, tmp_path: Path) -> None:
        """A non-bool value for tools_enabled is coerced to True (safe default)."""
        modes = [
            {
                "id": "weird",
                "label": "Weird",
                "eyebrow": "x",
                "file": "weird.md",
                "tools_enabled": "yes",        # invalid type
            }
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "")
        _write(tmp_path, "weird.md", "w")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        mode = mgr.get_mode("weird")

        assert mode is not None
        assert mode.tools_enabled_default is True


# ===========================================================================
# 2. ChatService — use_tools threaded to agent
# ===========================================================================

@pytest.fixture
def repo(tmp_path: Path) -> SQLiteSessionRepository:
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    return SQLiteSessionRepository(conn)


class TestChatServiceToolsFlag:
    """ChatService must forward the effective use_tools flag to process_chat_turn."""

    def test_use_tools_true_by_default(
        self,
        repo: SQLiteSessionRepository,
    ) -> None:
        """When use_tools is omitted, FakeOrchestrator receives use_tools=True."""
        orchestrator = FakeOrchestrator()
        svc = ChatService(
            session_repo=repo,
            turn_orchestrator=orchestrator,
        )

        svc.handle_turn(ChatTurnRequest(session_id="s1", user_message="hello"))

        assert orchestrator.last_turn_input is not None
        assert orchestrator.last_turn_input.use_tools is True

    def test_use_tools_false_forwarded(
        self,
        repo: SQLiteSessionRepository,
    ) -> None:
        """When use_tools=False is passed, FakeOrchestrator receives use_tools=False."""
        orchestrator = FakeOrchestrator()
        svc = ChatService(
            session_repo=repo,
            turn_orchestrator=orchestrator,
        )

        svc.handle_turn(ChatTurnRequest(session_id="s2", user_message="tell me a joke", use_tools=False))

        assert orchestrator.last_turn_input is not None
        assert orchestrator.last_turn_input.use_tools is False

    def test_use_tools_false_returns_empty_tool_logs(
        self,
        repo: SQLiteSessionRepository,
    ) -> None:
        """A no-tools turn must always produce an empty tool_logs list."""
        orchestrator = FakeOrchestrator(text="direct reply")
        svc = ChatService(
            session_repo=repo,
            turn_orchestrator=orchestrator,
        )

        r = svc.handle_turn(ChatTurnRequest(session_id="s3", user_message="quick question", use_tools=False))
        text, tool_logs = r.assistant_message, r.tool_calls_made

        assert text == "direct reply"
        assert tool_logs == []

    def test_use_tools_false_stored_in_ui_history(
        self,
        repo: SQLiteSessionRepository,
    ) -> None:
        """The assistant ui_message must record tools=[] when no tools were used."""
        orchestrator = FakeOrchestrator(text="chat reply")
        svc = ChatService(
            session_repo=repo,
            turn_orchestrator=orchestrator,
        )

        svc.handle_turn(ChatTurnRequest(session_id="s4", user_message="just chat", use_tools=False))

        _, ui_json, _ = repo.load_session("s4")
        ui = json.loads(ui_json)
        assistant_msg = ui[1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["tools"] == []


# ===========================================================================
# 3. POST /api/chat — serialisation and route handler
# ===========================================================================

class TestChatEndpointToolsEnabled:
    """The HTTP endpoint must accept and forward tools_enabled."""

    def _make_capture_svc(self) -> tuple[MagicMock, callable]:
        """Returns (mock_svc, override_factory) for dependency injection."""
        mock_svc = MagicMock()
        mock_svc.handle_turn.return_value = ChatTurnResponse(session_id="test-session", assistant_message="ok", ui_history=[], user_turn_id="test-user-id", assistant_turn_id="test-assistant-id", tool_calls_made=[])

        def override():
            return mock_svc

        return mock_svc, override

    def test_tools_enabled_true_default_in_schema(self) -> None:
        """ChatRequest must default tools_enabled to True."""
        from src.schemas import ChatRequest
        req = ChatRequest(session_id="x", message="hello")
        assert req.tools_enabled is True

    def test_tools_enabled_false_accepted_in_schema(self) -> None:
        """ChatRequest must accept tools_enabled=False."""
        from src.schemas import ChatRequest
        req = ChatRequest(session_id="x", message="hello", tools_enabled=False)
        assert req.tools_enabled is False

    def test_endpoint_passes_tools_enabled_true_to_service(self, tmp_path: Path) -> None:
        """When tools_enabled is omitted (defaults True), service receives use_tools=True."""
        mock_svc, override = self._make_capture_svc()

        try:
            app.dependency_overrides[get_chat_service] = override
            resp = TestClient(app).post("/api/chat", json={
                "session_id": "sess-a",
                "message": "hello",
            })
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_chat_service, None)

        req = mock_svc.handle_turn.call_args[0][0]
        assert req.use_tools is True

    def test_endpoint_passes_tools_enabled_false_to_service(self, tmp_path: Path) -> None:
        """When tools_enabled=False is sent, service receives use_tools=False."""
        mock_svc, override = self._make_capture_svc()

        try:
            app.dependency_overrides[get_chat_service] = override
            resp = TestClient(app).post("/api/chat", json={
                "session_id": "sess-b",
                "message": "just chat",
                "tools_enabled": False,
            })
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_chat_service, None)

        req = mock_svc.handle_turn.call_args[0][0]
        assert req.use_tools is False

    def test_endpoint_tools_enabled_false_response_has_empty_tool_logs(self) -> None:
        """Response tools_used must be [] when the agent returns no tool logs."""
        mock_svc, override = self._make_capture_svc()

        try:
            app.dependency_overrides[get_chat_service] = override
            resp = TestClient(app).post("/api/chat", json={
                "session_id": "sess-c",
                "message": "no tools please",
                "tools_enabled": False,
            })
            body = resp.json()
        finally:
            app.dependency_overrides.pop(get_chat_service, None)

        assert body["tools_used"] == []


# ===========================================================================

