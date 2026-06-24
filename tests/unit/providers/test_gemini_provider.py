"""
tests/test_gemini_provider.py
==============================
Unit tests for GeminiProvider — the LLMCompleter interface.

Tests the provider's ``complete()`` and ``complete_with_tools()`` methods.
The agentic tool loop is tested separately in test_turn_orchestrator.py.

Covers:
  - Basic text completion via complete()
  - context_files injection into user parts
  - Images base64-decoded and appended as Parts
  - Bad base64 image is skipped with a warning
  - complete_with_tools() continues conversation after tool results
"""
import base64
from unittest.mock import MagicMock, patch

import pytest
from google.genai import types

from src.agent.context_assembler import AssembledContext, ContextSlot
from src.agent.tool_executor import ToolCall, ToolResult
from src.providers.gemini import GeminiProvider


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_text_response(text: str) -> MagicMock:
    part = types.Part(text=text)
    mock = MagicMock()
    mock.candidates = [MagicMock(content=types.Content(role="model", parts=[part]))]
    mock.text = text
    mock.usage_metadata = MagicMock(
        prompt_token_count=10,
        candidates_token_count=5,
        total_token_count=15,
    )
    return mock


def _make_context(
    messages: list | None = None,
    system_prompt: str = "test system",
    images: list | None = None,
    context_files: list | None = None,
) -> AssembledContext:
    return AssembledContext(
        system_prompt=system_prompt,
        messages=messages or [{"role": "user", "content": "hello"}],
        total_tokens_estimated=10,
        slots_used={ContextSlot.SYSTEM_PROMPT: 5, ContextSlot.CONVERSATION_HISTORY: 5},
        images=images or [],
        context_files=context_files or [],
    )


@pytest.fixture
def provider() -> GeminiProvider:
    """Return a GeminiProvider with a mocked Gemini client."""
    with patch("src.providers.gemini.genai.Client") as mock_client_cls:
        p = GeminiProvider()
        p._client = mock_client_cls.return_value
        return p


# ---------------------------------------------------------------------------
# Basic completion
# ---------------------------------------------------------------------------

def test_complete_returns_raw_response(provider: GeminiProvider) -> None:
    """complete() returns the raw Gemini SDK response."""
    provider._client.models.generate_content.return_value = _make_text_response("Hello!")
    ctx = _make_context()

    response = provider.complete(ctx)

    assert response.text == "Hello!"
    provider._client.models.generate_content.assert_called_once()


def test_complete_uses_system_prompt(provider: GeminiProvider) -> None:
    """System prompt from context is passed to GenerateContentConfig."""
    provider._client.models.generate_content.return_value = _make_text_response("ok")
    ctx = _make_context(system_prompt="You are a kitchen expert.")

    provider.complete(ctx)

    call_kwargs = provider._client.models.generate_content.call_args[1]
    config = call_kwargs["config"]
    assert config.system_instruction == "You are a kitchen expert."


# ---------------------------------------------------------------------------
# context_files injection
# ---------------------------------------------------------------------------

def test_injects_context_files(provider: GeminiProvider) -> None:
    """Context file contents appear as a text part before the user message."""
    provider._client.models.generate_content.return_value = _make_text_response("noted")
    ctx = _make_context(context_files=["data/materials.md"])

    with patch("src.providers.gemini.read_file", return_value={"content": "# Materials\n18mm Birch."}):
        provider.complete(ctx)

    call_args = provider._client.models.generate_content.call_args
    contents = call_args[1]["contents"]
    # Find user Content with context injection
    user_contents = [c for c in contents if isinstance(c, types.Content) and c.role == "user"]
    assert len(user_contents) >= 1
    user_parts = user_contents[-1].parts
    texts = [p.text for p in user_parts if p.text]
    assert any("[Context files injected by user]" in t for t in texts)
    assert any("18mm Birch" in t for t in texts)


def test_skips_unreadable_context_file(provider: GeminiProvider) -> None:
    """Unreadable context files are silently skipped."""
    provider._client.models.generate_content.return_value = _make_text_response("ok")
    ctx = _make_context(context_files=["missing.md"])

    with patch("src.providers.gemini.read_file", return_value={"error": "File not found"}):
        provider.complete(ctx)

    # Should not raise — just skip the file
    provider._client.models.generate_content.assert_called_once()


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------

def test_decodes_valid_image(provider: GeminiProvider) -> None:
    """A valid base64 image is added as a Part."""
    raw = b"\x89PNG\r\n"
    b64 = base64.b64encode(raw).decode()
    provider._client.models.generate_content.return_value = _make_text_response("saw it")
    ctx = _make_context(images=[{"mime_type": "image/png", "data": b64}])

    provider.complete(ctx)

    call_args = provider._client.models.generate_content.call_args
    contents = call_args[1]["contents"]
    user_contents = [c for c in contents if isinstance(c, types.Content) and c.role == "user"]
    all_parts = [p for c in user_contents for p in c.parts]
    # Should have at least one inline_data part (image)
    image_parts = [p for p in all_parts if p.inline_data is not None]
    assert len(image_parts) >= 1


def test_skips_bad_base64_image(provider: GeminiProvider) -> None:
    """Invalid base64 image is skipped without raising."""
    provider._client.models.generate_content.return_value = _make_text_response("ok")
    ctx = _make_context(images=[{"mime_type": "image/png", "data": "!!!not_base64!!!"}])

    provider.complete(ctx)

    provider._client.models.generate_content.assert_called_once()


# ---------------------------------------------------------------------------
# complete_with_tools
# ---------------------------------------------------------------------------

def test_complete_with_tools_continues_conversation(provider: GeminiProvider) -> None:
    """complete_with_tools() appends tool call + result to conversation state."""
    # First call: complete() to set up conversation state
    provider._client.models.generate_content.return_value = _make_text_response("initial")
    ctx = _make_context()
    provider.complete(ctx)

    # Second call: complete_with_tools() with tool results
    provider._client.models.generate_content.return_value = _make_text_response("final answer")
    tool_calls = [ToolCall(id="tc1", name="read_file", arguments={"filepath": "x.md"})]
    tool_results = [ToolResult(tool_call_id="tc1", name="read_file", content="file content")]

    response = provider.complete_with_tools(ctx, tool_calls, tool_results)

    assert response.text == "final answer"
    # Verify conversation state has tool call and result
    assert len(provider._conversation_state) >= 3  # user + model(tool_call) + user(tool_result)
