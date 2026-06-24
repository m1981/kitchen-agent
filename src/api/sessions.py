"""
api/sessions.py
───────────────
Session lifecycle endpoints.

Routes:
  GET    /api/sessions                    → list sessions
  GET    /api/sessions/tree               → session tree
  GET    /api/sessions/{id}               → get one session
  DELETE /api/sessions/{id}               → delete session
  PATCH  /api/sessions/{id}/archive       → archive session
  DELETE /api/sessions/{id}/archive       → unarchive session
  POST   /api/sessions/{id}/fork          → fork session
  GET    /api/sessions/{id}/export        → export as markdown
  GET    /api/sessions/{id}/export/llm    → export as LLM JSON
  PATCH  /api/sessions/{id}/messages/{tid}         → edit message
  DELETE /api/sessions/{id}/messages/{tid}         → delete message
  POST   /api/sessions/{id}/messages/truncate      → truncate turns
  GET    /api/sessions/{id}/system-prompt          → get system prompt
  PATCH  /api/sessions/{id}/system-prompt          → update system prompt
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

log = structlog.get_logger(__name__)

from src.dependencies import (
    get_export_service,
    get_llm_provider,
    get_message_editor,
    get_session_repo,
)
from src.export_service import ExportService
from src.message_editor import EditError, MessageEditService
from src.repositories import SessionRepository
from src.schemas import (
    ForkRequest,
    ForkResponse,
    LlmExportConfig,
    LlmExportMetadata,
    LlmExportResponse,
    LlmExportTurn,
    MessageDeleteResponse,
    MessageEditRequest,
    MessageEditResponse,
    SessionNode,
    SessionSummary,
    SystemPromptResponse,
    SystemPromptUpdateRequest,
    SystemPromptUpdateResponse,
    TitleGenerateResponse,
    TitleUpdateRequest,
    TitleUpdateResponse,
    TruncateRequest,
    TruncateResponse,
)

router = APIRouter()


# ── Session listing ────────────────────────────────────────────────

@router.get("/api/sessions", response_model=list[SessionSummary])
def get_sessions(
    include_archived: bool = Query(False),
    session_repo: SessionRepository = Depends(get_session_repo),
) -> list[SessionSummary]:
    """Returns a flat list of all sessions ordered by most-recently updated."""
    return [
        SessionSummary(**row)
        for row in session_repo.list_sessions(include_archived=include_archived)
    ]


@router.get("/api/sessions/tree", response_model=list[SessionNode])
def get_session_tree(
    include_archived: bool = Query(True),
    session_repo: SessionRepository = Depends(get_session_repo),
) -> list[SessionNode]:
    """Returns all sessions as a forest of trees."""

    def _build(node: dict) -> SessionNode:
        return SessionNode(
            **{k: v for k, v in node.items() if k != "children"},
            children=[_build(c) for c in node.get("children", [])],
        )

    return [
        _build(root)
        for root in session_repo.get_session_tree(include_archived=include_archived)
    ]


@router.get("/api/sessions/{session_id}")
def get_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> dict:
    _, ui_json, _ = session_repo.load_session(session_id)
    ui_messages = json.loads(ui_json) if ui_json and ui_json != "[]" else []
    return {"ui_messages": ui_messages}


@router.get("/api/sessions/{session_id}/state")
def get_session_state(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> dict:
    """Lightweight state check for test verification.
    Returns message count, turn_ids, and roles without full message content."""
    _, ui_json, _ = session_repo.load_session(session_id)
    ui_messages = json.loads(ui_json) if ui_json and ui_json != "[]" else []
    return {
        "session_id": session_id,
        "message_count": len(ui_messages),
        "turn_ids": [m.get("turn_id") for m in ui_messages],
        "roles": [m["role"] for m in ui_messages],
    }


# ── Session lifecycle ──────────────────────────────────────────────

@router.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> None:
    """Permanently deletes a session and all its notes."""
    try:
        session_repo.delete_session(session_id)
    except ValueError as exc:
        detail = str(exc)
        status = 409 if "child" in detail.lower() else 404
        raise HTTPException(status_code=status, detail=detail) from exc


@router.patch("/api/sessions/{session_id}/archive", status_code=200)
def archive_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> dict:
    archived = session_repo.archive_session(session_id)
    if not archived:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found or already archived: {session_id}",
        )
    return {"archived": True, "session_id": session_id}


@router.delete("/api/sessions/{session_id}/archive", status_code=200)
def unarchive_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> dict:
    """Reverses an archive."""
    unarchived = session_repo.unarchive_session(session_id)
    if not unarchived:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found or not archived: {session_id}",
        )
    return {"archived": False, "session_id": session_id}


# ── Tree Operations ─────────────────────────────────────────────────────


class TreeOperationRequest(BaseModel):
    include_children: bool = False


@router.get("/api/sessions/{session_id}/flags", status_code=200)
def get_session_flags(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> dict:
    """
    Get session state flags for UI decisions.
    Returns is_archived, is_foldered, is_fork, is_fork_parent, children_count, folder_ids.
    """
    try:
        return session_repo.get_session_flags(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/sessions/{session_id}/archive/tree", status_code=200)
def archive_session_tree(
    session_id: str,
    request: TreeOperationRequest,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> dict:
    """
    Archive session and optionally all children.
    """
    try:
        archived_ids = session_repo.archive_tree(session_id, request.include_children)
        return {
            "archived": True,
            "session_ids": archived_ids,
            "count": len(archived_ids),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/api/sessions/{session_id}/archive/tree", status_code=200)
def unarchive_session_tree(
    session_id: str,
    request: TreeOperationRequest,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> dict:
    """
    Unarchive session and optionally all children.
    """
    try:
        unarchived_ids = session_repo.unarchive_tree(session_id, request.include_children)
        return {
            "archived": False,
            "session_ids": unarchived_ids,
            "count": len(unarchived_ids),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/api/sessions/{session_id}/title", response_model=TitleUpdateResponse)
def update_session_title(
    session_id: str,
    request: TitleUpdateRequest,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> TitleUpdateResponse:
    """Update the title of a session."""
    updated = session_repo.update_title(session_id, request.title)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found: {session_id}",
        )
    return TitleUpdateResponse(updated=True, title=request.title)


@router.post("/api/sessions/{session_id}/title/generate", response_model=TitleGenerateResponse)
def generate_session_title(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> TitleGenerateResponse:
    """Generate a title for the session using the LLM.
    
    Uses mimo-v2.5-pro model specifically for title generation.
    Extracts first and last message pairs for context.
    """
    # Load session messages
    _, ui_json, _ = session_repo.load_session(session_id)
    ui_messages = json.loads(ui_json) if ui_json and ui_json != "[]" else []
    
    if not ui_messages:
        raise HTTPException(
            status_code=400,
            detail="Cannot generate title for empty session",
        )
    
    # Separate user and assistant messages
    user_msgs = [m for m in ui_messages if m.get("role") == "user"]
    asst_msgs = [m for m in ui_messages if m.get("role") == "assistant"]
    
    # Build conversation excerpt with first and last pairs
    conversation_parts = []
    
    # First pair (beginning of conversation)
    if user_msgs:
        conversation_parts.append(f"User: {user_msgs[0].get('content', '')[:300]}")
    if asst_msgs:
        conversation_parts.append(f"Assistant: {asst_msgs[0].get('content', '')[:300]}")
    
    # Last pair (end of conversation) - if different from first
    if len(user_msgs) > 1:
        conversation_parts.append(f"\n...\n")
        conversation_parts.append(f"User: {user_msgs[-1].get('content', '')[:300]}")
    if len(asst_msgs) > 1:
        conversation_parts.append(f"Assistant: {asst_msgs[-1].get('content', '')[:300]}")
    
    conversation_excerpt = "\n".join(conversation_parts)
    
    # Generate title using LLM
    prompt = f"""Generate a short, descriptive title (max 50 chars) for this conversation.

IMPORTANT: The title MUST be in the same language as the conversation.
If the conversation is in Polish, write the title in Polish.
If the conversation is in English, write the title in English.

Return ONLY the title, no quotes or explanation.

Conversation:
{conversation_excerpt}"""
    
    try:
        from src.agent.context_assembler import AssembledContext, ContextSlot
        from src.providers.normalizer import ResponseNormalizer
        from src.providers.base import get_provider
        
        # Use claude-haiku-4-5 for fast title generation (~2s vs ~25s with mimo)
        title_provider = get_provider(provider_name='anthropic', model_override='claude-haiku-4-5')
        
        # Create minimal context for title generation
        context = AssembledContext(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a title generator. Return only a short title.",
            tool_schemas=[],
            slots_used={ContextSlot.CONVERSATION_HISTORY: 0},
            total_tokens_estimated=0,
        )
        
        raw_response = title_provider.complete(context)
        normalizer = ResponseNormalizer()
        
        normalized = normalizer.normalize(raw_response, 'anthropic')
        
        # Clean up the title
        title = normalized.text.strip()
        title = title.strip('"').strip("'")
        
        # Fallback if LLM returned empty text
        if not title:
            log.warning("title_generation_empty_response", session_id=session_id)
            if user_msgs:
                title = user_msgs[0].get("content", "")[:50].strip()
                if len(user_msgs[0].get("content", "")) > 50:
                    title += "..."
            else:
                title = f"Session {session_id[:8]}"
        
        # Truncate if too long
        if len(title) > 60:
            title = title[:57] + "..."
        
        # Update the session title
        session_repo.update_title(session_id, title)
        
        return TitleGenerateResponse(generated=True, title=title)
    except Exception as e:
        error_msg = str(e)
        log.error("title_generation_failed", error=error_msg, session_id=session_id)
        
        # Provide user-friendly error messages
        if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
            detail = "API key invalid or missing"
        elif "rate" in error_msg.lower() or "429" in error_msg:
            detail = "Rate limited, try again later"
        elif "timeout" in error_msg.lower():
            detail = "Request timed out, try again"
        elif "connection" in error_msg.lower():
            detail = "Cannot connect to LLM service"
        else:
            detail = f"Title generation failed: {error_msg}"
        
        raise HTTPException(status_code=500, detail=detail) from e


@router.post("/api/sessions/{session_id}/fork", response_model=ForkResponse)
def fork_session(
    session_id: str,
    request: ForkRequest,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> ForkResponse:
    try:
        new_id = session_repo.fork_session(session_id, request.turn_index)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ForkResponse(new_session_id=new_id)


# ── Export ─────────────────────────────────────────────────────────

@router.get(
    "/api/sessions/{session_id}/export",
    response_class=PlainTextResponse,
)
def export_session(
    session_id: str,
    export_service: ExportService = Depends(get_export_service),
) -> PlainTextResponse:
    """Exports the session as a human-readable Markdown document."""
    try:
        markdown = export_service.export_markdown(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(content=markdown, media_type="text/markdown")


@router.get(
    "/api/sessions/{session_id}/export/llm",
    response_model=LlmExportResponse,
)
def export_session_llm(
    session_id: str,
    export_service: ExportService = Depends(get_export_service),
) -> LlmExportResponse:
    """Exports the complete LLM call context as structured JSON."""
    try:
        data = export_service.export_llm_json(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return LlmExportResponse(
        metadata=LlmExportMetadata(**data["metadata"]),
        config=LlmExportConfig(**data["config"]),
        turns=[LlmExportTurn(**turn) for turn in data["turns"]],
    )


# ── Message editing ────────────────────────────────────────────────

@router.patch(
    "/api/sessions/{session_id}/messages/{turn_id}",
    response_model=MessageEditResponse,
)
def edit_message(
    session_id: str,
    turn_id: str,
    request: MessageEditRequest,
    editor: MessageEditService = Depends(get_message_editor),
) -> MessageEditResponse:
    """Edit the content of a single chat message identified by turn_id."""
    try:
        editor.edit_message(
            session_id=session_id,
            turn_id=turn_id,
            new_content=request.new_content,
        )
    except EditError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return MessageEditResponse(updated=True, turn_id=turn_id)


@router.delete(
    "/api/sessions/{session_id}/messages/{turn_id}",
    response_model=MessageDeleteResponse,
)
def delete_message(
    session_id: str,
    turn_id: str,
    delete_pair: bool = Query(False, description="Also delete the next paired message"),
    editor: MessageEditService = Depends(get_message_editor),
) -> MessageDeleteResponse:
    """Delete a single chat message (optionally with its paired response)."""
    try:
        editor.delete_message(
            session_id=session_id,
            turn_id=turn_id,
            delete_pair=delete_pair,
        )
    except EditError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return MessageDeleteResponse(deleted=True, turn_id=turn_id, delete_pair=delete_pair)


@router.post(
    "/api/sessions/{session_id}/messages/truncate",
    response_model=TruncateResponse,
)
def truncate_messages(
    session_id: str,
    request: TruncateRequest,
    editor: MessageEditService = Depends(get_message_editor),
) -> TruncateResponse:
    """Remove the last N turn-pairs from the conversation tail."""
    try:
        editor.truncate_turns(session_id=session_id, n=request.n)
    except EditError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return TruncateResponse(truncated=True, turns_removed=request.n)


# ── System prompt ──────────────────────────────────────────────────

@router.get(
    "/api/sessions/{session_id}/system-prompt",
    response_model=SystemPromptResponse,
)
def get_system_prompt(
    session_id: str,
    editor: MessageEditService = Depends(get_message_editor),
) -> SystemPromptResponse:
    """Retrieve the session-scoped system prompt (or null if unset)."""
    system_prompt = editor.get_system_prompt(session_id)
    return SystemPromptResponse(session_id=session_id, system_prompt=system_prompt)


@router.patch(
    "/api/sessions/{session_id}/system-prompt",
    response_model=SystemPromptUpdateResponse,
)
def update_system_prompt(
    session_id: str,
    request: SystemPromptUpdateRequest,
    editor: MessageEditService = Depends(get_message_editor),
) -> SystemPromptUpdateResponse:
    """Set or clear the session-scoped system prompt override."""
    editor.update_system_prompt(
        session_id=session_id,
        system_prompt=request.system_prompt,
    )
    return SystemPromptUpdateResponse(updated=True)
