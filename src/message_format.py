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
        {"id": "call_123", "name": "search", "arguments": {"query": "..."}}
    ]
}

# Tool response
{"role": "tool", "tool_call_id": "call_123", "content": "Found 5 results..."}

All messages may include an optional "turn_id" field for stable identity.
"""
from __future__ import annotations

from typing import Any, TypedDict


class ToolCallDict(TypedDict, total=False):
    id: str
    name: str
    arguments: dict[str, Any]


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
