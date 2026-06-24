"""
src/providers/normalizer.py
===========================
ResponseNormalizer — absorbs all provider-specific response shape differences.

The rest of the codebase only ever sees ``NormalizedResponse``.  Provider
SDKs (google-genai, anthropic) return wildly different structures; this
module is the **only place** that knows about both.

Design rules
------------
* ``normalize()`` takes a raw SDK response and a provider name string.
  It returns a ``NormalizedResponse`` — never raises for valid inputs.
* ``normalize_chunk()`` takes a raw streaming chunk and returns a text
  delta string.  Returns ``""`` for non-text chunks (no raise).
* Unknown providers raise ``ValueError`` — a programming error, not a
  runtime condition.
* The ``raw`` field on ``NormalizedResponse`` preserves the original SDK
  object for debugging.

Phase 1 scope
-------------
Initially the normalizer is used inside provider ``process_chat_turn()``
methods to normalize individual API responses during the agentic loop.
The provider's public interface (returning ``tuple[str, list[dict]]``)
does not change.
"""
from __future__ import annotations

import json
import structlog
from dataclasses import dataclass, field
from typing import Any

# Single canonical ToolCall — defined in tool_executor, re-exported here
# so normalizer consumers don't need to import from agent.tool_executor.
from src.agent.tool_executor import ToolCall  # noqa: F401

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes — the provider-agnostic contract
# ---------------------------------------------------------------------------


@dataclass
class NormalizedResponse:
    """
    Single shape regardless of which provider responded.

    The rest of the application only ever sees this.
    """

    text: str
    has_tool_calls: bool = False
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)  # {input, output, total}
    raw: Any = None  # keep original for debugging


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

class ResponseNormalizer:
    """
    Absorbs ALL provider-specific response shape differences.

    Gemini and Anthropic return very different structures.
    This is the only place that knows about both.
    """

    def normalize(self, raw: Any, provider: str) -> NormalizedResponse:
        """
        Convert a raw SDK response to a NormalizedResponse.

        Args:
            raw:      The raw response object from the provider SDK.
            provider: "gemini", "anthropic", or "mimo".

        Returns:
            A NormalizedResponse with text, tool_calls, and usage populated.

        Raises:
            ValueError: when provider is not recognized.
        """
        result = None
        if provider == "gemini":
            result = self._from_gemini(raw)
        elif provider == "anthropic":
            result = self._from_anthropic(raw)
        elif provider == "mimo":
            result = self._from_openai_compat(raw)
        else:
            raise ValueError(f"Unknown provider: {provider!r}. Supported: 'gemini', 'anthropic', 'mimo'.")

        log.debug(
            "normalize_result",
            provider=provider,
            text_length=len(result.text),
            has_tool_calls=result.has_tool_calls,
            tool_calls_count=len(result.tool_calls),
            usage=result.usage,
        )
        return result

    def normalize_chunk(self, chunk: Any, provider: str) -> str:
        """
        Extract text delta from a streaming chunk.

        Returns "" for non-text chunks (no raise).
        """
        if provider == "gemini":
            return self._gemini_chunk_text(chunk)
        if provider == "anthropic":
            return self._anthropic_chunk_text(chunk)
        if provider == "mimo":
            return self._openai_compat_chunk_text(chunk)
        raise ValueError(f"Unknown provider: {provider!r}. Supported: 'gemini', 'anthropic', 'mimo'.")

    # ── Gemini ────────────────────────────────────────────────────────

    def _from_gemini(self, raw: Any) -> NormalizedResponse:
        """
        google-genai SDK response shape::

            response.candidates[0].content.parts → text or function_call
            response.usage_metadata → token counts
        """
        candidate = raw.candidates[0]
        parts = candidate.content.parts if candidate.content and candidate.content.parts else []

        if not parts and candidate.content:
            log.warning("gemini_empty_parts", has_content=bool(candidate.content), has_parts=bool(getattr(candidate.content, 'parts', None)))

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for part in parts:
            if hasattr(part, "text") and isinstance(part.text, str) and part.text:
                text_parts.append(part.text)
            elif hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                call_id = fc.id if hasattr(fc, "id") and fc.id else fc.name
                tool_calls.append(
                    ToolCall(
                        id=call_id,
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {},
                    )
                )

        usage: dict = {"input": 0, "output": 0, "total": 0}
        if hasattr(raw, "usage_metadata") and raw.usage_metadata is not None:
            um = raw.usage_metadata
            usage = {
                "input": getattr(um, "prompt_token_count", 0) or 0,
                "output": getattr(um, "candidates_token_count", 0) or 0,
                "total": getattr(um, "total_token_count", 0) or 0,
            }

        return NormalizedResponse(
            text="".join(text_parts),
            has_tool_calls=bool(tool_calls),
            tool_calls=tool_calls,
            usage=usage,
            raw=raw,
        )

    def _gemini_chunk_text(self, chunk: Any) -> str:
        try:
            return chunk.candidates[0].content.parts[0].text or ""
        except (IndexError, AttributeError):
            return ""

    # ── Anthropic ─────────────────────────────────────────────────────

    def _from_anthropic(self, raw: Any) -> NormalizedResponse:
        """
        anthropic SDK response shape::

            response.content → list of TextBlock | ToolUseBlock
            response.usage → input_tokens, output_tokens
        """
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in raw.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(block.text)
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        usage: dict = {}
        if hasattr(raw, "usage") and raw.usage is not None:
            usage = {
                "input": raw.usage.input_tokens,
                "output": raw.usage.output_tokens,
                "total": raw.usage.input_tokens + raw.usage.output_tokens,
            }

        return NormalizedResponse(
            text="".join(text_parts),
            has_tool_calls=bool(tool_calls),
            tool_calls=tool_calls,
            usage=usage,
            raw=raw,
        )

    def _anthropic_chunk_text(self, chunk: Any) -> str:
        """
        Anthropic streaming events::

            content_block_delta → delta.type == "text_delta"
        """
        try:
            if chunk.type == "content_block_delta":
                if chunk.delta.type == "text_delta":
                    return chunk.delta.text
        except AttributeError:
            pass
        return ""

    # ── OpenAI-compatible (Mimo) ─────────────────────────────────────

    def _from_openai_compat(self, raw: Any) -> NormalizedResponse:
        """
        OpenAI-compatible response shape (used by Mimo)::

            response.choices[0].message.content → text
            response.choices[0].message.tool_calls → tool calls
            response.usage.prompt_tokens / completion_tokens
        """
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        if raw.choices:
            message = raw.choices[0].message
            if message.content:
                text_parts.append(message.content)
            if message.tool_calls:
                for tc in message.tool_calls:
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        arguments = {}
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    ))

        usage: dict = {"input": 0, "output": 0, "total": 0}
        if hasattr(raw, "usage") and raw.usage is not None:
            usage = {
                "input": raw.usage.prompt_tokens or 0,
                "output": raw.usage.completion_tokens or 0,
                "total": (raw.usage.prompt_tokens or 0) + (raw.usage.completion_tokens or 0),
            }

        return NormalizedResponse(
            text="".join(text_parts),
            has_tool_calls=bool(tool_calls),
            tool_calls=tool_calls,
            usage=usage,
            raw=raw,
        )

    def _openai_compat_chunk_text(self, chunk: Any) -> str:
        """
        OpenAI-compatible streaming chunk.

            chunk.choices[0].delta.content → text delta
        """
        try:
            return chunk.choices[0].delta.content or ""
        except (IndexError, AttributeError):
            return ""
