"""
src/message_editor.py
=====================
Business-logic layer for chat message editing and deletion.

Every message carries a ``turn_id`` (stamped at write time by
``chat_service.py`` via the orchestrator).  All manipulation is:
  * ui_messages: filter/find by ``turn_id`` (O(n) scan, one field compare)
  * api_items:   filter by ``turn_id`` (O(n) scan, one field compare)

Public API
----------
  MessageEditService.edit_message(session_id, turn_id, new_content)
  MessageEditService.delete_message(session_id, turn_id, delete_pair)
  MessageEditService.truncate_turns(session_id, n)
  MessageEditService.update_system_prompt(session_id, system_prompt)
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from src.repositories import SessionRepository

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Domain exception
# ---------------------------------------------------------------------------

class EditError(Exception):
    """Raised when a message-editing operation cannot be completed."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_histories(
    repo: SessionRepository,
    session_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """
    Load and parse both histories + system prompt from the repository.

    Returns:
        (api_items, ui_messages, system_prompt)

    Raises:
        EditError: when the session does not exist.
    """
    api_json, ui_json, system_prompt = repo.load_session(session_id)

    # load_session returns ("[]", "[]", None) for unknown IDs.
    if api_json == "[]" and ui_json == "[]":
        sessions = repo.list_sessions(include_archived=True)
        if not any(s["id"] == session_id for s in sessions):
            raise EditError(f"Session not found: {session_id}")

    api_items: list[dict[str, Any]] = json.loads(api_json) if api_json else []
    ui_messages: list[dict[str, Any]] = json.loads(ui_json) if ui_json else []
    return api_items, ui_messages, system_prompt


def _save_histories(
    repo: SessionRepository,
    session_id: str,
    api_items: list[dict[str, Any]],
    ui_messages: list[dict[str, Any]],
    system_prompt: str | None,
) -> None:
    """Persist both histories back to the repository."""
    title = next(
        (m["content"][:30] + ("..." if len(m["content"]) > 30 else "")
         for m in ui_messages if m.get("role") == "user"),
        "Chat",
    )
    repo.save_session(
        session_id=session_id,
        title=title,
        api_history_json=json.dumps(api_items),
        ui_history_json=json.dumps(ui_messages),
        system_prompt=system_prompt,
    )


def _find_ui_by_turn_id(
    ui_messages: list[dict[str, Any]],
    turn_id: str,
) -> int:
    """
    Return the index of the ui_message whose ``turn_id`` matches.

    Raises:
        EditError: when no message with that turn_id exists.
    """
    for i, msg in enumerate(ui_messages):
        if msg.get("turn_id") == turn_id:
            return i
    raise EditError(f"No message found with turn_id={turn_id!r}.")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MessageEditService:
    """
    Manages editing and deletion of chat messages within a session.

    All methods are synchronous and safe to call from ``run_in_executor``.
    """

    def __init__(self, session_repo: SessionRepository) -> None:
        self._repo = session_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def edit_message(
        self,
        session_id: str,
        turn_id: str,
        new_content: str,
    ) -> None:
        """
        Replace the content of the message identified by ``turn_id``.

        Both ``ui_history`` and ``api_history`` are updated atomically.

        Args:
            session_id:  Target session UUID.
            turn_id:     Stable identity of the turn to edit.
            new_content: Replacement text (must be non-empty after strip).

        Raises:
            EditError: on validation failure, session not found, or turn not found.
        """
        if not new_content.strip():
            raise EditError("new_content must not be empty or blank.")

        api_items, ui_messages, system_prompt = _load_histories(self._repo, session_id)

        # ── Update UI layer ──────────────────────────────────────────────────
        ui_idx = _find_ui_by_turn_id(ui_messages, turn_id)
        ui_messages[ui_idx]["content"] = new_content

        # ── Sync API layer — update the text item(s) for this turn ───────────
        # Only the type="text" item carries the visible content; function_call
        # and function_response items are LLM-internal and not edited.
        for item in api_items:
            if item.get("turn_id") == turn_id and item.get("type") == "text":
                item["data"] = new_content
                break  # only one text item per turn

        _save_histories(self._repo, session_id, api_items, ui_messages, system_prompt)
        logger.info(
            "message_edited",
            session_id=session_id[:8],
            turn_id=turn_id[:8],
            preview=new_content[:40],
        )

    def delete_message(
        self,
        session_id: str,
        turn_id: str,
        delete_pair: bool = False,
    ) -> None:
        """
        Remove the message identified by ``turn_id``.

        When ``delete_pair=True`` and the targeted message is a user turn, the
        immediately following assistant message is also removed.

        Both ``ui_history`` and ``api_history`` are updated atomically.

        Args:
            session_id:   Target session UUID.
            turn_id:      Stable identity of the turn to delete.
            delete_pair:  Also remove the next message (if it exists).

        Raises:
            EditError: on session not found or turn not found.
        """
        api_items, ui_messages, system_prompt = _load_histories(self._repo, session_id)

        ui_idx = _find_ui_by_turn_id(ui_messages, turn_id)

        # Collect the turn_ids to remove from both layers.
        turn_ids_to_remove: set[str] = {turn_id}

        if delete_pair and ui_idx + 1 < len(ui_messages):
            next_turn_id = ui_messages[ui_idx + 1].get("turn_id")
            if next_turn_id:
                turn_ids_to_remove.add(next_turn_id)

        # ── Remove from ui_messages (high-to-low to keep indices stable) ─────
        indices_to_remove = sorted(
            [i for i, m in enumerate(ui_messages) if m.get("turn_id") in turn_ids_to_remove],
            reverse=True,
        )
        for i in indices_to_remove:
            ui_messages.pop(i)

        # ── Remove all api items belonging to those turn_ids ──────────────────
        api_items = [item for item in api_items if item.get("turn_id") not in turn_ids_to_remove]

        _save_histories(self._repo, session_id, api_items, ui_messages, system_prompt)
        logger.info(
            "message_deleted",
            session_id=session_id[:8],
            turn_id=turn_id[:8],
            delete_pair=delete_pair,
            turns_removed=len(turn_ids_to_remove),
        )

    def truncate_turns(
        self,
        session_id: str,
        n: int,
    ) -> None:
        """
        Remove the last ``n`` complete turn-pairs (user + assistant) from the tail.

        Raises:
            EditError: when ``n < 1``, session not found, or ``n`` exceeds
                       the available number of pairs.
        """
        if n < 1:
            raise EditError("n must be >= 1.")

        api_items, ui_messages, system_prompt = _load_histories(self._repo, session_id)

        total = len(ui_messages)
        items_to_remove = n * 2
        if items_to_remove > total:
            raise EditError(
                f"n={n} exceeds the number of available turn pairs "
                f"(session has {total} messages = {total // 2} complete pairs)."
            )

        first_ui_to_remove = total - items_to_remove
        tail_ui = ui_messages[first_ui_to_remove:]

        # Filter api_items by turn_ids from the tail.
        tail_turn_ids: set[str] = {m["turn_id"] for m in tail_ui if m.get("turn_id")}
        api_items = [item for item in api_items if item.get("turn_id") not in tail_turn_ids]

        del ui_messages[first_ui_to_remove:]

        _save_histories(self._repo, session_id, api_items, ui_messages, system_prompt)
        logger.info(
            "turns_truncated",
            session_id=session_id[:8],
            n=n,
            remaining_messages=len(ui_messages),
        )

    def get_system_prompt(self, session_id: str) -> str | None:
        """
        Return the current session-scoped system prompt override.

        Unlike ``_load_histories``, this method does **not** raise when the
        session row does not exist yet (brand-new chat, no messages sent).
        It simply returns ``None`` in that case.
        """
        _, _, system_prompt = self._repo.load_session(session_id)
        return system_prompt

    def update_system_prompt(
        self,
        session_id: str,
        system_prompt: str,
    ) -> None:
        """
        Overwrite the session-scoped system prompt stored in the DB.

        Safe to call on a brand-new session that has no messages yet — the
        session row is created (upserted) on the spot with empty histories.
        This allows users to set a prompt override before sending the first
        message, which is the common UX pattern.

        An empty string is valid (clears any override) so that the next turn
        falls back to the PromptManager default.
        """
        # Load existing data so we don't overwrite histories that already exist.
        # Do NOT use _load_histories here — it raises for unknown session IDs.
        # load_session returns safe defaults ("[]") for unknown IDs, and
        # save_session uses INSERT OR REPLACE so a new row is created if absent.
        api_json, ui_json, _ = self._repo.load_session(session_id)
        api_items: list[dict] = json.loads(api_json) if api_json else []
        ui_messages: list[dict] = json.loads(ui_json) if ui_json else []
        _save_histories(self._repo, session_id, api_items, ui_messages, system_prompt)
        logger.info(
            "system_prompt_updated",
            session_id=session_id[:8],
            chars=len(system_prompt),
        )
