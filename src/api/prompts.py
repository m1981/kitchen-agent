"""
api/prompts.py
──────────────
Prompt mode management endpoints.

Routes:
  GET  /api/prompts/modes           → list all modes
  GET  /api/prompts/modes/{id}      → get mode detail
  POST /api/prompts/reload          → reload from disk
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.dependencies import get_prompt_manager
from src.prompt_manager import PromptManager
from src.schemas import PromptModeDetail, PromptModeResponse

router = APIRouter()


@router.get(
    "/api/prompts/modes",
    response_model=list[PromptModeResponse],
)
def get_prompt_modes(
    pm: PromptManager = Depends(get_prompt_manager),
) -> list[PromptModeResponse]:
    """Returns the list of available prompt modes for the frontend mode switcher."""
    return [PromptModeResponse(**m) for m in pm.get_all_modes()]


@router.get(
    "/api/prompts/modes/{mode_id}",
    response_model=PromptModeDetail,
)
def get_prompt_mode_detail(
    mode_id: str,
    pm: PromptManager = Depends(get_prompt_manager),
) -> PromptModeDetail:
    """Returns the full prompt text for a single mode."""
    all_modes = {m["id"]: m for m in pm.get_all_modes()}
    if mode_id not in all_modes:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt mode not found: {mode_id}",
        )
    content = pm.get_system_instruction(mode_id)
    meta = all_modes[mode_id]
    return PromptModeDetail(
        id=meta["id"],
        label=meta["label"],
        eyebrow=meta["eyebrow"],
        content=content,
    )


@router.post("/api/prompts/reload")
def reload_prompts(
    pm: PromptManager = Depends(get_prompt_manager),
) -> dict:
    """Hot-reload prompt files from disk."""
    pm.reload_prompts()
    return {"success": True}
