"""
ExportService
─────────────
Owns all session export formatting.

Sits between the storage layer (SessionRepository, raw data)
and the formatting layer (exporter.py, pure functions).

This is the only place that:
  - Knows about both repositories and exporters
  - Decides what data to fetch for each export format
  - Calls exporter pure functions with that data

Callers (API routes, main.py) use ExportService.
They do NOT call repository export methods or exporter functions directly.
"""
from __future__ import annotations

import json
from typing import Any

from src.exporter import export_session_to_llm_json, export_session_to_markdown
from src.repositories import SessionRepository


class ExportService:
    """
    Single responsibility: format session data for export.

    Two formats supported:
      - Markdown: human-readable conversation log
      - LLM JSON: structured format for replaying with an LLM
    """

    def __init__(self, session_repo: SessionRepository) -> None:
        self._repo = session_repo

    def export_markdown(self, session_id: str) -> str:
        """
        Fetch session and render as markdown.
        Returns markdown string ready to write to file or return as response.
        """
        data = self._repo.get_export_data(session_id)
        ui_history: list[dict[str, Any]] = (
            json.loads(data["ui_history"]) if data["ui_history"] else []
        )
        return export_session_to_markdown(
            ui_messages=ui_history,
            title=data["title"] or session_id,
        )

    def export_llm_json(
        self,
        session_id: str,
        tool_schemas: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Fetch session and render as LLM-replayable JSON.

        Args:
            session_id:   Session to export.
            tool_schemas: Optional tool declarations to embed in config block.
                          Pass from ToolRegistry when available.
                          Omit for a schema-free export.
        """
        data = self._repo.get_export_data(session_id)
        api_history: list[dict[str, Any]] = (
            json.loads(data["api_history"]) if data["api_history"] else []
        )
        return export_session_to_llm_json(
            api_items=api_history,
            title=data["title"] or session_id,
            session_id=session_id,
            system_instruction=data["system_prompt"],
            tool_schemas=tool_schemas,
        )
