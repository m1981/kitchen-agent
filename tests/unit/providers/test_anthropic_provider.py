"""
tests/test_anthropic_provider.py
=================================
Unit tests for AnthropicProvider — the LLMProvider interface.

Tests the provider's ``complete()`` and ``complete_with_tools()`` methods.
The agentic tool loop is tested separately in test_turn_orchestrator.py.

Covers:
  - Basic text completion via complete()
  - context_files injection
  - Images encoded as Anthropic image blocks
  - Bad base64 image skipped gracefully
  - System instruction forwarded
  - complete_with_tools() continues conversation
  - Tool schemas built from captured declarations
"""
import base64
from unittest.mock import MagicMock, patch

import pytest
import anthropic

from src.agent.context_assembler import AssembledContext, ContextSlot
from src.agent.tool_executor import ToolCall, ToolResult
from src.providers.anthropic_provider import AnthropicProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_block(text: str) -> MagicMock:
    block = MagicMock(spec=anthropic.types.TextBlock)
    block.type = "text"
    block.text = text
    return block


def _make_response(content_blocks: list, stop_reason: str = "end_turn") -> MagicMock:
    msg = MagicMock()
    msg.content = content_blocks
    msg.stop_reason = stop_reason
    text_parts = [b.text for b in content_blocks if getattr(b, "type", None) == "text"]
    msg.text = " ".join(text_parts) if text_parts else ""
    return msg


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
def provider() -> AnthropicProvider:
    """Return an AnthropicProvider with a mocked Anthropic client."""
    with patch("src.providers.anthropic_provider.anthropic.Anthropic") as mock_cls:
        p = AnthropicProvider()
        p._client = mock_cls.return_value
        return p


# ---------------------------------------------------------------------------
# Basic completion
# ---------------------------------------------------------------------------

def test_complete_returns_raw_response(provider: AnthropicProvider) -> None:
    """complete() returns the raw Anthropic SDK response."""
    resp = _make_response([_text_block("Hello from Claude!")])
    provider._client.messages.create.return_value = resp
    ctx = _make_context()

    response = provider.complete(ctx)

    assert response.text == "Hello from Claude!"
    provider._client.messages.create.assert_called_once()


def test_complete_uses_system_prompt(provider: AnthropicProvider) -> None:
    """System prompt from context is passed as the ``system`` parameter."""
    resp = _make_response([_text_block("ok")])
    provider._client.messages.create.return_value = resp
    ctx = _make_context(system_prompt="You are a kitchen expert.")

    provider.complete(ctx)

    call_kwargs = provider._client.messages.create.call_args[1]
    assert call_kwargs["system"] == "You are a kitchen expert."


def test_complete_null_system_prompt(provider: AnthropicProvider) -> None:
    """When system_prompt is empty, system kwarg should be None."""
    resp = _make_response([_text_block("ok")])
    provider._client.messages.create.return_value = resp
    ctx = _make_context(system_prompt="")

    provider.complete(ctx)

    call_kwargs = provider._client.messages.create.call_args[1]
    assert call_kwargs["system"] is None


# ---------------------------------------------------------------------------
# context_files injection
# ---------------------------------------------------------------------------

def test_context_files_injected_before_message(provider: AnthropicProvider) -> None:
    """Context file contents appear as a text block before the user message."""
    resp = _make_response([_text_block("noted")])
    provider._client.messages.create.return_value = resp
    ctx = _make_context(context_files=["data/materials.md"])

    with patch("src.providers.anthropic_provider.read_file", return_value={"content": "18mm Birch."}):
        provider.complete(ctx)

    call_kwargs = provider._client.messages.create.call_args[1]
    sent_messages = call_kwargs["messages"]
    user_msg = sent_messages[0]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    assert len(user_msg["content"]) >= 2
    context_block = user_msg["content"][0]
    assert context_block["type"] == "text"
    assert "[Context files injected by user]" in context_block["text"]
    assert "18mm Birch" in context_block["text"]


def test_unreadable_context_file_skipped(provider: AnthropicProvider) -> None:
    """Unreadable context files are silently skipped."""
    resp = _make_response([_text_block("ok")])
    provider._client.messages.create.return_value = resp
    ctx = _make_context(context_files=["missing.md"])

    with patch("src.providers.anthropic_provider.read_file", return_value={"error": "not found"}):
        provider.complete(ctx)

    provider._client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def test_valid_image_sent_as_base64_block(provider: AnthropicProvider) -> None:
    """A valid base64 image is added as an Anthropic image content block."""
    raw = b"\x89PNG\r\n"
    b64 = base64.b64encode(raw).decode()
    resp = _make_response([_text_block("saw it")])
    provider._client.messages.create.return_value = resp
    ctx = _make_context(images=[{"mime_type": "image/png", "data": b64}])

    provider.complete(ctx)

    call_kwargs = provider._client.messages.create.call_args[1]
    sent_messages = call_kwargs["messages"]
    user_msg = sent_messages[0]
    assert isinstance(user_msg["content"], list)
    image_blocks = [b for b in user_msg["content"] if b.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["type"] == "base64"
    assert image_blocks[0]["source"]["media_type"] == "image/png"
    assert image_blocks[0]["source"]["data"] == b64


def test_bad_base64_image_skipped(provider: AnthropicProvider) -> None:
    """Invalid base64 image is skipped without raising."""
    resp = _make_response([_text_block("ok")])
    provider._client.messages.create.return_value = resp
    ctx = _make_context(images=[{"mime_type": "image/png", "data": "!!!not_base64!!!"}])

    provider.complete(ctx)

    provider._client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# complete_with_tools
# ---------------------------------------------------------------------------

def test_complete_with_tools_continues_conversation(provider: AnthropicProvider) -> None:
    """complete_with_tools() appends tool result and calls API again."""
    # First call: complete() to set up conversation state
    resp1 = _make_response([_text_block("initial")])
    provider._client.messages.create.return_value = resp1
    ctx = _make_context()
    provider.complete(ctx)

    # Second call: complete_with_tools() with tool results
    resp2 = _make_response([_text_block("final answer")])
    provider._client.messages.create.return_value = resp2

    tool_calls = [ToolCall(id="tc1", name="read_file", arguments={"filepath": "x.md"})]
    tool_results = [ToolResult(tool_call_id="tc1", name="read_file", content="file content")]

    response = provider.complete_with_tools(ctx, tool_calls, tool_results)

    assert response.text == "final answer"
    # Verify conversation state has tool result
    assert len(provider._conversation_state) >= 2


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

def test_provider_uses_context_tool_schemas(provider: AnthropicProvider) -> None:
    """Provider must use context.tool_schemas from orchestrator, not build its own."""
    # The provider should not have _tool_schemas — schemas come from context
    assert not hasattr(provider, '_tool_schemas'), \
        "Provider should not build tool_schemas internally; use context.tool_schemas"


# ---------------------------------------------------------------------------
# Regression: turn_id must not leak to Anthropic API
# ---------------------------------------------------------------------------

def test_turn_id_stripped_from_messages(provider: AnthropicProvider) -> None:
    """
    Messages with turn_id, provider, model fields must be stripped
    before sending to Anthropic API.

    Regression test for: messages.0.turn_id: Extra inputs are not permitted
    """
    resp = _make_response([_text_block("ok")])
    provider._client.messages.create.return_value = resp

    # Context with messages containing extra fields (as stored in UI history)
    ctx = _make_context()
    ctx.messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there",
         "turn_id": "abc-123", "provider": "anthropic", "model": "claude-sonnet-4-6"},
        {"role": "user", "content": "Follow up"},
    ]

    provider.complete(ctx)

    # Verify the messages sent to Anthropic don't contain turn_id
    call_args = provider._client.messages.create.call_args
    messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
    for msg in messages:
        assert "turn_id" not in msg, f"turn_id leaked to API: {msg}"
        assert "provider" not in msg, f"provider leaked to API: {msg}"
        assert "model" not in msg, f"model leaked to API: {msg}"
