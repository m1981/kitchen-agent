"""
api/chat.py
───────────
Chat turn execution and token estimation endpoints.

Routes:
  POST /api/chat                → execute one turn
  POST /api/tokens/estimate     → estimate tokens before sending
  GET  /api/sessions/{id}/tokens → count tokens in existing session
"""
from __future__ import annotations

import asyncio
import json
from functools import partial
from pathlib import Path
from typing import Iterator

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.chat_service import ChatService, ChatTurnResponse
from src.agent.turn_orchestrator import TurnInput
from src.config import settings
from src.dependencies import (
    get_chat_service,
    get_prompt_manager,
    get_session_repo,
)
from src.prompt_manager import PromptManager
from src.repositories import SessionRepository
from src.schemas import (
    ChatRequest,
    ChatResponse,
    SessionTokensResponse,
    TokenEstimateRequest,
    TokenEstimateResponse,
    TokenBreakdown,
    ToolLog,
)
from src.logger import bind_request_context, clear_request_context, log_timing
from src.token_counter import build_pending_context_estimate, count_session_tokens
from src.tools.file_ops import read_file

log = structlog.get_logger(__name__)

router = APIRouter()


# ── Chat turn ──────────────────────────────────────────────────────

@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
    pm: PromptManager = Depends(get_prompt_manager),
) -> ChatResponse:
    """
    Processes a chat message through the Gemini agent and persists state.

    F05 — System instruction resolution
    ------------------------------------
    Priority (highest → lowest):
      1. ``request.system_prompt`` — explicit raw override (legacy / power-user)
      2. ``request.mode_id``       — resolved via PromptManager (new default)
    """
    # Bind request context for all subsequent log calls
    bind_request_context(
        session_id=request.session_id[:8],
        mode=request.mode_id,
        req_provider=request.provider,
        req_model=request.model,
    )

    log.info(
        "chat_request_received",
        message_preview=request.message[:80],
        has_images=bool(request.images),
        has_context_files=bool(request.context_files),
    )

    try:
        # Resolve the system instruction with the F05 priority rules
        if request.system_prompt is not None:
            system_instruction: str | None = request.system_prompt
        else:
            resolved = pm.get_system_instruction(request.mode_id)
            system_instruction = resolved if resolved else None

        # Resolve effective use_tools flag
        mode_obj = pm.get_mode(request.mode_id)
        mode_tools_default = mode_obj.tools_enabled_default if mode_obj else True
        use_tools: bool = request.tools_enabled and mode_tools_default

        # Resolve context file paths
        resolved_context_files = _resolve_context_file_paths(request.context_files)

        loop = asyncio.get_event_loop()

        chat_request = TurnInput(
            session_id=request.session_id,
            user_message=request.message,
            system_prompt=system_instruction,
            images=[img.model_dump() for img in request.images] if request.images else [],
            context_files=resolved_context_files,
            mode=request.mode_id or "default",
            use_tools=use_tools,
            provider=request.provider,
            model=request.model,
        )

        with log_timing(log, "chat_request_complete") as timing:
            result = await loop.run_in_executor(
                None,
                partial(service.handle_turn, chat_request),
            )

        log.info(
            "chat_response_sent",
            provider=result.provider_name,
            model=result.model_name,
            response_length=len(result.assistant_message),
            tool_calls=len(result.tool_calls_made),
            tools_used=result.tool_calls_made[:5],  # first 5 tool names
        )

        # Convert tool_logs dicts to ToolLog objects for response
        tool_log_objects = []
        for tl in result.tool_logs:
            tool_log_objects.append(ToolLog(
                name=tl["name"],
                args=tl.get("args", {}),
                result=tl.get("result", {}),
            ))

        log.debug(
            "chat_tool_logs_converted",
            tool_calls_made=result.tool_calls_made,
            tool_logs_count=len(tool_log_objects),
            tool_logs_preview=[t.name for t in tool_log_objects],
        )

        return ChatResponse(
            text=result.assistant_message,
            tools_used=tool_log_objects,
            user_turn_id=result.user_turn_id,
            assistant_turn_id=result.assistant_turn_id,
            provider=result.provider_name,
            model=result.model_name,
            token_breakdown=TokenBreakdown(**result.token_breakdown) if result.token_breakdown else None,
        )
    except Exception as exc:
        log.exception("chat_request_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        clear_request_context()


# ── Streaming chat turn ────────────────────────────────────────────

@router.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
    pm: PromptManager = Depends(get_prompt_manager),
):
    """
    Stream a chat turn via Server-Sent Events (SSE).

    Events:
      data: {"type":"text", "content":"..."}
      data: {"type":"tool_call", "name":"...", "args":{...}, "id":"..."}
      data: {"type":"tool_result", "name":"...", "result":{...}, "id":"..."}
      data: {"type":"done", "provider":"...", "model":"...", "turn_id":"..."}
      data: {"type":"error", "message":"..."}
      data: [DONE]
    """
    bind_request_context(
        session_id=request.session_id[:8],
        mode=request.mode_id,
        req_provider=request.provider,
        req_model=request.model,
    )

    log.info(
        "chat_stream_request_received",
        message_preview=request.message[:80],
        has_images=bool(request.images),
        has_context_files=bool(request.context_files),
    )

    # Resolve system instruction
    if request.system_prompt is not None:
        system_instruction: str | None = request.system_prompt
    else:
        resolved = pm.get_system_instruction(request.mode_id)
        system_instruction = resolved if resolved else None

    # Resolve use_tools flag
    mode_obj = pm.get_mode(request.mode_id)
    mode_tools_default = mode_obj.tools_enabled_default if mode_obj else True
    use_tools: bool = request.tools_enabled and mode_tools_default

    # Resolve context files
    resolved_context_files = _resolve_context_file_paths(request.context_files)

    chat_request = TurnInput(
        session_id=request.session_id,
        user_message=request.message,
        system_prompt=system_instruction,
        images=[img.model_dump() for img in request.images] if request.images else [],
        context_files=resolved_context_files,
        mode=request.mode_id or "default",
        use_tools=use_tools,
        provider=request.provider,
        model=request.model,
    )

    async def event_generator():
        try:
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()
            sentinel = object()  # Signals end of stream

            def run_stream():
                """Run the synchronous generator in a thread."""
                try:
                    for event in service.stream_turn(chat_request):
                        # Use call_soon_threadsafe to safely put events from
                        # the thread into the async queue
                        loop.call_soon_threadsafe(queue.put_nowait, event)
                except Exception as exc:
                    # Put the exception in the queue to propagate it
                    loop.call_soon_threadsafe(queue.put_nowait, exc)
                finally:
                    # Signal that the stream is done
                    loop.call_soon_threadsafe(queue.put_nowait, sentinel)

            # Start the stream in a thread
            loop.run_in_executor(None, run_stream)

            # Yield events from the queue as they arrive
            while True:
                event = await queue.get()
                if event is sentinel:
                    break
                if isinstance(event, Exception):
                    raise event

                log.debug("chat_stream_event", event_type=event.get("type"))
                data = json.dumps(event)
                yield f"data: {data}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as exc:
            log.exception("chat_stream_failed", error=str(exc))
            error_data = json.dumps({"type": "error", "message": str(exc)})
            yield f"data: {error_data}\n\n"
        finally:
            clear_request_context()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Token estimation ───────────────────────────────────────────────

@router.post("/api/tokens/estimate", response_model=TokenEstimateResponse)
def estimate_pending_tokens(
    request: TokenEstimateRequest,
) -> TokenEstimateResponse:
    """Estimate token cost of a pending turn before sending."""
    resolved_files = _resolve_context_file_paths(request.context_files)

    context_file_contents: list[str] = []
    for path in (resolved_files or []):
        result = read_file(path)
        context_file_contents.append(result.get("content", ""))

    estimate = build_pending_context_estimate(
        user_message=request.user_message,
        images=(
            [img.model_dump() for img in request.images]
            if request.images
            else None
        ),
        context_file_contents=context_file_contents,
        system_prompt=request.system_prompt,
        history_token_count=request.history_token_count,
    )

    return TokenEstimateResponse(
        text_tokens=estimate.text_tokens,
        image_tokens=estimate.image_tokens,
        context_file_tokens=estimate.context_file_tokens,
        system_prompt_tokens=estimate.system_prompt_tokens,
        history_tokens=estimate.history_tokens,
        total_tokens=estimate.total_tokens,
        fallback_used=estimate.fallback_used,
    )


@router.get(
    "/api/sessions/{session_id}/tokens",
    response_model=SessionTokensResponse,
)
def get_session_token_count(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> SessionTokensResponse:
    """Count tokens in an existing session."""
    api_json, _ui_json, system_prompt = session_repo.load_session(session_id)
    estimate = count_session_tokens(api_json, system_prompt=system_prompt)

    return SessionTokensResponse(
        session_id=session_id,
        text_tokens=estimate.text_tokens,
        image_tokens=estimate.image_tokens,
        context_file_tokens=estimate.context_file_tokens,
        system_prompt_tokens=estimate.system_prompt_tokens,
        history_tokens=estimate.history_tokens,
        total_tokens=estimate.total_tokens,
        fallback_used=estimate.fallback_used,
    )


# ── Private helpers ────────────────────────────────────────────────

def _resolve_context_file_paths(
    context_files: list[str] | None,
) -> list[str] | None:
    """
    Resolve context file paths sent by the frontend to full filesystem paths.

    Args:
        context_files: Raw list from the HTTP request, or ``None``.

    Returns:
        Resolved list of absolute path strings, or ``None`` when the input is
        empty / ``None``.
    """
    if not context_files:
        return None

    data_dir_resolved = settings.data_dir.resolve()
    resolved_paths: list[str] = []

    for fp in context_files:
        candidate = Path(fp)

        if candidate.is_absolute():
            try:
                candidate.resolve().relative_to(data_dir_resolved)
            except ValueError:
                log.warning(
                    "context_file_path_traversal_dropped",
                    path=fp,
                    data_dir=str(data_dir_resolved),
                )
                continue
            resolved_paths.append(fp)
        else:
            prefixed = (settings.data_dir / fp).resolve()
            if not str(prefixed).startswith(str(data_dir_resolved)):
                log.warning(
                    "context_file_path_traversal_dropped",
                    path=fp,
                    resolved=str(prefixed),
                )
                continue
            resolved_paths.append(str(prefixed))

    return resolved_paths or None
