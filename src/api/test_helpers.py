"""
api/test_helpers.py
───────────────────
Test-only endpoints for E2E testing.

Available only when DEBUG=true environment variable is set.

Routes:
  POST /api/_test/seed    → create a session with N turn-pairs for testing
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.config import settings
from src.dependencies import get_session_repo
from src.repositories import SessionRepository

router = APIRouter(tags=["test-helpers"])


# ── Request/Response Models ────────────────────────────────────────

class SeedRequest(BaseModel):
    """Request to seed a test session."""
    pairs: int = 2
    title: str | None = None


class SeedResponse(BaseModel):
    """Response after seeding a test session."""
    session_id: str
    message_count: int
    turn_ids: list[dict[str, str]]


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/api/_test/seed", response_model=SeedResponse)
def seed_session(
    request: SeedRequest,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> SeedResponse:
    """Create a session with N turn-pairs for E2E testing.

    All messages have stable turn_ids for edit/delete testing.
    Only available when DEBUG=true.
    """
    if not settings.debug:
        raise HTTPException(
            status_code=404,
            detail="Not found"
        )

    if request.pairs < 1 or request.pairs > 20:
        raise HTTPException(
            status_code=400,
            detail="pairs must be between 1 and 20"
        )

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    title = request.title or f"Test session ({request.pairs} pairs)"

    messages = []
    turn_ids = []

    for i in range(request.pairs):
        user_turn_id = str(uuid.uuid4())
        asst_turn_id = str(uuid.uuid4())

        messages.append({
            "role": "user",
            "content": f"Test user message {i + 1}",
            "turn_id": user_turn_id,
            "timestamp": now,
        })
        messages.append({
            "role": "assistant",
            "content": f"Test assistant reply {i + 1}",
            "turn_id": asst_turn_id,
            "timestamp": now,
        })

        turn_ids.append({"user": user_turn_id, "assistant": asst_turn_id})

    # Save to database
    ui_json = json.dumps(messages)
    api_json = json.dumps([{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages])
    session_repo.save_session(
        session_id=session_id,
        title=title,
        api_history_json=api_json,
        ui_history_json=ui_json,
        parent_id=None,
    )

    return SeedResponse(
        session_id=session_id,
        message_count=len(messages),
        turn_ids=turn_ids,
    )
