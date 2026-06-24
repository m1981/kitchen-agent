"""
api/notes.py
────────────
Note management endpoints.

Routes:
  POST   /api/sessions/{id}/notes        → create note
  GET    /api/sessions/{id}/notes        → list notes
  DELETE /api/sessions/{id}/notes/{nid}  → delete note

All note operations go through NoteManager (content layer) which owns
validation, domain logic, and search delegation. The API layer is a
thin HTTP adapter — nothing else.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.content.note_manager import Note, NoteManager
from src.dependencies import get_note_manager
from src.schemas import NoteCreateRequest, NoteResponse

router = APIRouter()


def _note_to_response(note: Note) -> NoteResponse:
    """Convert a Note domain object to the API response schema."""
    return NoteResponse(
        id=note.id,
        session_id=note.session_id,
        selected_text=note.selected_text,
        note=note.note,
        source_role=note.source_role,
        created_at=note.created_at,
    )


@router.post(
    "/api/sessions/{session_id}/notes",
    response_model=NoteResponse,
    status_code=201,
)
def create_note(
    session_id: str,
    request: NoteCreateRequest,
    note_manager: NoteManager = Depends(get_note_manager),
) -> NoteResponse:
    """Saves a text selection from a chat message as a note."""
    try:
        note = note_manager.create(
            session_id=session_id,
            selected_text=request.selected_text,
            source_role=request.source_role,
            note=request.note,
        )
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return _note_to_response(note)


@router.get(
    "/api/sessions/{session_id}/notes",
    response_model=list[NoteResponse],
)
def list_notes(
    session_id: str,
    note_manager: NoteManager = Depends(get_note_manager),
) -> list[NoteResponse]:
    return [_note_to_response(n) for n in note_manager.list_notes(session_id)]


@router.delete(
    "/api/sessions/{session_id}/notes/{note_id}",
    status_code=204,
)
def delete_note(
    session_id: str,
    note_id: str,
    note_manager: NoteManager = Depends(get_note_manager),
) -> None:
    deleted = note_manager.delete(note_id=note_id, session_id=session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
