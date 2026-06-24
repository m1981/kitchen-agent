"""
src/title_generator.py
======================
Shared title derivation logic for session titles.

Used by:
  - ChatService (auto-title on first turn)
  - ImportService (auto-title for imported chats)

Single source of truth for title generation rules.
"""

from __future__ import annotations


def derive_title(messages: list[dict], max_len: int = 30) -> str:
    """
    Derive a session title from the first user message.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        max_len: Maximum character length before truncation (default 30).

    Returns:
        - First user message content, truncated to max_len + "..." if needed
        - "New Chat" if no user message found or list is empty
    """
    first_content = next(
        (m["content"] for m in messages if m.get("role") == "user" and "content" in m),
        "New Chat",
    )
    return first_content[:max_len] + "..." if len(first_content) > max_len else first_content
