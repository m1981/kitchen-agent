"""
src/token_counter.py
====================
Token counting and estimation for Gemini conversations.

Two modes of operation
----------------------

1. **Exact** — ``count_session_tokens()``
   Calls ``client.models.count_tokens()`` (the real Gemini API) to get the
   authoritative token count for a stored session.  On API failure it
   gracefully degrades to the heuristic path and sets ``fallback_used=True``.

2. **Heuristic (fast, offline)** — ``build_pending_context_estimate()``
   Estimates tokens for a *pending* context (message + images + files +
   history) using local rules so the UI can show a "you are about to send
   ~N tokens" indicator **before** hitting Send.  Always sets
   ``fallback_used=True`` because it is never exact.

Heuristic rules
---------------
Text
    Gemini tokeniser averages ~4 characters per token.
    We use ceil(len(text) / 4) which is accurate to ±15 % for Latin text.

Images
    Gemini bills vision at 258 tokens for the first 512×512 tile plus 258
    for every additional tile.  We cannot decode image dimensions from raw
    bytes cheaply, so we use decoded byte-size as a proxy:
      < 50 KB  → 1 tile  (258 tokens)
      50–200 KB → 2 tiles (516 tokens)
      > 200 KB → 4 tiles  (1 032 tokens)
    This is intentionally conservative.

Context files
    Same text heuristic applied to each file's content.

Design notes
------------
* ``_client`` is module-level (same pattern as agent.py) so tests can patch
  ``src.token_counter._client`` with a single ``patch()`` call.
* ``count_session_tokens`` re-hydrates the serialised history so it can pass
  real ``Content`` objects to the Gemini count API.
* The function is synchronous — the FastAPI route dispatches it to
  ``run_in_executor`` if latency matters.
"""
from __future__ import annotations

import math
import base64
import json
import structlog

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from src.config import settings
from src.serializers import hydrate_history

load_dotenv()

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Gemini client (same singleton pattern as agent.py)
# ---------------------------------------------------------------------------

_client = genai.Client()

# ---------------------------------------------------------------------------
# Chars-per-token ratio used everywhere for the text heuristic
# ---------------------------------------------------------------------------
_CHARS_PER_TOKEN: int = 4

# Gemini vision tile cost in tokens (one 512×512 tile)
_TILE_TOKENS: int = 258

# Byte-size thresholds for the image tile heuristic
_IMG_SMALL_BYTES: int = 50_000    # < 50 KB  → 1 tile
_IMG_MEDIUM_BYTES: int = 200_000  # 50–200 KB → 2 tiles
#                                 # > 200 KB  → 4 tiles


# ════════════════════════════════════════════════════════════════════════════
# Public data model
# ════════════════════════════════════════════════════════════════════════════

class TokenEstimate(BaseModel):
    """
    A detailed breakdown of tokens in a context window.

    Attributes:
        text_tokens:         Tokens from the user message text.
        image_tokens:        Tokens from all attached images.
        context_file_tokens: Tokens from injected context files.
        system_prompt_tokens:Tokens in the system instruction.
        history_tokens:      Tokens from prior conversation history.
        total_tokens:        Sum of all the above.
        fallback_used:       True when the heuristic path was used instead of
                             the live Gemini count_tokens API.
    """
    text_tokens: int
    image_tokens: int
    context_file_tokens: int
    system_prompt_tokens: int
    history_tokens: int
    total_tokens: int
    fallback_used: bool = False


# ════════════════════════════════════════════════════════════════════════════
# Low-level heuristic helpers
# ════════════════════════════════════════════════════════════════════════════

def estimate_tokens_for_text(text: str) -> int:
    """
    Heuristic token estimate for a plain-text string.

    Uses the industry-standard approximation of 4 characters per token which
    is reasonable for Gemini's SentencePiece-based tokeniser on English and
    most European languages (including Polish).

    Args:
        text: The string to estimate.

    Returns:
        Integer token count (0 for empty string).
    """
    if not text:
        return 0
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


def estimate_tokens_for_image(b64_data: str, mime_type: str) -> int:
    """
    Heuristic token estimate for a base64-encoded image.

    Decodes the base64 string to get the byte length, then maps to a tile
    count using Gemini's 512×512 tile pricing model (258 tokens/tile).

    Falls back to the minimum cost (258 tokens) if the base64 is invalid.

    Args:
        b64_data:  Base64-encoded image data (no data-URI prefix).
        mime_type: Image MIME type (e.g. ``"image/png"``).  Currently unused
                   beyond logging but kept for future codec-specific logic.

    Returns:
        Integer token estimate.
    """
    try:
        raw_bytes = base64.b64decode(b64_data)
        byte_len = len(raw_bytes)
    except Exception:  # noqa: BLE001
        logger.warning("token_counter: invalid base64 for image (%s), using min cost", mime_type)
        return _TILE_TOKENS  # minimum cost

    if byte_len < _IMG_SMALL_BYTES:
        tiles = 1
    elif byte_len < _IMG_MEDIUM_BYTES:
        tiles = 2
    else:
        tiles = 4

    return tiles * _TILE_TOKENS


def estimate_tokens_for_context_files(file_contents: list[str]) -> int:
    """
    Estimate token count for a list of already-read file contents.

    Args:
        file_contents: List of file content strings.
                       Caller is responsible for reading files.
                       Empty list returns 0.

    Returns:
        Integer sum of token estimates across all files.
    """
    return sum(
        estimate_tokens_for_text(content)
        for content in file_contents
        if content
    )


# ════════════════════════════════════════════════════════════════════════════
# High-level: pending context estimate (heuristic, no API call)
# ════════════════════════════════════════════════════════════════════════════

def build_pending_context_estimate(
    user_message: str,
    images: list[dict] | None,
    context_file_contents: list[str] | None,
    system_prompt: str | None,
    history_token_count: int,
) -> TokenEstimate:
    """
    Build a ``TokenEstimate`` for a *not-yet-sent* turn using local heuristics.

    This function never calls the Gemini API.  It is designed to be called
    from the ``POST /api/tokens/estimate`` endpoint so the frontend can
    display an "about to send ~N tokens" indicator before the user presses
    Send.  ``fallback_used`` is always ``True``.

    Args:
        user_message:          The text the user is about to send.
        images:                List of ``{"mime_type": ..., "data": ...}`` dicts.
        context_file_contents: Already-read file contents as strings.
                               Caller reads files; we only count.
        system_prompt:         The system instruction, if any.
        history_token_count:   Token count of the conversation so far.

    Returns:
        ``TokenEstimate`` with all fields populated and ``fallback_used=True``.
    """
    text_tokens = estimate_tokens_for_text(user_message)

    image_tokens = 0
    if images:
        for img in images:
            image_tokens += estimate_tokens_for_image(
                img.get("data", ""), img.get("mime_type", "image/jpeg")
            )

    context_file_tokens = estimate_tokens_for_context_files(
        context_file_contents or []
    )

    system_prompt_tokens = (
        estimate_tokens_for_text(system_prompt) if system_prompt else 0
    )

    total = (
        text_tokens
        + image_tokens
        + context_file_tokens
        + system_prompt_tokens
        + history_token_count
    )

    return TokenEstimate(
        text_tokens=text_tokens,
        image_tokens=image_tokens,
        context_file_tokens=context_file_tokens,
        system_prompt_tokens=system_prompt_tokens,
        history_tokens=history_token_count,
        total_tokens=total,
        fallback_used=True,
    )


# ════════════════════════════════════════════════════════════════════════════
# High-level: exact session token count (live Gemini API)
# ════════════════════════════════════════════════════════════════════════════

def count_session_tokens(
    api_history_json: str,
    system_prompt: str | None,
    model: str | None = None,
) -> TokenEstimate:
    """
    Return the authoritative token count for a stored session by calling the
    Gemini ``count_tokens`` API.

    Falls back to a heuristic total if the API call fails (network error,
    quota exceeded, etc.), with ``fallback_used=True`` set on the result.

    An empty history (``"[]"`` or ``""``) is returned as all-zero without
    making any API call.

    Args:
        api_history_json: The ``api_history_json`` string stored in the DB.
        system_prompt:    The session's stored system prompt, forwarded in
                          ``GenerateContentConfig`` so the count reflects the
                          actual context window used.
        model:            Override the model name.  Defaults to
                          ``settings.gemini_model``.

    Returns:
        ``TokenEstimate`` — ``fallback_used=False`` on API success,
        ``True`` on error/fallback.
    """
    resolved_model = model or settings.gemini_model

    # ── Fast path: nothing to count ──────────────────────────────────────────
    items: list[dict] = json.loads(api_history_json) if api_history_json.strip() not in ("", "[]") else []
    if not items:
        return TokenEstimate(
            text_tokens=0,
            image_tokens=0,
            context_file_tokens=0,
            system_prompt_tokens=0,
            history_tokens=0,
            total_tokens=0,
            fallback_used=False,
        )

    # ── Re-hydrate to common format ─────────────────────────────────────────
    history: list[dict] = hydrate_history(api_history_json)

    # Convert common format to Gemini SDK objects for count_tokens API
    from src.providers.gemini import _coerce_history_for_gemini
    gemini_history = _coerce_history_for_gemini(history)

    if not gemini_history:
        logger.info(
            "token_counter: no convertible history items — using heuristic fallback",
        )
    else:
        config = types.CountTokensConfig(
            system_instruction=system_prompt,
        )

        # ── Attempt live API count ──────────────────────────────────────────
        try:
            response = _client.models.count_tokens(
                model=resolved_model,
                contents=gemini_history,
                config=config,
            )
            total = response.total_tokens or 0
            logger.info(
                "token_counter: exact count for %d history items → %d tokens",
                len(items),
                total,
            )
            return TokenEstimate(
                text_tokens=total,   # exact API doesn't split by type
                image_tokens=0,
                context_file_tokens=0,
                system_prompt_tokens=0,
                history_tokens=0,
                total_tokens=total,
                fallback_used=False,
            )

        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "token_counter: count_tokens API failed — using heuristic fallback. "
                "This is expected for non-Gemini providers.",
                error=str(exc),
            )

    # ── Heuristic fallback (works with common format) ─────────────────────
    heuristic_total = 0
    for item in items:
        role = item.get("role", "")
        content = item.get("content", "")
        tool_calls = item.get("tool_calls", [])

        # Count text content
        if isinstance(content, str) and content:
            heuristic_total += estimate_tokens_for_text(content)
        elif isinstance(content, list):
            # Structured content (legacy format)
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        heuristic_total += estimate_tokens_for_text(block.get("text", ""))

        # Count tool calls
        for tc in tool_calls:
            heuristic_total += estimate_tokens_for_text(
                tc.get("name", "") + json.dumps(tc.get("arguments", {}))
            )

    if system_prompt:
        heuristic_total += estimate_tokens_for_text(system_prompt)

    return TokenEstimate(
        text_tokens=heuristic_total,
        image_tokens=0,
        context_file_tokens=0,
        system_prompt_tokens=0,
        history_tokens=0,
        total_tokens=heuristic_total,
        fallback_used=True,
    )


# ════════════════════════════════════════════════════════════════════════════
# Class wrapper for dependency injection
# ════════════════════════════════════════════════════════════════════════════

class TokenCounter:
    """
    Thin class wrapper around module-level token functions.
    Satisfies TokenCounterProtocol for dependency injection.
    """

    def count(self, text: str) -> int:
        return estimate_tokens_for_text(text)

    def count_message(self, message: dict) -> int:
        content = message.get("content", "")
        if isinstance(content, str):
            return estimate_tokens_for_text(content)
        if isinstance(content, list):
            total = 0
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        total += estimate_tokens_for_text(part.get("text", ""))
                    elif part.get("type") == "image":
                        total += estimate_tokens_for_image(
                            part.get("b64_data", ""),
                            part.get("mime_type", "image/jpeg"),
                        )
            return total
        return 0

    def trim_to(self, text: str, max_tokens: int) -> str:
        """
        Trim text to approximately max_tokens.
        Uses character ratio as a fast approximation.
        """
        current = estimate_tokens_for_text(text)
        if current <= max_tokens:
            return text
        ratio = max_tokens / max(current, 1)
        char_limit = int(len(text) * ratio)
        return text[:char_limit]
