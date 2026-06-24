"""
src/folder_service.py
=====================
Business-logic layer for folder operations.

Sits between:
  - API layer (receives FolderCreateRequest/FolderUpdateRequest)
  - Repository layer (persists via FolderRepository)

Design:
  - Thin orchestrator with validation
  - Single responsibility: folder lifecycle
  - No direct DB access; delegates to repository
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.schemas import (
    FolderCreateRequest,
    FolderListResponse,
    FolderResponse,
    FolderUpdateRequest,
)

if TYPE_CHECKING:
    from src.repositories.folder_repo import SQLiteFolderRepository

logger = structlog.get_logger(__name__)


class FolderService:
    """
    Single responsibility: folder business logic.

    Validates input and delegates persistence to repository.
    """

    def __init__(self, folder_repo: SQLiteFolderRepository) -> None:
        self._repo = folder_repo

    def create_folder(self, request: FolderCreateRequest) -> FolderResponse:
        """
        Create a new folder.

        Args:
            request: Validated folder creation request.

        Returns:
            FolderResponse with created folder data.
        """
        logger.info("create_folder", name=request.name, parent_id=request.parent_id)

        result = self._repo.create_folder(
            name=request.name,
            color=request.color,
            icon=request.icon,
            parent_id=request.parent_id,
            order_index=0,
        )

        return FolderResponse(**result)

    def list_folders(self) -> FolderListResponse:
        """
        List all folders with session counts.

        Returns:
            FolderListResponse with all folders and total count.
        """
        folders = self._repo.list_folders()
        return FolderListResponse(
            folders=[FolderResponse(**f) for f in folders],
            total=len(folders),
        )

    def get_folder(self, folder_id: str) -> FolderResponse | None:
        """
        Get a single folder by ID.

        Args:
            folder_id: Folder UUID.

        Returns:
            FolderResponse or None if not found.
        """
        result = self._repo.get_folder(folder_id)
        if result is None:
            return None
        return FolderResponse(**result)

    def update_folder(
        self, folder_id: str, request: FolderUpdateRequest
    ) -> FolderResponse | None:
        """
        Update folder fields.

        Args:
            folder_id: Folder UUID.
            request: Fields to update (only non-None fields are applied).

        Returns:
            Updated FolderResponse or None if not found.
        """
        logger.info("update_folder", folder_id=folder_id, updates=request.model_dump(exclude_none=True))

        result = self._repo.update_folder(
            folder_id,
            name=request.name,
            color=request.color,
            icon=request.icon,
            order_index=request.order_index,
        )

        if result is None:
            return None

        return FolderResponse(**result)

    def delete_folder(self, folder_id: str) -> bool:
        """
        Delete a folder.

        Args:
            folder_id: Folder UUID.

        Returns:
            True if deleted, False if not found.
        """
        logger.info("delete_folder", folder_id=folder_id)
        return self._repo.delete_folder(folder_id)

    def reorder_folders(self, folder_ids: list[str]) -> int:
        """
        Reorder all folders by assigning order_index 0, 1, 2, … atomically.

        Args:
            folder_ids: Ordered list of folder UUIDs (new order).

        Returns:
            Number of folders reordered.
        """
        logger.info("reorder_folders", count=len(folder_ids))
        return self._repo.reorder_folders(folder_ids)

    def move_session(
        self, from_folder: str, to_folder: str, session_id: str
    ) -> bool:
        """
        Atomically move a session from one folder to another.

        Single transaction — no intermediate state where the session
        is in neither folder.

        Args:
            from_folder: Source folder UUID.
            to_folder: Target folder UUID.
            session_id: Session UUID.

        Returns:
            True on success, False if session not in source folder.
        """
        logger.info(
            "move_session",
            session_id=session_id,
            from_folder=from_folder,
            to_folder=to_folder,
        )
        return self._repo.move_session(from_folder, to_folder, session_id)

    def assign_session(self, folder_id: str, session_id: str) -> bool:
        """
        Assign a session to a folder.

        Args:
            folder_id: Folder UUID.
            session_id: Session UUID.

        Returns:
            True on success.
        """
        logger.info("assign_session", folder_id=folder_id, session_id=session_id)
        return self._repo.assign_session(folder_id, session_id)

    def unassign_session(self, folder_id: str, session_id: str) -> bool:
        """
        Remove session from folder.

        Args:
            folder_id: Folder UUID.
            session_id: Session UUID.

        Returns:
            True if removed, False if not assigned.
        """
        logger.info("unassign_session", folder_id=folder_id, session_id=session_id)
        return self._repo.unassign_session(folder_id, session_id)

    def get_folder_sessions(self, folder_id: str) -> list[dict]:
        """
        Get all sessions in a folder.

        Args:
            folder_id: Folder UUID.

        Returns:
            List of session dicts with id, title, updated_at.
        """
        return self._repo.get_folder_sessions(folder_id)

    # ── Tree Operations ─────────────────────────────────────────────────

    def assign_tree(
        self, folder_id: str, session_id: str, include_children: bool = False
    ) -> list[str]:
        """
        Assign session (and optionally children) to folder.

        Args:
            folder_id: Folder UUID.
            session_id: Session UUID.
            include_children: Whether to include all descendants.

        Returns:
            List of assigned session IDs.
        """
        logger.info(
            "assign_tree",
            folder_id=folder_id,
            session_id=session_id,
            include_children=include_children,
        )
        return self._repo.assign_tree(folder_id, session_id, include_children)

    def unassign_tree(
        self, folder_id: str, session_id: str, include_children: bool = False
    ) -> bool:
        """
        Remove session (and optionally children) from folder.

        Args:
            folder_id: Folder UUID.
            session_id: Session UUID.
            include_children: Whether to include all descendants.

        Returns:
            True if removed, False if not assigned.
        """
        logger.info(
            "unassign_tree",
            folder_id=folder_id,
            session_id=session_id,
            include_children=include_children,
        )
        result = self._repo.unassign_tree(folder_id, session_id, include_children)
        return len(result) > 0
