"""
api/files.py
────────────
File operation endpoints.

Routes:
  GET    /api/files              → list files in data/
  GET    /api/files/{path}       → read file content
  PUT    /api/files/{path}       → write file content
  POST   /api/files/append       → append to file
  POST   /api/files/revert/{id}  → revert a backup
  GET    /api/repo-map           → project tree
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.config import settings
from src.schemas import (
    FileAppendRequest,
    FileListItem,
    FileReadResponse,
    FileWriteRequest,
    RevertResponse,
)
from src.tools.file_ops import append_to_file, revert_backup
from src.tools.repo_map import get_repo_map

router = APIRouter()


@router.get("/api/files", response_model=list[FileListItem])
def list_files() -> list[FileListItem]:
    if not settings.data_dir.exists():
        return []
    return [
        FileListItem(path=p.relative_to(settings.data_dir).as_posix(), name=p.name)
        for p in sorted(settings.data_dir.rglob("*.md"))
    ]


@router.get("/api/files/{filepath:path}", response_model=FileReadResponse)
def read_file_endpoint(filepath: str) -> FileReadResponse:
    resolved = _resolve_data_path(filepath)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")
    return FileReadResponse(filepath=filepath, content=resolved.read_text(encoding="utf-8"))


@router.put("/api/files/{filepath:path}")
def write_file_endpoint(filepath: str, request: FileWriteRequest) -> dict:
    resolved = _resolve_data_path(filepath)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")
    resolved.write_text(request.content, encoding="utf-8")
    return {"success": f"Saved {filepath}."}


@router.post("/api/files/append")
def append_to_file_endpoint(request: FileAppendRequest) -> dict:
    """Appends a snippet to a Markdown file (Highlight → Add to Docs)."""
    _resolve_data_path(request.filepath)  # path-traversal guard only
    result = append_to_file(request.filepath, request.content)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/files/revert/{revert_id}", response_model=RevertResponse)
def revert_file_edit(revert_id: str) -> RevertResponse:
    """
    F03 — API-Native Snapshot Pattern.

    Reads the backup JSON stored at ``settings.data_dir/.backups/{revert_id}.json``,
    validates that the target path is inside ``data_dir`` (path-traversal guard),
    and restores the file.
    """
    backup_file = settings.data_dir / ".backups" / f"{revert_id}.json"

    if not backup_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Backup not found or already reverted: {revert_id}",
        )

    # Parse backup JSON
    try:
        state = json.loads(backup_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Backup file is malformed: {exc}",
        ) from exc

    # Path-traversal guard on the stored filepath
    stored_filepath: str = state.get("filepath", "")
    try:
        target_resolved = Path(stored_filepath).resolve()
        data_dir_resolved = settings.data_dir.resolve()
        if not str(target_resolved).startswith(str(data_dir_resolved)):
            raise HTTPException(
                status_code=400,
                detail="Backup references a path outside the data directory.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not validate backup path: {exc}",
        ) from exc

    # Delegate restore to the service layer
    result = revert_backup(revert_id=revert_id, backup_dir=settings.data_dir)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return RevertResponse(success=result["success"], message=result["message"])


@router.get("/api/repo-map")
def repo_map_endpoint() -> dict:
    """Returns the structured repo map (headings only) for the context sidebar."""
    result = get_repo_map(base_dir=str(settings.data_dir))
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ── Private helpers ────────────────────────────────────────────────

def _resolve_data_path(filepath: str) -> Path:
    """
    Resolves *filepath* relative to ``settings.data_dir`` and guards against
    path-traversal attacks.
    """
    resolved = (settings.data_dir / filepath).resolve()
    if not str(resolved).startswith(str(settings.data_dir.resolve())):
        raise HTTPException(status_code=400, detail="Path traversal not allowed.")
    return resolved
