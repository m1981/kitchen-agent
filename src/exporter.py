"""
src/exporter.py
===============
Export functions for chat sessions.

Three export formats are provided:

1. ``export_session_to_markdown`` — Human-readable Markdown.
   Uses ``ui_history_json`` (the pretty, tool-summarised UI representation).
   Suitable for archiving, sharing, or reading.

2. ``export_session_to_llm_json`` — LLM-context debug export.
   Uses ``api_history_json`` (the raw dehydrated ``Content`` objects) so you
   can see *exactly* what the model had in its context window, including
   ``thought_signature`` hex bytes, function call IDs, and every Part.

   F04 addition: a top-level ``"config"`` block is prepended BEFORE ``"turns"``
   containing the reconstructed ``GenerateContentConfig`` envelope:
     - model name          (from settings)
     - temperature         (from settings)
     - system_instruction  (persisted from ChatRequest.system_prompt)
     - tools / function_declarations  (from the live tool registry)

   Key order in output dict: ``metadata`` → ``config`` → ``turns``

   Suitable for debugging multi-turn tool-calling sessions.

Public surface
--------------
  build_config_block(system_instruction, tool_declarations)  → dict
  export_session_to_markdown(ui_messages, title)  → str
  export_session_to_llm_json(api_items, title, session_id, system_instruction, tool_schemas) → dict

Pure functions only — no DB or HTTP concerns.
"""

import json
from datetime import datetime, timezone
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# ── Format 1: Markdown export (unchanged) ─────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────


def _render_tool_call(tool: dict[str, Any]) -> str:
    """Renders a single tool invocation as a collapsible ``<details>`` block."""
    name = tool.get("name", "unknown")
    args_json = json.dumps(tool.get("args", {}), indent=2, ensure_ascii=False)
    result_json = json.dumps(tool.get("result", {}), indent=2, ensure_ascii=False)

    return (
        "<details>\n"
        f"<summary>🔧 Tool call: <code>{name}</code></summary>\n\n"
        "**Arguments:**\n\n"
        f"```json\n{args_json}\n```\n\n"
        "**Result:**\n\n"
        f"```json\n{result_json}\n```\n\n"
        "</details>"
    )


def _render_message(message: dict[str, Any]) -> str:
    """Renders a single UI message (user or assistant) as Markdown."""
    role = message.get("role", "unknown")
    content = message.get("content", "")

    if role == "user":
        return f"## User\n\n{content}"

    if role == "assistant":
        tool_blocks = [_render_tool_call(t) for t in (message.get("tools") or [])]
        parts = [f"## Assistant\n\n{content}", *tool_blocks]
        return "\n\n".join(parts)

    # Fallback for unknown roles (future-proofing).
    return f"## {role.capitalize()}\n\n{content}"


def export_session_to_markdown(
    ui_messages: list[dict[str, Any]],
    title: str,
) -> str:
    """
    Renders a chat session as a Markdown document.

    Args:
        ui_messages: List of UI-format messages (role / content / tools).
        title:       Session title used as the document ``# heading``.

    Returns:
        A Markdown string ending with a trailing newline.
    """
    safe_title = title.strip() or "Untitled Session"
    sections = [f"# {safe_title}", *(_render_message(m) for m in ui_messages)]
    return "\n\n".join(sections) + "\n"


# ──────────────────────────────────────────────────────────────────────────────
# ── Format 2: LLM-context debug export ────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────


def build_config_block(
    system_instruction: str | None,
    tool_declarations: list[Any] | None = None,
) -> dict[str, Any]:
    """
    Reconstructs the ``GenerateContentConfig`` envelope as a plain dict,
    exactly as it was sent to the Gemini API on every ``generate_content``
    call.

    Because ``GenerateContentConfig`` is a Pydantic model in the ``google-genai``
    SDK, we build a real instance and dump it via ``model_dump_json`` to get
    the canonical wire representation.  Only non-None fields are included,
    matching ``exclude_none=True`` semantics.

    Args:
        system_instruction:  The persisted system prompt for this session,
                             or ``None`` if no persona was active.
        tool_declarations:   Optional list of FunctionDeclaration objects.
                             When ``None``, falls back to the default
                             ToolRegistry via ``build_default_registry()``.

    Returns:
        A dict with keys: ``model``, ``temperature``, ``system_instruction``,
        ``tools``.  ``system_instruction`` is always present (may be ``None``).
    """
    # Import here to avoid circular dependency risks at module load time.
    # These imports are fast (already-imported modules, no I/O).
    from google.genai import types
    from src.config import settings

    if tool_declarations is not None:
        gemini_tools = types.Tool(function_declarations=tool_declarations)
    else:
        from src.tools.registry import build_default_registry
        registry = build_default_registry()
        schemas = registry.schemas_for_provider("gemini")
        gemini_tools = types.Tool(function_declarations=schemas)
    config = types.GenerateContentConfig(
        tools=[gemini_tools],
        temperature=settings.gemini_temperature,
        system_instruction=system_instruction,
    )

    # Dump via the SDK's own Pydantic serializer for maximum fidelity.
    # We then re-parse to a plain dict so no SDK types leak into the output.
    raw: dict[str, Any] = json.loads(config.model_dump_json(exclude_none=True))

    # Ensure the canonical structure: model name is not part of the config
    # object itself (it's passed separately to generate_content), so we
    # inject it explicitly for completeness.
    return {
        "model": settings.gemini_model,
        "temperature": raw.get("temperature", settings.gemini_temperature),
        # Always include system_instruction key — None makes the absence explicit.
        "system_instruction": raw.get("system_instruction", None),
        "tools": raw.get("tools", []),
    }


def _render_llm_part(item: dict[str, Any]) -> dict[str, Any]:
    """
    Converts a single dehydrated API-history item into a debug-friendly
    part dict that mirrors what the Gemini SDK sends to the model.

    Handles the four recognised types:
      - ``text``              → ``{type, text}``
      - ``function_call``     → ``{type, name, args, id, thought_signature_hex}``
      - ``function_response`` → ``{type, name, response, id}``
      - anything else         → ``{type: "unknown_part", raw: <original>}``
    """
    item_type = item.get("type")

    if item_type == "text":
        return {
            "type": "text",
            "text": item.get("data", ""),
        }

    if item_type == "function_call":
        return {
            "type": "function_call",
            "name": item.get("name"),
            "args": item.get("args"),
            "id": item.get("id"),
            # thought_signature is already stored as hex (or None) by the serializer
            "thought_signature_hex": item.get("signature"),
        }

    if item_type == "function_response":
        return {
            "type": "function_response",
            "name": item.get("name"),
            "response": item.get("response"),
            "id": item.get("id"),
        }

    # Unrecognised part — preserve raw data so nothing is silently dropped
    return {
        "type": "unknown_part",
        "raw": item,
    }


def _render_llm_turn(
    item: dict[str, Any],
    already_has_parts: bool = False,
) -> dict[str, Any]:
    """
    Converts a single dehydrated API-history item (or a pre-composed
    multi-part turn dict) into a turn dict suitable for the LLM debug export.

    Args:
        item:              A dehydrated item as stored in ``api_history_json``,
                           OR a dict with a ``"parts"`` key already populated
                           (multi-part turn, future-proofing path).
        already_has_parts: When ``True`` the caller supplies an item whose
                           ``"parts"`` key already holds a list of pre-rendered
                           part dicts.  The function wraps them unchanged under
                           the same role.

    Returns:
        ``{"role": str, "parts": [part_dict, ...]}``
    """
    role = item.get("role", "unknown")

    if already_has_parts:
        # Multi-part path: parts list was already built by the caller.
        return {
            "role": role,
            "parts": item.get("parts", []),
        }

    # Single-part path (current serializer stores one part per item).
    return {
        "role": role,
        "parts": [_render_llm_part(item)],
    }


def export_session_to_llm_json(
    api_items: list[dict[str, Any]],
    title: str,
    session_id: str,
    system_instruction: str | None = None,
    tool_schemas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Renders the complete LLM call context as a structured JSON document.

    Output structure (key order is canonical):
    ::

        {
          "metadata": {
            "session_id": "…",
            "title":      "…",
            "turn_count": N,
            "export_timestamp": "…"
          },
          "config": {
            "model":              "gemini-3.1-pro-preview",
            "temperature":        0.2,
            "system_instruction": "…" | null,
            "tools": [ { "function_declarations": [ … ] } ]
          },
          "turns": [ … ]
        }

    The ``config`` block is placed between ``metadata`` and ``turns`` so that
    when a developer reads the exported JSON top-to-bottom they first see the
    call envelope (what model, what tools, what system prompt) before the
    actual conversation turns — matching the mental model of how a Gemini API
    call is structured.

    Args:
        api_items:          Dehydrated Content dicts from ``api_history_json``.
        title:              Session title (for metadata block).
        session_id:         Session UUID (for metadata block).
        system_instruction: Persisted system prompt (``None`` if not set).

    Returns:
        Ordered dict with ``metadata``, ``config``, ``turns`` keys.
    """
    turns = [_render_llm_turn(item) for item in api_items]

    # Use an explicit insertion order to guarantee metadata → config → turns.
    result: dict[str, Any] = {}

    result["metadata"] = {
        "session_id": session_id,
        "title": title,
        "turn_count": len(turns),
        "export_timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    result["config"] = build_config_block(
        system_instruction=system_instruction,
        tool_declarations=tool_schemas,
    )

    result["turns"] = turns

    return result
