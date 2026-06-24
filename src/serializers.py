"""
src/serializers.py
==================
Round-trip serialization for conversation history stored in SQLite.

**Provider-Agnostic Format (v2)**
---------------------------------
All messages are stored in a common OpenAI-compatible format:

    {"role": "user", "content": "Hello", "turn_id": "uuid"}
    {"role": "assistant", "content": "Hi!", "tool_calls": [...], "turn_id": "uuid"}
    {"role": "tool", "tool_call_id": "call_123", "content": "result", "turn_id": "uuid"}

This format is provider-agnostic — both Gemini and Anthropic providers
can consume it by converting to their native API format internally.

Every item carries a ``turn_id`` for stable identity (used by edit/delete).
"""

import json
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dehydrate_history(history: list, turn_ids: list[str] | None = None) -> str:
    """
    Convert a conversation history to a JSON string for DB storage.

    Accepts:
      - Common format dicts (pass through, turn_id ensured)
      - Gemini ``types.Content`` objects (convert to common format)

    Every item in the output is guaranteed to have a ``turn_id`` field.
    If an item already has one it is preserved; otherwise a UUID is generated.

    Args:
        history:  History list in any supported format.
        turn_ids: Optional parallel list of ``turn_id`` strings.  When provided,
                  used for items that don't already carry a ``turn_id``.

    Returns:
        JSON string of the dehydrated history in common format.
    """
    simple_list: list[dict] = []

    for idx, item in enumerate(history):
        turn_id: str | None = turn_ids[idx] if turn_ids is not None and idx < len(turn_ids) else None

        if isinstance(item, dict):
            # Already a dict — common format.  Ensure turn_id is present.
            if turn_id and "turn_id" not in item:
                item = {**item, "turn_id": turn_id}
            if "turn_id" not in item:
                item = {**item, "turn_id": str(uuid.uuid4())}
            simple_list.append(item)
        else:
            # Assume Gemini types.Content object — convert to common format
            try:
                from google.genai import types

                if isinstance(item, types.Content):
                    converted = _gemini_content_to_common(item, turn_id)
                    if converted is not None:
                        simple_list.append(converted)
                else:
                    logger.warning(
                        "dehydrate_history: skipping unknown item type %s",
                        type(item).__name__,
                    )
            except ImportError:
                logger.warning(
                    "dehydrate_history: skipping non-dict item (no Gemini SDK)",
                )

    return json.dumps(simple_list)


def _gemini_content_to_common(content: Any, turn_id: str | None) -> dict | None:
    """Convert Gemini types.Content to common format."""
    if not content.parts:
        return None

    role = content.role
    part = content.parts[0]

    # Preserve turn_id from the Content object if present (stamped by orchestrator)
    effective_turn_id = turn_id or getattr(content, "turn_id", None) or str(uuid.uuid4())

    if part.text is not None:
        msg: dict[str, Any] = {"role": role, "content": part.text}

    elif part.function_call is not None:
        msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": part.function_call.id or "",
                    "name": part.function_call.name,
                    "arguments": part.function_call.args or {},
                }
            ],
        }

    elif part.function_response is not None:
        msg = {
            "role": "tool",
            "tool_call_id": part.function_response.id or "",
            "content": json.dumps(part.function_response.response)
            if isinstance(part.function_response.response, dict)
            else str(part.function_response.response),
        }

    else:
        logger.warning("Skipping unrecognised Gemini part type")
        return None

    msg["turn_id"] = effective_turn_id
    return msg


def hydrate_history(json_string: str) -> list[dict]:
    """
    Rebuild a conversation history from a DB JSON string.

    Always returns a list of dicts in **common format**:
        {"role": "user"|"assistant"|"tool", "content": "...", ...}

    ``turn_id`` is preserved in the output for stable message identity.
    """
    if not json_string or json_string.strip() in ("", "[]"):
        return []

    return json.loads(json_string)
