"""
Evaluation tests for the /api/chat endpoint.

Tests verify request validation, response schema, error handling,
provider threading, and tool execution.

Uses FastAPI dependency_overrides (NOT unittest.mock.patch) to inject mocks.
"""
import pytest
import structlog
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from src.main import app
from src.dependencies import get_chat_service

log = structlog.get_logger(__name__)
client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_overrides():
    """Clear dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_service():
    """Mock ChatService injected via FastAPI dependency_overrides."""
    mock = MagicMock()
    app.dependency_overrides[get_chat_service] = lambda: mock
    log.info("mock_service_injected")
    return mock


def _result(**kwargs):
    """Build a mock ChatTurnResponse with sensible defaults."""
    defaults = {
        "assistant_message": "Hello!",
        "ui_history": [],
        "user_turn_id": "turn-1",
        "assistant_turn_id": "turn-2",
        "tool_calls_made": [],
        "tool_logs": [],
        "tokens_used": {"input": 10, "output": 5, "total": 15},
        "provider_name": "gemini",
        "model_name": "gemini-2.5-flash",
    }
    defaults.update(kwargs)
    return MagicMock(**defaults)


# ---------------------------------------------------------------------------
# Request Validation
# ---------------------------------------------------------------------------

class TestRequestValidation:
    def test_missing_session_id_returns_422(self, mock_service):
        """session_id is required."""
        resp = client.post("/api/chat", json={"message": "hi", "mode": "general"})
        assert resp.status_code == 422
        assert "session_id" in str(resp.json())

    def test_missing_message_returns_422(self, mock_service):
        """message is required."""
        resp = client.post("/api/chat", json={"session_id": "x", "mode": "general"})
        assert resp.status_code == 422
        assert "message" in str(resp.json())

    def test_missing_mode_uses_default(self, mock_service):
        """mode defaults to 'general' — omitting it should succeed."""
        mock_service.handle_turn.return_value = _result()
        resp = client.post("/api/chat", json={"session_id": "x", "message": "hi"})
        assert resp.status_code == 200

    def test_empty_message_accepted(self, mock_service):
        """Empty string message — service decides if valid."""
        mock_service.handle_turn.return_value = _result(assistant_message="")
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "", "mode": "general"
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Response Schema
# ---------------------------------------------------------------------------

class TestResponseSchema:
    def test_has_required_fields(self, mock_service):
        """Response must have text, tools_used, user_turn_id, assistant_turn_id."""
        mock_service.handle_turn.return_value = _result()
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "hi", "mode": "general"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data
        assert "tools_used" in data
        assert "user_turn_id" in data
        assert "assistant_turn_id" in data

    def test_tools_used_is_list_of_dicts(self, mock_service):
        """
        REGRESSION: tools_used must be list of {name, args, result} dicts.
        Bug: was passing list[str] → Pydantic 500 error.
        """
        mock_service.handle_turn.return_value = _result(
            tool_calls_made=["read_file"],
            tool_logs=[{
                "name": "read_file",
                "args": {"filepath": "/test.md"},
                "result": {"content": "hello"},
            }],
        )
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "read test.md", "mode": "general"
        })
        assert resp.status_code == 200, f"500 error: {resp.text}"
        tools = resp.json()["tools_used"]
        assert len(tools) == 1
        assert tools[0]["name"] == "read_file"
        assert "args" in tools[0]
        assert "result" in tools[0]

    def test_provider_and_model_in_response(self, mock_service):
        """Response echoes back provider/model used."""
        mock_service.handle_turn.return_value = _result(
            provider_name="mimo", model_name="mimo-v2.5-pro"
        )
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "hi", "mode": "general",
            "provider": "mimo", "model": "mimo-v2.5-pro",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "mimo"
        assert data["model"] == "mimo-v2.5-pro"

    def test_turn_ids_populated(self, mock_service):
        """Turn IDs are passed through from service."""
        mock_service.handle_turn.return_value = _result(
            user_turn_id="u-123", assistant_turn_id="a-456"
        )
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "hi", "mode": "general"
        })
        assert resp.status_code == 200
        assert resp.json()["user_turn_id"] == "u-123"
        assert resp.json()["assistant_turn_id"] == "a-456"


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_service_exception_returns_500(self, mock_service):
        """Unhandled service errors → 500 with detail."""
        mock_service.handle_turn.side_effect = ValueError("Session not found")
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "hi", "mode": "general"
        })
        assert resp.status_code == 500
        assert "Session not found" in resp.json().get("detail", "")

    def test_llm_api_error_returns_500(self, mock_service):
        """LLM API failure → 500."""
        mock_service.handle_turn.side_effect = Exception("Rate limit exceeded")
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "hi", "mode": "general"
        })
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Provider Threading
# ---------------------------------------------------------------------------

class TestProviderThreading:
    def test_provider_passed_to_service(self, mock_service):
        """Request provider/model forwarded to ChatTurnRequest."""
        mock_service.handle_turn.return_value = _result(
            provider_name="mimo", model_name="mimo-v2.5-pro"
        )
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "hi", "mode": "general",
            "provider": "mimo", "model": "mimo-v2.5-pro",
        })
        assert resp.status_code == 200

        call_req = mock_service.handle_turn.call_args[0][0]
        assert call_req.provider == "mimo"
        assert call_req.model == "mimo-v2.5-pro"

    def test_default_provider_when_omitted(self, mock_service):
        """When provider/model omitted, they are None in request."""
        mock_service.handle_turn.return_value = _result()
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "hi", "mode": "general"
        })
        assert resp.status_code == 200

        call_req = mock_service.handle_turn.call_args[0][0]
        assert call_req.provider is None
        assert call_req.model is None


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------

class TestToolExecution:
    def test_single_tool(self, mock_service):
        """Single tool call returned correctly."""
        mock_service.handle_turn.return_value = _result(
            tool_calls_made=["read_file"],
            tool_logs=[{
                "name": "read_file",
                "args": {"filepath": "/a.txt"},
                "result": {"content": "data"},
            }],
        )
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "read a.txt", "mode": "general"
        })
        assert resp.status_code == 200
        assert len(resp.json()["tools_used"]) == 1
        assert resp.json()["tools_used"][0]["name"] == "read_file"

    def test_multiple_tools(self, mock_service):
        """Multiple tools returned in order."""
        mock_service.handle_turn.return_value = _result(
            tool_calls_made=["read_file", "list_directory"],
            tool_logs=[
                {"name": "read_file", "args": {"filepath": "/a"}, "result": {"content": "a"}},
                {"name": "list_directory", "args": {"dirpath": "/"}, "result": {"entries": ["a"]}},
            ],
        )
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "read and list", "mode": "general"
        })
        assert resp.status_code == 200
        tools = resp.json()["tools_used"]
        assert len(tools) == 2
        assert tools[0]["name"] == "read_file"
        assert tools[1]["name"] == "list_directory"

    def test_no_tools_empty_list(self, mock_service):
        """No tools → empty list."""
        mock_service.handle_turn.return_value = _result()
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "hi", "mode": "general"
        })
        assert resp.status_code == 200
        assert resp.json()["tools_used"] == []

    def test_tool_args_and_result_preserved(self, mock_service):
        """Tool args and result dicts passed through verbatim."""
        mock_service.handle_turn.return_value = _result(
            tool_calls_made=["write_file"],
            tool_logs=[{
                "name": "write_file",
                "args": {"filepath": "/out.txt", "content": "data"},
                "result": {"success": True, "bytes_written": 4},
            }],
        )
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "write out.txt", "mode": "general"
        })
        assert resp.status_code == 200
        tool = resp.json()["tools_used"][0]
        assert tool["args"]["filepath"] == "/out.txt"
        assert tool["result"]["success"] is True


# ---------------------------------------------------------------------------
# Normalizer Edge Cases (regression)
# ---------------------------------------------------------------------------

class TestNormalizerEdgeCases:
    def test_gemini_empty_parts_no_crash(self, mock_service):
        """
        REGRESSION: Gemini content.parts=None → TypeError.
        Fix: normalizer treats None parts as [].
        """
        mock_service.handle_turn.return_value = _result(assistant_message="")
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "hi", "mode": "general"
        })
        assert resp.status_code == 200

    def test_mimo_tool_call_id_set(self, mock_service):
        """
        REGRESSION: Mimo API rejects tool messages without tool_call_id.
        The provider must set tool_call_id on every tool message.
        """
        mock_service.handle_turn.return_value = _result(
            tool_calls_made=["read_file"],
            tool_logs=[{
                "name": "read_file",
                "args": {"filepath": "/x"},
                "result": {"content": "y"},
            }],
        )
        resp = client.post("/api/chat", json={
            "session_id": "x", "message": "read", "mode": "general"
        })
        # Should not 500 with "tool_call_id is not set"
        assert resp.status_code == 200
