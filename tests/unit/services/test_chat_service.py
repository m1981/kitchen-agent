"""
tests/test_chat_service.py
==========================
Unit tests for ChatService — the business-logic layer between the HTTP
handler and the agent.

All external I/O (DB, agent, prompt logger) is mocked so these tests run
instantly without network or disk access.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from src.chat_service import ChatService, ChatTurnRequest, _make_title
from src.repositories import SQLiteConnection, SQLiteSessionRepository


# ---------------------------------------------------------------------------
# _make_title helper
# ---------------------------------------------------------------------------

def test_make_title_short_message() -> None:
    msgs = [{"role": "user", "content": "Hello"}]
    assert _make_title(msgs) == "Hello"


def test_make_title_long_message_truncated() -> None:
    msgs = [{"role": "user", "content": "A" * 40}]
    title = _make_title(msgs)
    assert title.endswith("...")
    assert len(title) == 33  # 30 chars + "..."


def test_make_title_no_user_message() -> None:
    msgs = [{"role": "assistant", "content": "Hi"}]
    assert _make_title(msgs) == "New Chat"


def test_make_title_empty_list() -> None:
    assert _make_title([]) == "New Chat"


# ---------------------------------------------------------------------------
# ChatService.handle_turn
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    return SQLiteSessionRepository(conn)


# ---------------------------------------------------------------------------
# ChatService with TurnOrchestrator
# ---------------------------------------------------------------------------

from tests.helpers import FakeOrchestrator
from src.agent.turn_orchestrator import ToolCallDetail


@pytest.fixture
def fake_orchestrator():
    return FakeOrchestrator()


@patch("src.chat_service.log_turn")
def test_handle_turn_saves_session(
    mock_log: MagicMock,
    fake_orchestrator: FakeOrchestrator,
    repo: SQLiteSessionRepository,
) -> None:
    """handle_turn should persist the session and return structured response."""
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=fake_orchestrator,
    )
    session_id = "test-orch-001"

    result = service.handle_turn(ChatTurnRequest(
        session_id=session_id,
        user_message="What hinges should I use?",
    ))

    assert result.assistant_message == "response text"
    assert result.tool_calls_made == []
    assert result.user_turn_id == "test-user-turn-id"
    assert result.assistant_turn_id == "test-assistant-turn-id"
    assert fake_orchestrator.run_call_count == 1

    # Verify session persisted
    _, ui_json, _ = repo.load_session(session_id)
    ui_messages = json.loads(ui_json)
    assert len(ui_messages) == 2
    assert ui_messages[0]["role"] == "user"
    assert ui_messages[0]["content"] == "What hinges should I use?"
    assert "turn_id" in ui_messages[0]
    assert ui_messages[1]["role"] == "assistant"
    assert ui_messages[1]["content"] == "response text"
    assert "turn_id" in ui_messages[1]


@patch("src.chat_service.log_turn")
def test_handle_turn_returns_turn_ids(
    mock_log: MagicMock,
    fake_orchestrator: FakeOrchestrator,
    repo: SQLiteSessionRepository,
) -> None:
    """handle_turn must return user_turn_id and assistant_turn_id from orchestrator."""
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=fake_orchestrator,
    )

    result = service.handle_turn(ChatTurnRequest(
        session_id="test-turn-ids",
        user_message="Hello",
    ))

    assert result.user_turn_id == "test-user-turn-id"
    assert result.assistant_turn_id == "test-assistant-turn-id"
    # Verify they are non-empty strings (valid UUIDs in production)
    assert len(result.user_turn_id) > 0
    assert len(result.assistant_turn_id) > 0


@patch("src.chat_service.log_turn")
def test_handle_turn_appends_to_history(
    mock_log: MagicMock,
    fake_orchestrator: FakeOrchestrator,
    repo: SQLiteSessionRepository,
) -> None:
    """Second turn must append to existing history."""
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=fake_orchestrator,
    )

    service.handle_turn(ChatTurnRequest(session_id="sess-orch-1", user_message="Turn 1"))

    fake_orchestrator._text = "Answer 2"
    service.handle_turn(ChatTurnRequest(session_id="sess-orch-1", user_message="Turn 2"))

    _, ui_json, _ = repo.load_session("sess-orch-1")
    ui_messages = json.loads(ui_json)
    assert len(ui_messages) == 4
    assert ui_messages[2]["content"] == "Turn 2"
    assert ui_messages[3]["content"] == "Answer 2"


@patch("src.chat_service.log_turn")
def test_handle_turn_passes_images_and_context(
    mock_log: MagicMock,
    repo: SQLiteSessionRepository,
) -> None:
    """Images and context_files must be forwarded to the orchestrator."""
    orchestrator = FakeOrchestrator()
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=orchestrator,
    )

    images = [{"mime_type": "image/png", "data": "abc123"}]
    context = ["/data/file.txt"]

    service.handle_turn(ChatTurnRequest(
        session_id="sess-orch-img",
        user_message="describe this",
        images=images,
        context_files=context,
    ))

    assert orchestrator.last_turn_input is not None
    assert orchestrator.last_turn_input.images == images
    assert orchestrator.last_turn_input.context_files == context


@patch("src.chat_service.log_turn")
def test_handle_turn_persists_tool_calls(
    mock_log: MagicMock,
    repo: SQLiteSessionRepository,
) -> None:
    """Tool calls from orchestrator must be persisted in history."""
    tool_details = [
        ToolCallDetail(
            id="call_1",
            name="read_file",
            arguments={"filepath": "/test.md"},
            result_content="file content here",
            is_error=False,
        )
    ]
    orchestrator = FakeOrchestrator(
        text="Based on the file, here is my answer.",
        tool_details=tool_details,
    )
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=orchestrator,
    )

    result = service.handle_turn(ChatTurnRequest(
        session_id="sess-orch-tools",
        user_message="Read the file",
    ))

    assert result.assistant_message == "Based on the file, here is my answer."
    assert len(result.tool_calls_made) == 1
    assert result.tool_calls_made[0] == "read_file"


@patch("src.chat_service.log_turn")
def test_handle_turn_logs_prompt(
    mock_log: MagicMock,
    fake_orchestrator: FakeOrchestrator,
    repo: SQLiteSessionRepository,
) -> None:
    """log_turn must be called."""
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=fake_orchestrator,
    )

    service.handle_turn(ChatTurnRequest(session_id="sess-orch-log", user_message="Log me"))

    assert mock_log.called
    _, kwargs = mock_log.call_args
    assert kwargs.get("user_message") == "Log me"
    assert kwargs.get("session_id") == "sess-orch-log"


@patch("src.chat_service.log_turn")
def test_use_tools_false_forwarded_to_orchestrator(
    mock_log: MagicMock,
    repo: SQLiteSessionRepository,
) -> None:
    """use_tools=False must be forwarded to TurnInput."""
    orchestrator = FakeOrchestrator()
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=orchestrator,
    )

    service.handle_turn(ChatTurnRequest(
        session_id="sess-no-tools",
        user_message="hello",
        use_tools=False,
    ))

    assert orchestrator.last_turn_input is not None
    assert orchestrator.last_turn_input.use_tools is False


# ---------------------------------------------------------------------------
# System prompt priority in _load_session
# ---------------------------------------------------------------------------

@pytest.fixture
def repo_for_priority(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    return SQLiteSessionRepository(conn)


@patch("src.chat_service.log_turn")
def test_load_session_uses_saved_prompt_when_request_is_none(
    mock_log: MagicMock,
    repo_for_priority: SQLiteSessionRepository,
) -> None:
    """When request.system_prompt is None, should use saved_system_prompt."""
    repo_for_priority.save_session(
        session_id="sess-priority",
        title="Test",
        api_history_json="[]",
        ui_history_json="[]",
        system_prompt="Saved override",
    )
    orchestrator = FakeOrchestrator()
    service = ChatService(session_repo=repo_for_priority, turn_orchestrator=orchestrator)

    service.handle_turn(ChatTurnRequest(
        session_id="sess-priority",
        user_message="hello",
        system_prompt=None,  # not provided
    ))

    # The orchestrator should receive the saved prompt
    assert orchestrator.last_turn_input is not None
    assert orchestrator.last_turn_input.system_prompt == "Saved override"


@patch("src.chat_service.log_turn")
def test_load_session_uses_request_prompt_over_saved(
    mock_log: MagicMock,
    repo_for_priority: SQLiteSessionRepository,
) -> None:
    """When request.system_prompt is provided, should use it over saved."""
    repo_for_priority.save_session(
        session_id="sess-priority-2",
        title="Test",
        api_history_json="[]",
        ui_history_json="[]",
        system_prompt="Saved override",
    )
    orchestrator = FakeOrchestrator()
    service = ChatService(session_repo=repo_for_priority, turn_orchestrator=orchestrator)

    service.handle_turn(ChatTurnRequest(
        session_id="sess-priority-2",
        user_message="hello",
        system_prompt="Request override",
    ))

    assert orchestrator.last_turn_input is not None
    assert orchestrator.last_turn_input.system_prompt == "Request override"


@patch("src.chat_service.log_turn")
def test_load_session_empty_string_clears_saved(
    mock_log: MagicMock,
    repo_for_priority: SQLiteSessionRepository,
) -> None:
    """When request.system_prompt is empty string, should clear (not use saved)."""
    repo_for_priority.save_session(
        session_id="sess-priority-3",
        title="Test",
        api_history_json="[]",
        ui_history_json="[]",
        system_prompt="Saved override",
    )
    orchestrator = FakeOrchestrator()
    service = ChatService(session_repo=repo_for_priority, turn_orchestrator=orchestrator)

    service.handle_turn(ChatTurnRequest(
        session_id="sess-priority-3",
        user_message="hello",
        system_prompt="",  # explicitly clear
    ))

    # Empty string means "clear override" - should NOT fall back to saved
    assert orchestrator.last_turn_input is not None
    assert orchestrator.last_turn_input.system_prompt == ""


@patch("src.chat_service.log_turn")
def test_load_session_none_when_no_saved(
    mock_log: MagicMock,
    repo_for_priority: SQLiteSessionRepository,
) -> None:
    """When no saved prompt and request is None, should be None."""
    orchestrator = FakeOrchestrator()
    service = ChatService(session_repo=repo_for_priority, turn_orchestrator=orchestrator)

    service.handle_turn(ChatTurnRequest(
        session_id="sess-new",
        user_message="hello",
        system_prompt=None,
    ))

    assert orchestrator.last_turn_input is not None
    assert orchestrator.last_turn_input.system_prompt is None


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

@patch("src.chat_service.log_turn")
def test_provider_forwarded_to_turn_input(
    mock_log: MagicMock,
    fake_orchestrator: FakeOrchestrator,
    repo: SQLiteSessionRepository,
) -> None:
    """provider from ChatTurnRequest must be forwarded to TurnInput."""
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=fake_orchestrator,
    )

    service.handle_turn(ChatTurnRequest(
        session_id="sess-provider",
        user_message="hello",
        provider="anthropic",
    ))

    assert fake_orchestrator.last_turn_input is not None
    assert fake_orchestrator.last_turn_input.provider == "anthropic"


@patch("src.chat_service.log_turn")
def test_model_forwarded_to_turn_input(
    mock_log: MagicMock,
    fake_orchestrator: FakeOrchestrator,
    repo: SQLiteSessionRepository,
) -> None:
    """model from ChatTurnRequest must be forwarded to TurnInput."""
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=fake_orchestrator,
    )

    service.handle_turn(ChatTurnRequest(
        session_id="sess-model",
        user_message="hello",
        provider="gemini",
        model="gemini-2.5-pro",
    ))

    assert fake_orchestrator.last_turn_input is not None
    assert fake_orchestrator.last_turn_input.provider == "gemini"
    assert fake_orchestrator.last_turn_input.model == "gemini-2.5-pro"


@patch("src.chat_service.log_turn")
def test_no_provider_uses_default(
    mock_log: MagicMock,
    fake_orchestrator: FakeOrchestrator,
    repo: SQLiteSessionRepository,
) -> None:
    """When provider is None, TurnInput.provider should be None (use default)."""
    service = ChatService(
        session_repo=repo,
        turn_orchestrator=fake_orchestrator,
    )

    service.handle_turn(ChatTurnRequest(
        session_id="sess-default",
        user_message="hello",
    ))

    assert fake_orchestrator.last_turn_input is not None
    assert fake_orchestrator.last_turn_input.provider is None
    assert fake_orchestrator.last_turn_input.model is None


# ---------------------------------------------------------------------------
# Provider/model in response
# ---------------------------------------------------------------------------

@patch("src.chat_service.log_turn")
def test_response_includes_provider_and_model(
    mock_log: MagicMock,
    repo: SQLiteSessionRepository,
) -> None:
    """ChatTurnResponse must include provider_name and model_name from orchestrator."""
    orchestrator = FakeOrchestrator(text="response")
    # Simulate what the real orchestrator does
    orchestrator._provider_name = "anthropic"
    orchestrator._model_name = "claude-sonnet-4-20250514"

    service = ChatService(
        session_repo=repo,
        turn_orchestrator=orchestrator,
    )

    # Monkey-patch the fake to return provider/model in TurnOutput
    original_run = orchestrator.run
    def patched_run(session, turn_input):
        output = original_run(session, turn_input)
        output.provider_name = turn_input.provider or "gemini"
        output.model_name = turn_input.model or "gemini-2.5-flash"
        return output
    orchestrator.run = patched_run

    result = service.handle_turn(ChatTurnRequest(
        session_id="sess-provider-resp",
        user_message="hello",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
    ))

    assert result.provider_name == "anthropic"
    assert result.model_name == "claude-sonnet-4-20250514"


@patch("src.chat_service.log_turn")
def test_ui_history_stores_provider_and_model(
    mock_log: MagicMock,
    repo: SQLiteSessionRepository,
) -> None:
    """Provider/model must be persisted in ui_history assistant message."""
    orchestrator = FakeOrchestrator(text="response")

    # Patch run to add provider/model to output
    original_run = orchestrator.run
    def patched_run(session, turn_input):
        output = original_run(session, turn_input)
        output.provider_name = "gemini"
        output.model_name = "gemini-2.5-pro"
        return output
    orchestrator.run = patched_run

    service = ChatService(
        session_repo=repo,
        turn_orchestrator=orchestrator,
    )

    service.handle_turn(ChatTurnRequest(
        session_id="sess-ui-model",
        user_message="hello",
    ))

    _, ui_json, _ = repo.load_session("sess-ui-model")
    ui_messages = json.loads(ui_json)
    assistant_msg = next(m for m in ui_messages if m["role"] == "assistant")

    assert assistant_msg["provider"] == "gemini"
    assert assistant_msg["model"] == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# ChatService.stream_turn
# ---------------------------------------------------------------------------

class TestStreamTurn:
    """Tests for ChatService.stream_turn() — streaming path."""

    @patch("src.chat_service.log_turn")
    def test_stream_turn_yields_text_delta(self, mock_log, repo):
        """stream_turn must yield text_delta events."""
        orchestrator = FakeOrchestrator(text="Hello!")
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        events = list(service.stream_turn(ChatTurnRequest(
            session_id="stream-001",
            user_message="Hi",
        )))

        text_events = [e for e in events if e["type"] == "text"]
        assert len(text_events) >= 1
        assert "Hello!" in text_events[0]["content"]

    @patch("src.chat_service.log_turn")
    def test_stream_turn_yields_done_event(self, mock_log, repo):
        """stream_turn must yield a done event at the end."""
        orchestrator = FakeOrchestrator(text="Response.")
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        events = list(service.stream_turn(ChatTurnRequest(
            session_id="stream-002",
            user_message="Hello",
        )))

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        assert done_events[0]["provider"] == "gemini"

    @patch("src.chat_service.log_turn")
    def test_stream_turn_persists_session(self, mock_log, repo):
        """stream_turn must persist the session after streaming."""
        orchestrator = FakeOrchestrator(text="Persisted.")
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        list(service.stream_turn(ChatTurnRequest(
            session_id="stream-003",
            user_message="Save me",
        )))

        _, ui_json, _ = repo.load_session("stream-003")
        ui_messages = json.loads(ui_json)
        assert len(ui_messages) == 2
        assert ui_messages[0]["role"] == "user"
        assert ui_messages[0]["content"] == "Save me"
        assert ui_messages[1]["role"] == "assistant"
        assert ui_messages[1]["content"] == "Persisted."

    @patch("src.chat_service.log_turn")
    def test_stream_turn_history_includes_tool_calls(self, mock_log, repo):
        """Fix #5: streaming history must include tool call/response pairs."""
        tool_details = [
            ToolCallDetail(
                id="call_1",
                name="read_file",
                arguments={"filepath": "/test.md"},
                result_content="file content",
                is_error=False,
            )
        ]
        orchestrator = FakeOrchestrator(
            text="Based on the file.",
            tool_details=tool_details,
        )
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        list(service.stream_turn(ChatTurnRequest(
            session_id="stream-tools",
            user_message="Read file",
        )))

        # Load the persisted API history
        api_json, _, _ = repo.load_session("stream-tools")
        from src.serializers import hydrate_history
        api_history = hydrate_history(api_json)

        # Must have: user, assistant(tool_call), tool(result), assistant(text)
        assert len(api_history) == 4
        assert api_history[0]["role"] == "user"
        assert api_history[1]["role"] == "assistant"
        assert "tool_calls" in api_history[1] or "content" in api_history[1]
        assert api_history[2]["role"] == "tool"
        assert api_history[3]["role"] == "assistant"
        assert api_history[3]["content"] == "Based on the file."

    @patch("src.chat_service.log_turn")
    def test_stream_turn_no_tools_has_flat_history(self, mock_log, repo):
        """Without tools, streaming history should be user + assistant."""
        orchestrator = FakeOrchestrator(text="Simple.", tool_details=[])
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        list(service.stream_turn(ChatTurnRequest(
            session_id="stream-simple",
            user_message="Hello",
        )))

        api_json, _, _ = repo.load_session("stream-simple")
        from src.serializers import hydrate_history
        api_history = hydrate_history(api_json)

        assert len(api_history) == 2
        assert api_history[0]["role"] == "user"
        assert api_history[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# ChatService token_breakdown tests
# ---------------------------------------------------------------------------

class TestTokenBreakdown:
    """Tests for token_breakdown in ChatTurnResponse."""

    @patch("src.chat_service.log_turn")
    def test_handle_turn_returns_token_breakdown(self, mock_log, repo):
        """handle_turn should return token_breakdown with all fields."""
        orchestrator = FakeOrchestrator(text="Response.")
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        result = service.handle_turn(ChatTurnRequest(
            session_id="test-breakdown",
            user_message="Hello",
        ))

        assert "user_message_tokens" in result.token_breakdown
        assert "tool_calls_tokens" in result.token_breakdown
        assert "tool_results_tokens" in result.token_breakdown
        assert "assistant_tokens" in result.token_breakdown
        assert "turn_total" in result.token_breakdown
        assert "conversation_total" in result.token_breakdown

    @patch("src.chat_service.log_turn")
    def test_handle_turn_token_counts_positive(self, mock_log, repo):
        """Token counts should be positive for non-empty messages."""
        orchestrator = FakeOrchestrator(text="Hello back!")
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        result = service.handle_turn(ChatTurnRequest(
            session_id="test-counts",
            user_message="Hello there",
        ))

        assert result.token_breakdown["user_message_tokens"] > 0
        assert result.token_breakdown["assistant_tokens"] > 0
        assert result.token_breakdown["turn_total"] > 0

    @patch("src.chat_service.log_turn")
    def test_ui_history_has_token_count(self, mock_log, repo):
        """UI history messages should have token_count field."""
        orchestrator = FakeOrchestrator(text="Response.")
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        result = service.handle_turn(ChatTurnRequest(
            session_id="test-ui-tokens",
            user_message="Hello",
        ))

        # Check UI history has token_count
        user_msg = next(m for m in result.ui_history if m["role"] == "user")
        assistant_msg = next(m for m in result.ui_history if m["role"] == "assistant")

        assert "token_count" in user_msg
        assert user_msg["token_count"] > 0
        assert "token_count" in assistant_msg
        assert assistant_msg["token_count"] > 0

    @patch("src.chat_service.log_turn")
    def test_conversation_total_accumulates(self, mock_log, repo):
        """conversation_total should grow across multiple turns."""
        orchestrator = FakeOrchestrator(text="Response.")
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        # First turn
        result1 = service.handle_turn(ChatTurnRequest(
            session_id="test-accum",
            user_message="First",
        ))
        total1 = result1.token_breakdown["conversation_total"]

        # Second turn
        result2 = service.handle_turn(ChatTurnRequest(
            session_id="test-accum",
            user_message="Second",
        ))
        total2 = result2.token_breakdown["conversation_total"]

        # Total should grow
        assert total2 > total1

    @patch("src.chat_service.log_turn")
    def test_stream_turn_returns_token_breakdown(self, mock_log, repo):
        """stream_turn done event should include token_breakdown."""
        orchestrator = FakeOrchestrator(text="Streamed.")
        service = ChatService(session_repo=repo, turn_orchestrator=orchestrator)

        events = list(service.stream_turn(ChatTurnRequest(
            session_id="test-stream-breakdown",
            user_message="Hello",
        )))

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        assert "token_breakdown" in done_events[0]
        assert done_events[0]["token_breakdown"]["user_message_tokens"] > 0
