"""
api/import_chat.py
──────────────────
Import chat sessions from external JSON files.

Routes:
  POST /api/sessions/import → import a chat session
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from src.dependencies import get_import_service
from src.import_service import ImportService
from src.schemas import ImportRequest, ImportResponse

log = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/api/sessions/import", response_model=ImportResponse, status_code=201)
async def import_chat(
    request: ImportRequest,
    service: ImportService = Depends(get_import_service),
) -> ImportResponse:
    """
    Import a chat session from an external JSON payload.

    Creates a new session with:
    - Dual history format (api + ui)
    - Auto-generated or provided title
    - Optional system prompt
    - Provider/model metadata preserved per message

    No tool calls are supported in imported chats (plain text only).

    Request body:
    ```json
    {
        "title": "Optional custom title",
        "messages": [
            {"role": "user", "content": "Hello", "provider": "openai", "model": "gpt-4"},
            {"role": "assistant", "content": "Hi!", "provider": "openai", "model": "gpt-4"}
        ],
        "system_prompt": "Optional system prompt"
    }
    ```

    Returns:
    ```json
    {
        "session_id": "uuid",
        "title": "Hello",
        "message_count": 2,
        "turn_count": 2
    }
    ```
    """
    log.info(
        "import_request_received",
        message_count=len(request.messages),
        has_title=request.title is not None,
        has_system_prompt=request.system_prompt is not None,
    )

    try:
        result = service.import_chat(request)

        log.info(
            "import_request_completed",
            session_id=result.session_id[:8],
            title=result.title[:30],
            message_count=result.message_count,
        )

        return result

    except ValueError as e:
        log.warning("import_request_validation_error", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        log.error("import_request_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to import chat session")
