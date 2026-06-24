"""
tests/unit/services/test_import_service.py
===========================================
Unit tests for ImportService — the business-logic layer for importing
chat sessions from external JSON files.

All external I/O (DB) is mocked so these tests run instantly.
"""

import json
from unittest.mock import MagicMock, call

import pytest

from src.import_service import ImportService
from src.schemas import ImportMessage, ImportRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_repo() -> MagicMock:
    """Mock SessionRepository."""
    repo = MagicMock()
    repo.save_session = MagicMock()
    return repo


@pytest.fixture
def mock_token_counter() -> MagicMock:
    """Mock TokenCounterProtocol."""
    counter = MagicMock()
    counter.count = MagicMock(side_effect=lambda text: len(text.split()))
    return counter


@pytest.fixture
def service(mock_repo: MagicMock, mock_token_counter: MagicMock) -> ImportService:
    """ImportService with mocked dependencies."""
    return ImportService(session_repo=mock_repo, token_counter=mock_token_counter)


# ---------------------------------------------------------------------------
# ImportService.import_chat
# ---------------------------------------------------------------------------

class TestImportChat:
    """Test the main import_chat method."""

    def test_returns_import_response(self, service: ImportService) -> None:
        """Import returns ImportResponse with expected fields."""
        request = ImportRequest(
            messages=[
                ImportMessage(role="user", content="Hello"),
                ImportMessage(role="assistant", content="Hi there!"),
            ]
        )
        result = service.import_chat(request)

        assert result.session_id is not None
        assert len(result.session_id) > 0
        assert result.title == "Hello"
        assert result.message_count == 2
        assert result.turn_count == 2

    def test_auto_generates_title_from_first_user_message(
        self, service: ImportService
    ) -> None:
        """Title is derived from first user message when not provided."""
        request = ImportRequest(
            messages=[
                ImportMessage(role="user", content="How to design a kitchen?"),
                ImportMessage(role="assistant", content="Here are tips..."),
            ]
        )
        result = service.import_chat(request)
        assert result.title == "How to design a kitchen?"

    def test_uses_provided_title_when_given(self, service: ImportService) -> None:
        """Explicit title is used instead of auto-generation."""
        request = ImportRequest(
            title="My Custom Title",
            messages=[
                ImportMessage(role="user", content="Hello"),
                ImportMessage(role="assistant", content="Hi!"),
            ]
        )
        result = service.import_chat(request)
        assert result.title == "My Custom Title"

    def test_persists_to_repository(self, service: ImportService, mock_repo: MagicMock) -> None:
        """Session is saved to repository with correct parameters."""
        request = ImportRequest(
            title="Test Session",
            messages=[
                ImportMessage(role="user", content="Hello"),
                ImportMessage(role="assistant", content="Hi!"),
            ],
            system_prompt="You are a helpful assistant.",
        )
        result = service.import_chat(request)

        mock_repo.save_session.assert_called_once()
        call_args = mock_repo.save_session.call_args

        assert call_args.kwargs["session_id"] == result.session_id
        assert call_args.kwargs["title"] == "Test Session"
        assert call_args.kwargs["system_prompt"] == "You are a helpful assistant."

    def test_empty_messages_raises_error(self, service: ImportService) -> None:
        """Empty messages list raises ValueError."""
        request = ImportRequest(messages=[])
        with pytest.raises(ValueError, match="Messages list cannot be empty"):
            service.import_chat(request)

    def test_session_id_is_unique_uuid(self, service: ImportService) -> None:
        """Each import generates a unique UUID session ID."""
        request = ImportRequest(
            messages=[ImportMessage(role="user", content="Hello")]
        )
        result1 = service.import_chat(request)
        result2 = service.import_chat(request)

        assert result1.session_id != result2.session_id
        assert len(result1.session_id) == 36  # UUID format

    def test_system_prompt_persisted(self, service: ImportService, mock_repo: MagicMock) -> None:
        """System prompt is passed to repository."""
        request = ImportRequest(
            messages=[ImportMessage(role="user", content="Hello")],
            system_prompt="Custom system prompt",
        )
        service.import_chat(request)

        call_args = mock_repo.save_session.call_args
        assert call_args.kwargs["system_prompt"] == "Custom system prompt"

    def test_null_system_prompt_when_absent(
        self, service: ImportService, mock_repo: MagicMock
    ) -> None:
        """System prompt is None when not provided."""
        request = ImportRequest(
            messages=[ImportMessage(role="user", content="Hello")]
        )
        service.import_chat(request)

        call_args = mock_repo.save_session.call_args
        assert call_args.kwargs["system_prompt"] is None


# ---------------------------------------------------------------------------
# ImportService._build_histories
# ---------------------------------------------------------------------------

class TestBuildHistories:
    """Test the internal _build_histories method."""

    def test_api_history_has_required_fields(self, service: ImportService) -> None:
        """API history items contain role, content, turn_id."""
        messages = [
            ImportMessage(role="user", content="Hello"),
            ImportMessage(role="assistant", content="Hi!"),
        ]
        api_history, _ = service._build_histories(messages)

        for item in api_history:
            assert "role" in item
            assert "content" in item
            assert "turn_id" in item

    def test_ui_history_has_metadata_fields(self, service: ImportService) -> None:
        """UI history items contain provider, model, token_count."""
        messages = [
            ImportMessage(role="user", content="Hello", provider="openai", model="gpt-4"),
        ]
        _, ui_history = service._build_histories(messages)

        item = ui_history[0]
        assert item["provider"] == "openai"
        assert item["model"] == "gpt-4"
        assert "token_count" in item

    def test_turn_ids_are_unique(self, service: ImportService) -> None:
        """Each message gets a unique turn_id."""
        messages = [
            ImportMessage(role="user", content="First"),
            ImportMessage(role="assistant", content="Second"),
            ImportMessage(role="user", content="Third"),
        ]
        api_history, _ = service._build_histories(messages)

        turn_ids = [item["turn_id"] for item in api_history]
        assert len(turn_ids) == len(set(turn_ids))

    def test_turn_ids_match_between_histories(self, service: ImportService) -> None:
        """API and UI histories have matching turn_ids for same message."""
        messages = [
            ImportMessage(role="user", content="Hello"),
            ImportMessage(role="assistant", content="Hi!"),
        ]
        api_history, ui_history = service._build_histories(messages)

        for api_item, ui_item in zip(api_history, ui_history):
            assert api_item["turn_id"] == ui_item["turn_id"]

    def test_default_provider_when_missing(self, service: ImportService) -> None:
        """Provider defaults to 'imported' when not specified."""
        messages = [
            ImportMessage(role="user", content="Hello"),
        ]
        _, ui_history = service._build_histories(messages)

        assert ui_history[0]["provider"] == "imported"

    def test_default_model_when_missing(self, service: ImportService) -> None:
        """Model defaults to 'unknown' when not specified."""
        messages = [
            ImportMessage(role="user", content="Hello"),
        ]
        _, ui_history = service._build_histories(messages)

        assert ui_history[0]["model"] == "unknown"

    def test_token_count_called_for_each_message(
        self, service: ImportService, mock_token_counter: MagicMock
    ) -> None:
        """Token counter is called once per message."""
        messages = [
            ImportMessage(role="user", content="Hello"),
            ImportMessage(role="assistant", content="Hi there!"),
        ]
        service._build_histories(messages)

        assert mock_token_counter.count.call_count == 2

    def test_content_preserved_in_both_histories(self, service: ImportService) -> None:
        """Message content is identical in both histories."""
        messages = [
            ImportMessage(role="user", content="Test message with special chars: @#$%"),
        ]
        api_history, ui_history = service._build_histories(messages)

        assert api_history[0]["content"] == ui_history[0]["content"]
        assert api_history[0]["content"] == "Test message with special chars: @#$%"

    def test_role_preserved_in_both_histories(self, service: ImportService) -> None:
        """Message role is identical in both histories."""
        messages = [
            ImportMessage(role="user", content="Hello"),
            ImportMessage(role="assistant", content="Hi!"),
        ]
        api_history, ui_history = service._build_histories(messages)

        assert api_history[0]["role"] == "user"
        assert api_history[1]["role"] == "assistant"
        assert ui_history[0]["role"] == "user"
        assert ui_history[1]["role"] == "assistant"

    def test_no_tool_calls_in_api_history(self, service: ImportService) -> None:
        """API history does NOT contain tool_calls field."""
        messages = [
            ImportMessage(role="user", content="Hello"),
            ImportMessage(role="assistant", content="Hi!"),
        ]
        api_history, _ = service._build_histories(messages)

        for item in api_history:
            assert "tool_calls" not in item

    def test_json_serializable(self, service: ImportService) -> None:
        """Both histories are JSON serializable (required for DB storage)."""
        messages = [
            ImportMessage(role="user", content="Hello"),
            ImportMessage(role="assistant", content="Hi!"),
        ]
        api_history, ui_history = service._build_histories(messages)

        # Should not raise
        json.dumps(api_history)
        json.dumps(ui_history)


# ---------------------------------------------------------------------------
# ImportService._build_histories — edge cases
# ---------------------------------------------------------------------------

class TestBuildHistoriesEdgeCases:
    """Test edge cases in history building."""

    def test_single_user_message(self, service: ImportService) -> None:
        """Single user message without assistant response."""
        messages = [
            ImportMessage(role="user", content="Hello"),
        ]
        api_history, ui_history = service._build_histories(messages)

        assert len(api_history) == 1
        assert len(ui_history) == 1
        assert api_history[0]["role"] == "user"

    def test_single_assistant_message(self, service: ImportService) -> None:
        """Single assistant message (e.g., system-generated)."""
        messages = [
            ImportMessage(role="assistant", content="Welcome!"),
        ]
        api_history, ui_history = service._build_histories(messages)

        assert len(api_history) == 1
        assert api_history[0]["role"] == "assistant"

    def test_many_messages(self, service: ImportService) -> None:
        """Handles large number of messages."""
        messages = [
            ImportMessage(role="user" if i % 2 == 0 else "assistant", content=f"Msg {i}")
            for i in range(100)
        ]
        api_history, ui_history = service._build_histories(messages)

        assert len(api_history) == 100
        assert len(ui_history) == 100

    def test_unicode_content(self, service: ImportService) -> None:
        """Unicode content is preserved correctly."""
        messages = [
            ImportMessage(role="user", content="Kuchnie z klasą 🍳"),
            ImportMessage(role="assistant", content="Oto propozycje: 🎨"),
        ]
        api_history, ui_history = service._build_histories(messages)

        assert api_history[0]["content"] == "Kuchnie z klasą 🍳"
        assert api_history[1]["content"] == "Oto propozycje: 🎨"

    def test_multiline_content(self, service: ImportService) -> None:
        """Multiline content is preserved exactly."""
        content = "Line 1\nLine 2\nLine 3"
        messages = [
            ImportMessage(role="user", content=content),
        ]
        api_history, _ = service._build_histories(messages)

        assert api_history[0]["content"] == content

    def test_empty_content_allowed(self, service: ImportService) -> None:
        """Empty string content is allowed (not the same as missing)."""
        messages = [
            ImportMessage(role="user", content=""),
        ]
        api_history, ui_history = service._build_histories(messages)

        assert api_history[0]["content"] == ""
        assert ui_history[0]["content"] == ""

    def test_provider_model_per_message(self, service: ImportService) -> None:
        """Different messages can have different provider/model."""
        messages = [
            ImportMessage(role="user", content="Hello", provider="openai", model="gpt-4"),
            ImportMessage(role="assistant", content="Hi!", provider="anthropic", model="claude-3"),
        ]
        _, ui_history = service._build_histories(messages)

        assert ui_history[0]["provider"] == "openai"
        assert ui_history[0]["model"] == "gpt-4"
        assert ui_history[1]["provider"] == "anthropic"
        assert ui_history[1]["model"] == "claude-3"
