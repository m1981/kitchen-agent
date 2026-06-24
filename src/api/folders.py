"""
api/folders.py
──────────────
Folder CRUD and session assignment endpoints.

Routes:
  POST   /api/folders                          → create folder
  GET    /api/folders                          → list all folders
  GET    /api/folders/{folder_id}              → get folder details
  PATCH  /api/folders/{folder_id}              → update folder
  DELETE /api/folders/{folder_id}              → delete folder
  POST   /api/folders/{folder_id}/sessions/{session_id}  → assign session
  DELETE /api/folders/{folder_id}/sessions/{session_id}  → unassign session
  GET    /api/folders/{folder_id}/sessions     → list folder sessions
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.dependencies import get_folder_service
from src.folder_service import FolderService
from src.schemas import (
    FolderAssignRequest,
    FolderCreateRequest,
    FolderListResponse,
    FolderMoveSessionRequest,
    FolderReorderRequest,
    FolderResponse,
    FolderUpdateRequest,
)

log = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/api/folders", response_model=FolderResponse, status_code=201)
async def create_folder(
    request: FolderCreateRequest,
    service: FolderService = Depends(get_folder_service),
) -> FolderResponse:
    """Create a new folder."""
    log.info("create_folder_request", name=request.name)

    try:
        result = service.create_folder(request)
        log.info("create_folder_success", folder_id=result.id)
        return result
    except Exception as e:
        log.error("create_folder_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create folder")


@router.get("/api/folders", response_model=FolderListResponse)
async def list_folders(
    service: FolderService = Depends(get_folder_service),
) -> FolderListResponse:
    """List all folders with session counts."""
    return service.list_folders()


@router.patch("/api/folders/reorder")
async def reorder_folders(
    request: FolderReorderRequest,
    service: FolderService = Depends(get_folder_service),
) -> dict:
    """Reorder folders. Assigns order_index 0, 1, 2, … atomically."""
    log.info("reorder_folders_request", count=len(request.folder_ids))

    count = service.reorder_folders(request.folder_ids)
    return {"reordered": True, "count": count}


@router.patch("/api/folders/move-session")
async def move_session(
    request: FolderMoveSessionRequest,
    service: FolderService = Depends(get_folder_service),
) -> dict:
    """Atomically move a session from one folder to another."""
    log.info(
        "move_session_request",
        session_id=request.session_id,
        from_folder=request.from_folder,
        to_folder=request.to_folder,
    )

    success = service.move_session(
        request.from_folder, request.to_folder, request.session_id
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Session not found in source folder",
        )

    return {
        "moved": True,
        "session_id": request.session_id,
        "from_folder": request.from_folder,
        "to_folder": request.to_folder,
    }


@router.get("/api/folders/{folder_id}", response_model=FolderResponse)
async def get_folder(
    folder_id: str,
    service: FolderService = Depends(get_folder_service),
) -> FolderResponse:
    """Get a single folder by ID."""
    result = service.get_folder(folder_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return result


@router.patch("/api/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: str,
    request: FolderUpdateRequest,
    service: FolderService = Depends(get_folder_service),
) -> FolderResponse:
    """Update folder fields."""
    log.info("update_folder_request", folder_id=folder_id)

    result = service.update_folder(folder_id, request)
    if result is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return result


@router.delete("/api/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: str,
    service: FolderService = Depends(get_folder_service),
) -> None:
    """Delete a folder."""
    log.info("delete_folder_request", folder_id=folder_id)

    success = service.delete_folder(folder_id)
    if not success:
        raise HTTPException(status_code=404, detail="Folder not found")


@router.post(
    "/api/folders/{folder_id}/sessions/{session_id}",
    status_code=201,
)
async def assign_session(
    folder_id: str,
    session_id: str,
    service: FolderService = Depends(get_folder_service),
) -> dict:
    """Assign a session to a folder."""
    log.info("assign_session_request", folder_id=folder_id, session_id=session_id)

    success = service.assign_session(folder_id, session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to assign session")

    return {"assigned": True, "folder_id": folder_id, "session_id": session_id}


@router.delete(
    "/api/folders/{folder_id}/sessions/{session_id}",
    status_code=204,
)
async def unassign_session(
    folder_id: str,
    session_id: str,
    service: FolderService = Depends(get_folder_service),
) -> None:
    """Remove session from folder."""
    log.info("unassign_session_request", folder_id=folder_id, session_id=session_id)

    success = service.unassign_session(folder_id, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not assigned to folder")


@router.get("/api/folders/{folder_id}/sessions")
async def get_folder_sessions(
    folder_id: str,
    service: FolderService = Depends(get_folder_service),
) -> list[dict]:
    """Get all sessions in a folder."""
    # Verify folder exists
    folder = service.get_folder(folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    return service.get_folder_sessions(folder_id)


# ── Tree Assignment ─────────────────────────────────────────────────────


class TreeAssignRequest(BaseModel):
    include_children: bool = False


@router.post(
    "/api/folders/{folder_id}/sessions/{session_id}/tree",
    status_code=201,
)
async def assign_session_tree(
    folder_id: str,
    session_id: str,
    request: TreeAssignRequest,
    service: FolderService = Depends(get_folder_service),
) -> dict:
    """Assign session (and optionally children) to folder."""
    log.info(
        "assign_session_tree_request",
        folder_id=folder_id,
        session_id=session_id,
        include_children=request.include_children,
    )

    try:
        assigned_ids = service.assign_tree(
            folder_id, session_id, request.include_children
        )
        return {
            "assigned": True,
            "folder_id": folder_id,
            "session_ids": assigned_ids,
            "count": len(assigned_ids),
        }
    except Exception as e:
        log.error("assign_session_tree_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to assign session tree")


@router.delete(
    "/api/folders/{folder_id}/sessions/{session_id}/tree",
    status_code=204,
)
async def unassign_session_tree(
    folder_id: str,
    session_id: str,
    request: TreeAssignRequest,
    service: FolderService = Depends(get_folder_service),
) -> None:
    """Remove session (and optionally children) from folder."""
    log.info(
        "unassign_session_tree_request",
        folder_id=folder_id,
        session_id=session_id,
        include_children=request.include_children,
    )

    success = service.unassign_tree(
        folder_id, session_id, request.include_children
    )
    if not success:
        raise HTTPException(status_code=404, detail="Session not assigned to folder")
