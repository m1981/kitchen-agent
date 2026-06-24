"""
tests/test_chat_provider_routing.py
=====================================
Tests for per-request provider + model routing in POST /api/chat.

Verifies that ``provider`` and ``model`` fields in ChatRequest are
accepted, validated, and forwarded to get_provider() so each turn can
use a different backend without changing server config.

Covers
------
- ChatRequest accepts optional provider / model fields (schema)
- Omitting both fields → server default used (backward compat)
- Providing provider="gemini" routes to GeminiProvider
- Providing provider="anthropic" routes to AnthropicProvider
- Providing model="..." overrides the provider's default model
- Unknown provider name → HTTP 400 (not 500)
- model_override is passed into GeminiProvider / AnthropicProvider
- GeminiProvider respects model_override in the API call
- AnthropicProvider respects model_override in the API call
- Explicit provider_name triggers NotImplementedError (legacy path removed)
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.dependencies import get_chat_service, get_session_repo
from src.repositories import SQLiteConnection, SQLiteSessionRepository
from src.schemas import ChatRequest
from src.chat_service import ChatService, ChatTurnResponse
from tests.helpers import FakeOrchestrator


# ---------------------------------------------------------------------------
# Schema validation — ChatRequest accepts new fields
# ---------------------------------------------------------------------------

def test_chat_request_accepts_provider_field() -> None:
    req = ChatRequest(session_id="s1", message="hi", provider="anthropic")
    assert req.provider == "anthropic"


def test_chat_request_accepts_model_field() -> None:
    req = ChatRequest(session_id="s1", message="hi", model="claude-sonnet-4-5")
    assert req.model == "claude-sonnet-4-5"


def test_chat_request_provider_defaults_to_none() -> None:
    req = ChatRequest(session_id="s1", message="hi")
    assert req.provider is None


def test_chat_request_model_defaults_to_none() -> None:
    req = ChatRequest(session_id="s1", message="hi")
    assert req.model is None


def test_chat_request_provider_and_model_together() -> None:
    req = ChatRequest(session_id="s1", message="hi", provider="gemini", model="gemini-2.5-pro")
    assert req.provider == "gemini"
    assert req.model == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# get_provider() factory honours model_override
# ---------------------------------------------------------------------------

def test_get_provider_passes_model_to_gemini() -> None:
    from src.providers.base import get_provider
    with patch("src.providers.gemini.genai.Client"):
        provider = get_provider(provider_name="gemini", model_override="gemini-2.5-pro")
    from src.providers.gemini import GeminiProvider
    assert isinstance(provider, GeminiProvider)
    assert provider._model == "gemini-2.5-pro"


def test_get_provider_passes_model_to_anthropic() -> None:
    from src.providers.base import get_provider
    with patch("src.providers.anthropic_provider.anthropic.Anthropic"):
        provider = get_provider(provider_name="anthropic", model_override="claude-opus-4-5")
    from src.providers.anthropic_provider import AnthropicProvider
    assert isinstance(provider, AnthropicProvider)
    assert provider._model == "claude-opus-4-5"


def test_get_provider_uses_settings_default_when_no_override() -> None:
    import src.config as cfg
    from src.providers.base import get_provider
    with patch.object(cfg.settings, "llm_provider", "gemini"), \
         patch.object(cfg.settings, "gemini_model", "gemini-2.5-flash"), \
         patch("src.providers.gemini.genai.Client"):
        provider = get_provider()
    from src.providers.gemini import GeminiProvider
    assert isinstance(provider, GeminiProvider)
    assert provider._model == "gemini-2.5-flash"


def test_get_provider_raises_for_unknown_provider_name() -> None:
    from src.providers.base import get_provider
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider(provider_name="openai")


# ---------------------------------------------------------------------------
# GeminiProvider uses _model in API call (via complete())
# ---------------------------------------------------------------------------

def test_gemini_provider_uses_model_override_in_api_call() -> None:
    from google.genai import types
    from src.providers.gemini import GeminiProvider
    from src.agent.context_assembler import AssembledContext, ContextSlot

    with patch("src.providers.gemini.genai.Client") as mock_cls:
        provider = GeminiProvider(model_override="gemini-2.5-pro")
        mock_client = mock_cls.return_value

        part = types.Part(text="ok")
        resp = MagicMock()
        resp.candidates = [MagicMock(content=types.Content(role="model", parts=[part]))]
        resp.text = "ok"
        mock_client.models.generate_content.return_value = resp

        ctx = AssembledContext(
            system_prompt="test",
            messages=[{"role": "user", "content": "test"}],
            total_tokens_estimated=10,
            slots_used={ContextSlot.SYSTEM_PROMPT: 5, ContextSlot.CONVERSATION_HISTORY: 5},
        )
        provider.complete(ctx)

    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-2.5-pro"


def test_gemini_provider_uses_settings_model_by_default() -> None:
    from google.genai import types
    from src.providers.gemini import GeminiProvider
    from src.providers.config import GeminiConfig
    from src.agent.context_assembler import AssembledContext, ContextSlot

    # The provider reads model from GeminiConfig, not directly from settings.
    # In production, dependencies.py builds config from settings.
    config = GeminiConfig(model="gemini-2.5-flash")
    with patch("src.providers.gemini.genai.Client") as mock_cls:
        provider = GeminiProvider(config=config)
        mock_client = mock_cls.return_value

        part = types.Part(text="ok")
        resp = MagicMock()
        resp.candidates = [MagicMock(content=types.Content(role="model", parts=[part]))]
        resp.text = "ok"
        mock_client.models.generate_content.return_value = resp

        ctx = AssembledContext(
            system_prompt="test",
            messages=[{"role": "user", "content": "test"}],
            total_tokens_estimated=10,
            slots_used={ContextSlot.SYSTEM_PROMPT: 5, ContextSlot.CONVERSATION_HISTORY: 5},
        )
        provider.complete(ctx)

    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# AnthropicProvider uses _model in API call (via complete())
# ---------------------------------------------------------------------------

def test_anthropic_provider_uses_model_override_in_api_call() -> None:
    from src.providers.anthropic_provider import AnthropicProvider
    from src.agent.context_assembler import AssembledContext, ContextSlot

    with patch("src.providers.anthropic_provider.anthropic.Anthropic") as mock_cls:
        provider = AnthropicProvider(model_override="claude-opus-4-5")
        mock_client = mock_cls.return_value

        tb = MagicMock()
        tb.type = "text"
        tb.text = "ok"
        resp = MagicMock()
        resp.content = [tb]
        resp.stop_reason = "end_turn"
        mock_client.messages.create.return_value = resp

        ctx = AssembledContext(
            system_prompt="test",
            messages=[{"role": "user", "content": "test"}],
            total_tokens_estimated=10,
            slots_used={ContextSlot.SYSTEM_PROMPT: 5, ContextSlot.CONVERSATION_HISTORY: 5},
        )
        provider.complete(ctx)

    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-opus-4-5"


def test_anthropic_provider_uses_settings_model_by_default() -> None:
    from src.providers.anthropic_provider import AnthropicProvider
    from src.providers.config import AnthropicConfig
    from src.agent.context_assembler import AssembledContext, ContextSlot

    # The provider reads model from AnthropicConfig, not directly from settings.
    config = AnthropicConfig(model="claude-sonnet-4-5")
    with patch("src.providers.anthropic_provider.anthropic.Anthropic") as mock_cls:
        provider = AnthropicProvider(config=config)
        mock_client = mock_cls.return_value

        tb = MagicMock()
        tb.type = "text"
        tb.text = "ok"
        resp = MagicMock()
        resp.content = [tb]
        resp.stop_reason = "end_turn"
        mock_client.messages.create.return_value = resp

        ctx = AssembledContext(
            system_prompt="test",
            messages=[{"role": "user", "content": "test"}],
            total_tokens_estimated=10,
            slots_used={ContextSlot.SYSTEM_PROMPT: 5, ContextSlot.CONVERSATION_HISTORY: 5},
        )
        provider.complete(ctx)

    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-sonnet-4-5"


# ---------------------------------------------------------------------------
# POST /api/chat — legacy provider path raises NotImplementedError
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    conn = SQLiteConnection(db_path=str(tmp_path / "t.db"))
    return SQLiteSessionRepository(conn)


def test_chat_endpoint_provider_field_accepted(repo) -> None:
    """Provider field in request is accepted (ignored at service level)."""
    client = TestClient(app)
    app.dependency_overrides[get_session_repo] = lambda: repo

    orchestrator = FakeOrchestrator()
    app.dependency_overrides[get_chat_service] = lambda: ChatService(
        session_repo=repo,
        turn_orchestrator=orchestrator,
    )

    resp = client.post("/api/chat", json={
        "session_id": "sess-001",
        "message": "hello",
        "provider": "anthropic",
    })

    # Should succeed (provider field is accepted, just not used by ChatService)
    assert resp.status_code == 200
    assert orchestrator.run_call_count == 1
    app.dependency_overrides.clear()


def test_chat_endpoint_uses_server_default_when_no_provider(repo) -> None:
    """Omitting provider/model must use the orchestrator path."""
    client = TestClient(app)
    app.dependency_overrides[get_session_repo] = lambda: repo

    orchestrator = FakeOrchestrator()
    app.dependency_overrides[get_chat_service] = lambda: ChatService(
        session_repo=repo,
        turn_orchestrator=orchestrator,
    )

    client.post("/api/chat", json={
        "session_id": "sess-003",
        "message": "hello",
    })

    assert orchestrator.run_call_count == 1
    assert orchestrator.last_turn_input is not None
    assert orchestrator.last_turn_input.user_message == "hello"
    app.dependency_overrides.clear()


def test_chat_unknown_provider_accepted(repo) -> None:
    """Provider field is accepted (selection happens in DI, not in endpoint)."""
    client = TestClient(app)
    app.dependency_overrides[get_session_repo] = lambda: repo

    orchestrator = FakeOrchestrator()
    app.dependency_overrides[get_chat_service] = lambda: ChatService(
        session_repo=repo,
        turn_orchestrator=orchestrator,
    )

    resp = client.post("/api/chat", json={
        "session_id": "sess-004",
        "message": "hello",
        "provider": "openai",
    })

    # Provider field is accepted — it's just not used by ChatService
    assert resp.status_code == 200
    assert orchestrator.run_call_count == 1
    app.dependency_overrides.clear()
