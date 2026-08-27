"""
src/message_format.py
=====================
Provider-agnostic message format for DB storage and inter-provider compatibility.

This module defines the **canonical message format** used throughout the system.
All providers convert FROM this format to their native API format, and convert
TO this format when returning results.

Format (OpenAI-compatible):
--------------------------
# User message
{"role": "user", "content": "Hello"}

# Assistant message (text only)
{"role": "assistant", "content": "Let me help..."}

# Assistant message with tool calls
{
    "role": "assistant",
    "content": "Let me search...",
    "tool_calls": [
        {"id": "call_123", "name": "search", "arguments": {"query": "..."},
         "thought_signature": "<base64>"}     # optional, Gemini 3 thinking models
    ]
}

# Tool response
{"role": "tool", "tool_call_id": "call_123", "content": "Found 5 results..."}

All messages may include an optional "turn_id" field for stable identity.
"""
from __future__ import annotations

import base64
from typing import Any, TypedDict


class ToolCallDict(TypedDict, total=False):
    id: str
    name: str
    arguments: dict[str, Any]
    # Opaque token a thinking model attaches to its function call.  Gemini 3
    # rejects a request (400 INVALID_ARGUMENT) that replays a function call
    # without it, so it has to survive JSON storage — hence base64 of the
    # raw bytes rather than the bytes themselves.
    thought_signature: str


def encode_thought_signature(signature: bytes | None) -> str | None:
    """SDK bytes → base64 str for JSON storage.  ``None`` passes through."""
    if not signature:
        return None
    if isinstance(signature, str):
        return signature
    return base64.b64encode(signature).decode("ascii")


def decode_thought_signature(signature: str | None) -> bytes | None:
    """base64 str → SDK bytes.  Malformed input is dropped, never raised."""
    if not signature:
        return None
    if isinstance(signature, bytes):
        return signature
    try:
        return base64.b64decode(signature, validate=True)
    except (ValueError, TypeError):
        return None


class MessageDict(TypedDict, total=False):
    role: str  # "user" | "assistant" | "tool"
    content: str | list[dict[str, Any]]  # text or structured content
    tool_calls: list[ToolCallDict]  # only for assistant messages
    tool_call_id: str  # only for tool messages
    turn_id: str  # optional stable identity
    token_count: int  # token count for this message


def make_user_message(content: str, turn_id: str | None = None) -> MessageDict:
    """Create a user message in common format."""
    msg: MessageDict = {"role": "user", "content": content}
    if turn_id:
        msg["turn_id"] = turn_id
    return msg


def make_assistant_message(
    content: str | list[dict[str, Any]],
    tool_calls: list[ToolCallDict] | None = None,
    turn_id: str | None = None,
) -> MessageDict:
    """Create an assistant message in common format."""
    msg: MessageDict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if turn_id:
        msg["turn_id"] = turn_id
    return msg


def make_tool_message(
    tool_call_id: str,
    content: str,
    turn_id: str | None = None,
) -> MessageDict:
    """Create a tool response message in common format."""
    msg: MessageDict = {"role": "tool", "tool_call_id": tool_call_id, "content": content}
    if turn_id:
        msg["turn_id"] = turn_id
    return msg
