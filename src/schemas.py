"""
src/schemas.py
==============
Pydantic models for API requests and responses.
"""

from typing import Any
from pydantic import BaseModel, Field


class ChatImagePart(BaseModel):
    mime_type: str  # e.g. "image/jpeg"
    data: str       # base64-encoded bytes


class ChatRequest(BaseModel):
    """
    Request body for POST /api/chat.

    F05 changes
    -----------
    ``mode_id`` replaces the old ``system_prompt`` as the primary way to
    select a persona.  The backend resolves ``mode_id`` → full system
    instruction via ``PromptManager`` before calling the agent.

    Backward compatibility
    ----------------------
    ``system_prompt`` is kept as an **optional override**.  When provided it
    takes precedence over ``mode_id`` so the old Svelte frontend (which sends
    the full prompt string directly) continues to work without changes.

    Priority (highest → lowest):
      1. ``system_prompt``  (explicit raw override — legacy / power-user path)
      2. ``mode_id``        (resolved via PromptManager — new default path)
    """
    session_id: str
    message: str
    # F05 — new primary field; defaults to "general"
    mode_id: str = "general"
    # Legacy override — if set, bypasses mode_id resolution entirely
    system_prompt: str | None = None
    images: list[ChatImagePart] | None = None
    context_files: list[str] | None = None
    # Provider routing — both optional; omit to use the server default.
    # When provided they are forwarded to get_provider() for this turn only.
    provider: str | None = None   # e.g. "gemini" | "anthropic"
    model: str | None = None      # provider-specific model id override
    # Tool-calling toggle — Option C: per-request override of the mode default.
    # True  → agentic loop (LLM may call file tools); default behaviour.
    # False → plain LLM call; no tools sent, no agentic loop.
    # When omitted the resolved mode's tools_enabled_default is used instead.
    tools_enabled: bool = True


class ToolLog(BaseModel):
    name: str
    args: dict[str, Any]
    result: dict[str, Any]
    token_count: int = 0  # token count for this tool call + result


class TokenBreakdown(BaseModel):
    """
    Per-turn token breakdown.

    user_message_tokens  : Tokens in the user's message.
    tool_calls_tokens    : Total tokens across all tool call arguments.
    tool_results_tokens  : Total tokens across all tool results.
    assistant_tokens     : Tokens in the assistant's final response.
    turn_total           : Sum of all above for this turn.
    conversation_total   : Running total across the entire conversation.
    """
    user_message_tokens: int = 0
    tool_calls_tokens: int = 0
    tool_results_tokens: int = 0
    assistant_tokens: int = 0
    turn_total: int = 0
    conversation_total: int = 0


class ChatResponse(BaseModel):
    text: str
    tools_used: list[ToolLog]
    user_turn_id: str | None = None
    assistant_turn_id: str | None = None
    provider: str | None = None
    model: str | None = None
    token_breakdown: TokenBreakdown | None = None  # per-turn token breakdown


class ForkRequest(BaseModel):
    turn_index: int


class ForkResponse(BaseModel):
    new_session_id: str


class SessionSummary(BaseModel):
    """Flat representation of a session as returned by GET /api/sessions."""
    id: str
    title: str | None
    updated_at: str | None
    parent_id: str | None = None
    fork_turn_index: int | None = None
    root_id: str | None = None
    archived_at: str | None = None


class SessionNode(BaseModel):
    """One node in the session tree returned by GET /api/sessions/tree."""
    id: str
    title: str | None
    updated_at: str | None
    parent_id: str | None = None
    fork_turn_index: int | None = None
    root_id: str | None = None
    archived_at: str | None = None
    children: list["SessionNode"] = []


# Required so Pydantic can resolve the self-referential type.
SessionNode.model_rebuild()


class TitleUpdateRequest(BaseModel):
    """Request body for PATCH /api/sessions/{id}/title."""
    title: str


class TitleUpdateResponse(BaseModel):
    """Response for PATCH /api/sessions/{id}/title."""
    updated: bool
    title: str


class TitleGenerateResponse(BaseModel):
    """Response for POST /api/sessions/{id}/title/generate."""
    generated: bool
    title: str


class FileReadResponse(BaseModel):
    filepath: str
    content: str


class FileWriteRequest(BaseModel):
    content: str


class FileAppendRequest(BaseModel):
    filepath: str
    content: str


class FileListItem(BaseModel):
    path: str
    name: str


# ---------------------------------------------------------------------------
# F03 — Snapshot / Revert schemas
# ---------------------------------------------------------------------------

class RevertResponse(BaseModel):
    """
    Response returned by POST /api/files/revert/{revert_id}.

    success : Always True on a 200 response (errors become HTTP 4xx).
    message : Human-readable description, e.g. "Reverted changes to notes.md".
    """
    success: bool
    message: str


class NoteCreateRequest(BaseModel):
    selected_text: str
    source_role: str  # "user" | "assistant"
    note: str = ""


class NoteResponse(BaseModel):
    id: str
    session_id: str
    selected_text: str
    note: str
    source_role: str
    created_at: str


# ---------------------------------------------------------------------------
# F04 — LLM-context debug export schemas (extended from F03)
# ---------------------------------------------------------------------------

class LlmExportMetadata(BaseModel):
    """Metadata block for the LLM debug export."""
    session_id: str
    title: str
    turn_count: int
    export_timestamp: str  # ISO 8601 UTC


class LlmExportConfig(BaseModel):
    """
    Reconstructed GenerateContentConfig envelope — what the Gemini API
    received alongside the conversation turns.

    model              : Gemini model name (e.g. "gemini-3.1-pro-preview").
    temperature        : Sampling temperature used for this session.
    system_instruction : Persisted system prompt, or null if none was active.
    tools              : Full tool/function_declarations schema as sent to the API.
    """
    model: str
    temperature: float
    system_instruction: str | None
    tools: list[dict[str, Any]]  # open structure — mirrors SDK wire format


class LlmExportTurn(BaseModel):
    """One Content turn as the LLM sees it."""
    role: str
    parts: list[dict[str, Any]]  # keep as raw dicts — structure varies by type


class LlmExportResponse(BaseModel):
    """
    Response returned by GET /api/sessions/{id}/export/llm.

    Key order (canonical, matches debug reading order):
      metadata → config → turns

    metadata : Session info and export timestamp.
    config   : Reconstructed GenerateContentConfig envelope (F04).
    turns    : Ordered list of every Content turn in the LLM context window.
    """
    metadata: LlmExportMetadata
    config: LlmExportConfig
    turns: list[LlmExportTurn]


# ---------------------------------------------------------------------------
# F05 — Backend Prompt Management schemas
# ---------------------------------------------------------------------------

class PromptModeResponse(BaseModel):
    """
    Metadata for one prompt mode, returned by GET /api/prompts/modes.

    Intentionally does NOT include ``content`` so the frontend never
    receives the full system prompt text in the list response.
    """
    id: str
    label: str
    eyebrow: str


class PromptModeDetail(BaseModel):
    """
    Full detail for one prompt mode, returned by GET /api/prompts/modes/{mode_id}.

    Includes ``content`` — the complete resolved system instruction
    (base_agent_rules + mode body) — so the frontend can display it
    in an expandable panel when the user explicitly asks to inspect it.

    Returns 404 when the mode_id is not found.
    """
    id: str
    label: str
    eyebrow: str
    content: str


# ---------------------------------------------------------------------------
# Message Editor schemas — in-session message editing/deletion
# ---------------------------------------------------------------------------

class MessageEditRequest(BaseModel):
    """
    Request body for PATCH /api/sessions/{id}/messages/{index}.

    new_content : Replacement text for the targeted message.
                  Must be non-empty after stripping whitespace.
    """
    new_content: str


class MessageEditResponse(BaseModel):
    """
    Response returned by PATCH /api/sessions/{id}/messages/{turn_id}.

    updated  : Always True on a 200 response.
    turn_id  : The stable UUID of the message that was edited (echoed back).
    """
    updated: bool
    turn_id: str


class MessageDeleteResponse(BaseModel):
    """
    Response returned by DELETE /api/sessions/{id}/messages/{turn_id}.

    deleted     : Always True on a 200 response.
    turn_id     : The stable UUID of the message that was deleted.
    delete_pair : Whether the paired next message was also removed.
    """
    deleted: bool
    turn_id: str
    delete_pair: bool


class TruncateRequest(BaseModel):
    """
    Request body for POST /api/sessions/{id}/messages/truncate.

    n : Number of complete turn-pairs (user + assistant) to remove from the tail.
        Must be >= 1.
    """
    n: int


class TruncateResponse(BaseModel):
    """
    Response returned by POST /api/sessions/{id}/messages/truncate.

    truncated     : Always True on a 200 response.
    turns_removed : The value of ``n`` that was applied.
    """
    truncated: bool
    turns_removed: int


class SystemPromptUpdateRequest(BaseModel):
    """
    Request body for PATCH /api/sessions/{id}/system-prompt.

    system_prompt : The new session-scoped system-prompt override.
                    Empty string is valid (clears the override).
    """
    system_prompt: str


class SystemPromptResponse(BaseModel):
    """
    Response returned by GET /api/sessions/{id}/system-prompt.

    session_id    : The session UUID.
    system_prompt : Current value stored in the DB (None if never set).
    """
    session_id: str
    system_prompt: str | None


class SystemPromptUpdateResponse(BaseModel):
    """
    Response returned by PATCH /api/sessions/{id}/system-prompt.

    updated : Always True on a 200 response.
    """
    updated: bool


# ---------------------------------------------------------------------------
# Token counting / estimation
# ---------------------------------------------------------------------------

class TokenEstimateRequest(BaseModel):
    """
    Body for POST /api/tokens/estimate.

    Describes a *pending* (not-yet-sent) context so the backend can return
    a heuristic token count before the user presses Send.

    user_message        : The text the user is about to send.
    images              : Optional list of images (same shape as ChatRequest).
    context_files       : Optional list of file paths attached as context.
    system_prompt       : The system instruction for the current mode/session.
    history_token_count : Token count of the prior conversation history
                          (caller supplies — avoids re-reading the DB).
    """
    user_message: str
    images: list[ChatImagePart] | None = None
    context_files: list[str] | None = None
    system_prompt: str | None = None
    history_token_count: int = 0


class SessionTokensResponse(BaseModel):
    """
    Response for GET /api/sessions/{session_id}/tokens.

    Wraps the TokenEstimate from token_counter plus the session_id for
    easy correlation on the client side.

    session_id            : The queried session UUID.
    text_tokens           : Token count for history text (exact or heuristic).
    image_tokens          : Always 0 for stored sessions (images not stored).
    context_file_tokens   : Always 0 for stored sessions.
    system_prompt_tokens  : Always 0 (folded into text_tokens for exact path).
    history_tokens        : Always 0 (all history is in text_tokens for exact).
    total_tokens          : Authoritative total.
    fallback_used         : True when the Gemini API was unavailable.
    """
    session_id: str
    text_tokens: int
    image_tokens: int
    context_file_tokens: int
    system_prompt_tokens: int
    history_tokens: int
    total_tokens: int
    fallback_used: bool


class TokenEstimateResponse(BaseModel):
    """
    Response for POST /api/tokens/estimate.

    A full breakdown so the frontend can show a tooltip with component detail.

    text_tokens          : Tokens from the user message text.
    image_tokens         : Tokens from all attached images.
    context_file_tokens  : Tokens from injected context files.
    system_prompt_tokens : Tokens in the system instruction.
    history_tokens       : Tokens from prior conversation history.
    total_tokens         : Sum of all the above.
    fallback_used        : Always True (heuristic, never exact API).
    """
    text_tokens: int
    image_tokens: int
    context_file_tokens: int
    system_prompt_tokens: int
    history_tokens: int
    total_tokens: int
    fallback_used: bool


# ---------------------------------------------------------------------------
# Provider catalogue  (GET /api/providers, GET /api/providers/active)
# ---------------------------------------------------------------------------

class ModelInfo(BaseModel):
    """
    Metadata for one model within a provider.

    context_k  : Context window size in **thousands** of tokens.
                 E.g. 1000 means a 1M-token context window.
    """
    id: str
    label: str
    context_k: int


class ProviderInfo(BaseModel):
    """
    Metadata for one LLM provider including its model catalogue.

    Returned by GET /api/providers.
    """
    id: str
    label: str
    default_model: str
    models: list[ModelInfo]


class ActiveProvider(BaseModel):
    """
    The server's currently configured default provider + model.

    Returned by GET /api/providers/active.  The frontend uses this to
    pre-select the correct option in the provider picker on first load.
    """
    provider: str
    model: str


class AppInfo(BaseModel):
    """
    Domain branding metadata for the running instance.

    Returned by GET /api/app-info.  Driven by the APP_TITLE and
    APP_DESCRIPTION environment variables (see config.py) so any domain
    can brand the UI without touching frontend source code.
    """
    title: str
    description: str


# ── Import schemas ─────────────────────────────────────────────────────────────

class ImportMessage(BaseModel):
    """Single message in an import payload."""
    role: str  # "user" or "assistant"
    content: str
    model: str | None = None
    provider: str | None = None


class ImportRequest(BaseModel):
    """Request body for POST /api/sessions/import."""
    title: str | None = None  # Optional; auto-generated if absent
    messages: list[ImportMessage]
    system_prompt: str | None = None


class ImportResponse(BaseModel):
    """Response for POST /api/sessions/import."""
    session_id: str
    title: str
    message_count: int
    turn_count: int


# ── Folder schemas ─────────────────────────────────────────────────────────────

class FolderCreateRequest(BaseModel):
    """Request body for POST /api/folders."""
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(default="#6B7280", pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str = Field(default="📁", max_length=10)
    parent_id: str | None = None


class FolderUpdateRequest(BaseModel):
    """Request body for PATCH /api/folders/{id}."""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(default=None, max_length=10)
    order_index: int | None = None


class FolderResponse(BaseModel):
    """Response for folder operations."""
    id: str
    name: str
    color: str
    icon: str
    parent_id: str | None
    order_index: int
    session_count: int = 0
    created_at: str
    updated_at: str


class FolderListResponse(BaseModel):
    """Response for GET /api/folders."""
    folders: list[FolderResponse]
    total: int


class FolderAssignRequest(BaseModel):
    """Request body for POST /api/folders/{id}/sessions/{session_id}."""
    session_id: str


class FolderReorderRequest(BaseModel):
    """Request body for PATCH /api/folders/reorder."""
    folder_ids: list[str] = Field(min_length=1)


class FolderMoveSessionRequest(BaseModel):
    """Request body for PATCH /api/folders/move-session."""
    session_id: str
    from_folder: str
    to_folder: str
