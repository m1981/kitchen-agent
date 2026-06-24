"""
src/import_service.py
=====================
Business-logic layer for importing chat sessions from external JSON files.

Sits between:
  - API layer (receives ImportRequest)
  - Repository layer (persists via SessionRepository)
  - Token counter (estimates token counts)

Design decisions:
  - No tool calls in imported chats (plain text only)
  - Turn IDs are generated per message (not per pair) for consistency
  - Provider/model metadata stored in ui_history for frontend display
  - Title auto-generated from first user message if not provided
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import structlog

from src.schemas import ImportRequest, ImportResponse
from src.title_generator import derive_title

if TYPE_CHECKING:
    from src.protocols import TokenCounterProtocol
    from src.repositories import SessionRepository

logger = structlog.get_logger(__name__)


class ImportService:
    """
    Single responsibility: import external chat sessions.

    Constructs both history formats (api + ui) from flat message list.
    """

    def __init__(
        self,
        session_repo: SessionRepository,
        token_counter: TokenCounterProtocol,
    ) -> None:
        self._repo = session_repo
        self._counter = token_counter

    def import_chat(self, request: ImportRequest) -> ImportResponse:
        """
        Import a chat session from external JSON.

        Args:
            request: Validated import request with messages and optional metadata.

        Returns:
            ImportResponse with session_id, title, message_count, turn_count.

        Raises:
            ValueError: If messages list is empty.
        """
        if not request.messages:
            raise ValueError("Messages list cannot be empty.")

        # Build dual histories
        api_history, ui_history = self._build_histories(request.messages)

        # Derive title
        title = request.title or derive_title(ui_history)

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Persist
        self._repo.save_session(
            session_id=session_id,
            title=title,
            api_history_json=json.dumps(api_history),
            ui_history_json=json.dumps(ui_history),
            system_prompt=request.system_prompt,
        )

        logger.info(
            "import_chat completed",
            session_id=session_id,
            message_count=len(request.messages),
            turn_count=len(api_history),
        )

        return ImportResponse(
            session_id=session_id,
            title=title,
            message_count=len(request.messages),
            turn_count=len(api_history),
        )

    def _build_histories(
        self,
        messages: list,
    ) -> tuple[list[dict], list[dict]]:
        """
        Transform flat import messages into dual history format.

        Each message gets:
          - api_history item: {role, content, turn_id}
          - ui_history item: {role, content, turn_id, provider, model, token_count}

        Returns:
            Tuple of (api_history, ui_history) as lists of dicts.
        """
        api_history: list[dict] = []
        ui_history: list[dict] = []

        for msg in messages:
            turn_id = str(uuid.uuid4())
            content = msg.content
            role = msg.role

            # API history — provider-agnostic common format
            api_item = {
                "role": role,
                "content": content,
                "turn_id": turn_id,
            }
            api_history.append(api_item)

            # UI history — enriched with metadata for frontend
            token_count = self._counter.count(content)
            ui_item = {
                "role": role,
                "content": content,
                "turn_id": turn_id,
                "provider": msg.provider or "imported",
                "model": msg.model or "unknown",
                "token_count": token_count,
            }
            ui_history.append(ui_item)

        return api_history, ui_history
