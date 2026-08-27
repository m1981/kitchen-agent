"""
src/providers/gemini.py
=======================
GeminiProvider — wraps the Google Gemini SDK agentic loop.

History format
--------------
Gemini uses SDK ``types.Content`` objects.  The history list passed in and
mutated in place must contain ``types.Content`` items (same as before the
refactor).

Provider-switching compatibility
---------------------------------
When a session was started with the Anthropic provider its history is stored
as plain ``{"role": ..., "content": ...}`` dicts (the Anthropic MessageParam
shape).  ``_coerce_history_for_gemini()`` converts any plain-dict items to
``types.Content`` objects before the API call.  Existing ``types.Content``
objects are returned unchanged (pure-Gemini sessions are unaffected).
"""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any, Iterator

import structlog
from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.logger import LOG_LLM_TRACE, log_timing
from src.agent.tool_executor import ToolCall, ToolExecutor, ToolResult
from src.providers.normalizer import ResponseNormalizer
from src.tools.file_ops import read_file

load_dotenv()

log = structlog.get_logger(__name__)


def _build_default_registry():
    """Lazy-load the default ToolRegistry."""
    from src.tools.registry import build_default_registry
    return build_default_registry()


# ---------------------------------------------------------------------------
# Diagnostics — why did the model not answer / not call a tool?
# ---------------------------------------------------------------------------
#
# Gemini can return HTTP 200 with nothing usable: only thought parts, a
# finish_reason of MAX_TOKENS/SAFETY, or a prompt blocked by a filter.  The
# helpers below turn a raw response (or one stream chunk) into flat key-value
# pairs so the logs answer three questions without a debugger:
#
#   1. did the request carry the tool declarations?   → tool_declaration_names
#   2. what did the model actually emit?              → part_kinds / function_calls
#   3. why did it stop?                               → finish_reason / block_reason
#
# Set LOG_LLM_TRACE=1 to additionally dump every raw chunk as JSON.


def _part_kind(part: Any) -> str:
    """Classify one Gemini ``Part`` for tracing."""
    if getattr(part, "thought", None):
        return "thought"
    if getattr(part, "function_call", None):
        return "function_call"
    if getattr(part, "function_response", None):
        return "function_response"
    if getattr(part, "inline_data", None):
        return "inline_data"
    if getattr(part, "executable_code", None):
        return "executable_code"
    if getattr(part, "code_execution_result", None):
        return "code_execution_result"
    text = getattr(part, "text", None)
    if isinstance(text, str) and text:
        return "text"
    return "empty"


def _describe_parts(parts: Any) -> dict:
    """Summarise a list of Parts: counts per kind, text size, tool names."""
    kinds: dict[str, int] = {}
    text_len = 0
    thought_len = 0
    function_calls: list[str] = []

    for part in parts or []:
        kind = _part_kind(part)
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "text":
            text_len += len(part.text)
        elif kind == "thought":
            thought_len += len(getattr(part, "text", "") or "")
        elif kind == "function_call":
            function_calls.append(part.function_call.name)

    return {
        "part_kinds": kinds or None,
        "text_len": text_len,
        "thought_len": thought_len or None,
        "function_calls": function_calls or None,
    }


def _describe_usage(usage: Any) -> dict:
    """Flatten ``usage_metadata`` (thought tokens included — they are billed)."""
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
        "thought_tokens": getattr(usage, "thoughts_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
    }


def _describe_response(response: Any) -> dict:
    """Flat, log-friendly summary of a Gemini response or a single chunk."""
    info: dict = {}

    candidates = getattr(response, "candidates", None) or []
    info["candidates"] = len(candidates)

    if candidates:
        candidate = candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        if finish_reason:
            info["finish_reason"] = str(finish_reason)
        info["finish_message"] = getattr(candidate, "finish_message", None)

        blocked = [
            f"{getattr(r, 'category', '?')}:{getattr(r, 'probability', '?')}"
            for r in (getattr(candidate, "safety_ratings", None) or [])
            if getattr(r, "blocked", False)
        ]
        if blocked:
            info["safety_blocked"] = blocked

        content = getattr(candidate, "content", None)
        info.update(_describe_parts(getattr(content, "parts", None)))

    feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(feedback, "block_reason", None) if feedback else None
    if block_reason:
        info["prompt_block_reason"] = str(block_reason)

    info.update(_describe_usage(getattr(response, "usage_metadata", None)))
    return {k: v for k, v in info.items() if v is not None}


def _declaration_names(declarations: Any) -> list[str]:
    """Tool names actually put on the wire — proves the request carried them."""
    names: list[str] = []
    for decl in declarations or []:
        name = decl.get("name") if isinstance(decl, dict) else getattr(decl, "name", None)
        if name:
            names.append(name)
    return names


def _raw_dump(obj: Any) -> str | None:
    """Full JSON of a response/chunk — only when LOG_LLM_TRACE is enabled."""
    if not LOG_LLM_TRACE:
        return None
    try:
        return obj.model_dump_json(exclude_none=True)[:8000]
    except Exception:  # noqa: BLE001 — tracing must never break a turn
        return repr(obj)[:8000]


# ---------------------------------------------------------------------------
# Anthropic → Gemini history coercion
# ---------------------------------------------------------------------------

def _coerce_history_for_gemini(history: list) -> list:
    """
    Convert common format dicts to Gemini ``types.Content`` objects.

    Common format:
        {"role": "user", "content": "Hello"}
        {"role": "assistant", "content": "Hi!", "tool_calls": [...]}
        {"role": "tool", "tool_call_id": "...", "content": "result"}

    Existing ``types.Content`` objects are passed through unchanged.
    """
    result: list[types.Content] = []
    # Build tool_call_id → function_name mapping as we scan forward
    tool_id_to_name: dict[str, str] = {}

    for item in history:
        # Already a Gemini Content object — pass through
        if isinstance(item, types.Content):
            # Extract tool_call IDs from existing Content objects
            for part in item.parts or []:
                if part.function_call and part.function_call.id:
                    tool_id_to_name[part.function_call.id] = part.function_call.name
            result.append(item)
            continue

        # Skip non-dict items
        if not isinstance(item, dict):
            log.warning(
                "coerce_history_for_gemini: skipping unknown item type %s",
                type(item).__name__,
            )
            continue

        role: str = item.get("role", "user")
        content: Any = item.get("content", "")
        tool_calls: list[dict] | None = item.get("tool_calls")
        tool_call_id: str | None = item.get("tool_call_id")

        # Map roles: common format uses "assistant", Gemini uses "model"
        gemini_role = "model" if role == "assistant" else role

        # Handle tool response messages
        if role == "tool" and tool_call_id:
            # Look up function name from preceding tool_calls
            func_name = tool_id_to_name.get(tool_call_id, "unknown")

            # Parse content as JSON response
            if isinstance(content, str):
                try:
                    response_dict: dict = json.loads(content)
                except (json.JSONDecodeError, ValueError):
                    response_dict = {"content": content}
            elif isinstance(content, dict):
                response_dict = content
            else:
                response_dict = {"content": str(content)}

            result.append(
                types.Content(
                    role="user",  # Gemini uses "user" for tool responses
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=func_name,
                                response=response_dict,
                                id=tool_call_id,
                            )
                        )
                    ],
                )
            )
            continue

        # Handle assistant messages with tool calls
        if tool_calls:
            parts: list[types.Part] = []

            # Add text content if present
            if content and isinstance(content, str):
                parts.append(types.Part(text=content))

            # Add tool calls and build mapping
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                tc_name = tc.get("name", "unknown")
                if tc_id:
                    tool_id_to_name[tc_id] = tc_name
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            name=tc_name,
                            args=tc.get("arguments", {}),
                            id=tc.get("id", ""),
                        )
                    )
                )

            if parts:
                result.append(types.Content(role=gemini_role, parts=parts))
            continue

        # Handle regular text messages
        if isinstance(content, str):
            result.append(
                types.Content(role=gemini_role, parts=[types.Part(text=content)])
            )
            continue

        # Handle list content (structured content)
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(types.Part(text=block.get("text", "")))
                    else:
                        parts.append(types.Part(text=str(block)))
                else:
                    parts.append(types.Part(text=str(block)))

            if parts:
                result.append(types.Content(role=gemini_role, parts=parts))
            continue

        # Fallback: stringify
        log.warning(
            "coerce_history_for_gemini: unexpected content type %s",
            type(content).__name__,
        )
        result.append(
            types.Content(role=gemini_role, parts=[types.Part(text=str(content))])
        )

    return result


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class GeminiProvider:
    """
    LLM provider backed by the Google Gemini SDK.

    Creates a single ``genai.Client`` instance per ``GeminiProvider`` object.
    In production ``get_provider()`` is called per request, so the client is
    lightweight — the SDK reuses the underlying HTTP session.
    """

    def __init__(
        self,
        model_override: str | None = None,
        config: "GeminiConfig | None" = None,
    ) -> None:
        from src.providers.config import GeminiConfig, resolve_temperature

        self._config = config or GeminiConfig()
        self._client = genai.Client()
        # Resolved at construction so it is stable for the lifetime of this
        # instance and visible to tests via provider._model.
        self._model: str = model_override or self._config.model
        # Per-model override (e.g. gemini-3.7-flash → 0.0) wins over the
        # provider-level temperature from Settings.
        self._temperature: float = resolve_temperature(
            self._model, self._config.temperature
        )
        self._normalizer = ResponseNormalizer()
        self._registry = _build_default_registry()
        self._tool_executor = ToolExecutor(registry=self._registry)

    # ── LLMProvider interface (for TurnOrchestrator) ─────────────────────

    def complete(self, context: "AssembledContext") -> Any:
        """
        Single turn completion via the Gemini API.
        Returns raw SDK response — normalizer handles parsing.
        """
        from src.agent.context_assembler import AssembledContext

        # Build user parts with context files and images
        user_parts: list[types.Part] = []

        if context.context_files:
            snippets: list[str] = []
            for fp in context.context_files:
                result = read_file(fp)
                if "content" in result:
                    snippets.append(f"=== {fp} ===\n{result['content']}")
                else:
                    log.warning("context_file_unreadable", path=fp, error=result.get("error"))
            if snippets:
                block = "[Context files injected by user]\n\n" + "\n\n".join(snippets)
                user_parts.append(types.Part(text=block))

        # Build messages list, injecting user parts into the last user message
        messages = list(context.messages)
        if messages and messages[-1].get("role") == "user":
            user_parts.append(types.Part(text=messages[-1]["content"]))
            messages[-1] = {"role": "user", "content": "", "_parts": user_parts}

        if context.images:
            for img in context.images:
                try:
                    raw_bytes = base64.b64decode(img["data"])
                    user_parts.append(
                        types.Part.from_bytes(data=raw_bytes, mime_type=img["mime_type"])
                    )
                except Exception as exc:
                    log.warning("image_decode_failed", error=str(exc))

        # Convert messages to Gemini Content objects
        self._conversation_state = _coerce_history_for_gemini(messages)

        # If we have enriched user parts, replace the last user Content
        if user_parts and self._conversation_state:
            last = self._conversation_state[-1]
            if last.role == "user":
                self._conversation_state[-1] = types.Content(role="user", parts=user_parts)

        # Use schemas from orchestrator — already in Gemini FunctionDeclaration format.
        # When use_tools=False, context.tool_schemas is None → no tools.
        declarations = context.tool_schemas if context.tool_schemas is not None else []
        gemini_tools = types.Tool(function_declarations=declarations) if declarations else None

        config_kwargs: dict = {}
        if context.system_prompt:
            config_kwargs["system_instruction"] = context.system_prompt
        if gemini_tools is not None:
            config_kwargs["tools"] = [gemini_tools]
        config_kwargs["temperature"] = self._temperature

        log.info(
            "gemini_complete_start",
            model=self._model,
            temperature=self._temperature,
            messages_count=len(self._conversation_state),
            has_system_prompt=bool(context.system_prompt),
            tool_declarations_count=len(declarations),
            tool_declaration_names=_declaration_names(declarations),
            has_images=bool(context.images),
            has_context_files=bool(context.context_files),
        )

        with log_timing(log, "gemini_complete_end") as timing:
            response = self._client.models.generate_content(
                model=self._model,
                contents=self._conversation_state,
                config=types.GenerateContentConfig(**config_kwargs),
            )

        # Log response metadata
        if response.usage_metadata:
            timing["input_tokens"] = response.usage_metadata.prompt_token_count
            timing["output_tokens"] = response.usage_metadata.candidates_token_count
            timing["total_tokens"] = response.usage_metadata.total_token_count

        # Log tool calls in response
        tool_call_names: list[str] = []
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts or []:
                if part.function_call:
                    tool_call_names.append(part.function_call.name)
                    log.debug(
                        "gemini_tool_call",
                        tool_name=part.function_call.name,
                        tool_call_id=getattr(part.function_call, "id", None),
                        args_keys=list(part.function_call.args.keys()) if part.function_call.args else [],
                    )
        if tool_call_names:
            timing["tool_calls"] = tool_call_names

        summary = _describe_response(response)
        log.info("gemini_complete_result", model=self._model, **summary)
        raw = _raw_dump(response)
        if raw:
            log.info("gemini_complete_raw", model=self._model, raw=raw)

        if not summary.get("text_len") and not summary.get("function_calls"):
            log.warning(
                "gemini_empty_response",
                where="complete",
                model=self._model,
                temperature=self._temperature,
                hint=(
                    "no text and no tool call — check finish_reason, "
                    "prompt_block_reason and part_kinds above"
                ),
                **summary,
            )

        # Store response in conversation state for tool loop continuity
        if response.candidates and response.candidates[0].content:
            self._conversation_state.append(response.candidates[0].content)

        return response

    def complete_with_tools(
        self,
        context: "AssembledContext",
        tool_calls: list["ToolCall"],
        tool_results: list["ToolResult"],
    ) -> Any:
        """
        Continue generation after tool execution.
        Builds tool call and result messages, appends to conversation state.
        """
        from src.agent.context_assembler import AssembledContext

        log.debug(
            "gemini_complete_with_tools_start",
            model=self._model,
            temperature=self._temperature,
            tool_calls_count=len(tool_calls),
            tool_call_names=[tc.name for tc in tool_calls],
            tool_results_count=len(tool_results),
            tool_results_errors=[tr.name for tr in tool_results if tr.is_error],
        )

        # Build tool call message (assistant Content with function_call parts)
        parts: list[types.Part] = []
        for tc in tool_calls:
            parts.append(types.Part(
                function_call=types.FunctionCall(
                    name=tc.name, args=tc.arguments, id=tc.id,
                )
            ))
            log.debug(
                "gemini_tool_call_sent",
                tool_name=tc.name,
                tool_call_id=tc.id,
                args_keys=list(tc.arguments.keys()),
            )
        tool_call_content = types.Content(role="model", parts=parts)
        self._conversation_state.append(tool_call_content)

        # Build tool result message (user Content with function_response parts)
        result_parts: list[types.Part] = []
        for tr in tool_results:
            try:
                import ast
                response_dict = ast.literal_eval(tr.content)
            except (ValueError, SyntaxError):
                response_dict = {"content": tr.content}
            result_parts.append(types.Part(
                function_response=types.FunctionResponse(
                    name=tr.name,
                    response=response_dict,
                    id=tr.tool_call_id,
                )
            ))
            log.debug(
                "gemini_tool_result_sent",
                tool_name=tr.name,
                tool_call_id=tr.tool_call_id,
                result_size=len(tr.content),
                is_error=tr.is_error,
            )
        tool_result_content = types.Content(role="user", parts=result_parts)
        self._conversation_state.append(tool_result_content)

        # Use schemas from orchestrator
        declarations = context.tool_schemas if context.tool_schemas is not None else []
        gemini_tools = types.Tool(function_declarations=declarations) if declarations else None

        config_kwargs: dict = {}
        if context.system_prompt:
            config_kwargs["system_instruction"] = context.system_prompt
        if gemini_tools is not None:
            config_kwargs["tools"] = [gemini_tools]
        config_kwargs["temperature"] = self._temperature

        with log_timing(log, "gemini_complete_with_tools_end") as timing:
            response = self._client.models.generate_content(
                model=self._model,
                contents=self._conversation_state,
                config=types.GenerateContentConfig(**config_kwargs),
            )

        if response.usage_metadata:
            timing["input_tokens"] = response.usage_metadata.prompt_token_count
            timing["output_tokens"] = response.usage_metadata.candidates_token_count
            timing["total_tokens"] = response.usage_metadata.total_token_count

        summary = _describe_response(response)
        log.info("gemini_complete_with_tools_result", model=self._model, **summary)
        raw = _raw_dump(response)
        if raw:
            log.info("gemini_complete_with_tools_raw", model=self._model, raw=raw)

        if not summary.get("text_len") and not summary.get("function_calls"):
            log.warning(
                "gemini_empty_response",
                where="complete_with_tools",
                model=self._model,
                temperature=self._temperature,
                hint="model produced nothing after tool results were fed back",
                **summary,
            )

        # Store response in conversation state for next iteration
        if response.candidates and response.candidates[0].content:
            self._conversation_state.append(response.candidates[0].content)

        return response

    def _consume_stream(self, chunks: Iterator[Any], where: str) -> Iterator[Any]:
        """
        Yield raw chunks, trace each one, then yield a merged
        ``{"type": "__final_message__"}`` carrying every accumulated part.

        Gemini splits one logical response across many chunks and a
        ``function_call`` does not have to arrive in the last one.  Without a
        merged final message the orchestrator normalizes whichever chunk came
        last — which is usually the empty usage-only chunk — and silently
        reports ``tool_calls=0``.  Anthropic and MiMo already emit
        ``__final_message__``; this brings Gemini in line.
        """
        parts: list[Any] = []
        chunk_count = 0
        last_usage: Any = None
        finish_reason: str | None = None
        prompt_block_reason: str | None = None

        for chunk in chunks:
            chunk_count += 1
            log.debug(
                "gemini_stream_chunk",
                where=where,
                index=chunk_count,
                **_describe_response(chunk),
            )
            raw = _raw_dump(chunk)
            if raw:
                log.info("gemini_stream_chunk_raw", where=where, index=chunk_count, raw=raw)

            candidates = getattr(chunk, "candidates", None) or []
            if candidates:
                candidate = candidates[0]
                if getattr(candidate, "finish_reason", None):
                    finish_reason = str(candidate.finish_reason)
                content = getattr(candidate, "content", None)
                for part in (getattr(content, "parts", None) or []):
                    parts.append(part)
                    if getattr(part, "function_call", None):
                        log.info(
                            "gemini_stream_tool_call",
                            where=where,
                            chunk_index=chunk_count,
                            tool_name=part.function_call.name,
                            tool_call_id=getattr(part.function_call, "id", None),
                            args_keys=(
                                list(part.function_call.args.keys())
                                if part.function_call.args else []
                            ),
                        )

            feedback = getattr(chunk, "prompt_feedback", None)
            if feedback is not None and getattr(feedback, "block_reason", None):
                prompt_block_reason = str(feedback.block_reason)
            if getattr(chunk, "usage_metadata", None):
                last_usage = chunk.usage_metadata

            yield chunk

        summary = _describe_parts(parts)
        log.info(
            "gemini_stream_end",
            where=where,
            model=self._model,
            chunks_received=chunk_count,
            finish_reason=finish_reason,
            prompt_block_reason=prompt_block_reason,
            **summary,
            **_describe_usage(last_usage),
        )

        if not summary["text_len"] and not summary["function_calls"]:
            # The turn produced nothing the user can see and no tool call.
            # Everything needed to tell why is on this one line.
            log.warning(
                "gemini_empty_response",
                where=where,
                model=self._model,
                temperature=self._temperature,
                chunks_received=chunk_count,
                finish_reason=finish_reason,
                prompt_block_reason=prompt_block_reason,
                part_kinds=summary["part_kinds"],
                thought_len=summary["thought_len"],
                hint=(
                    "thought-only output → raise the thinking budget or lower it "
                    "so the model gets to the answer; MAX_TOKENS → response cut "
                    "short; SAFETY/block_reason → filtered; no parts at all → "
                    "model id may not support this request shape"
                ),
                **_describe_usage(last_usage),
            )

        # model_construct: the parts are SDK objects already — skip re-validation
        accumulated_content = (
            types.Content.model_construct(role="model", parts=parts) if parts else None
        )
        if accumulated_content:
            self._conversation_state.append(accumulated_content)

        yield {
            "type": "__final_message__",
            "message": SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=accumulated_content or SimpleNamespace(parts=[]),
                        finish_reason=finish_reason,
                    )
                ],
                usage_metadata=last_usage,
            ),
        }

    def stream(self, context: "AssembledContext") -> Iterator[Any]:
        """
        Stream a single turn via the Gemini API.
        Yields raw SDK chunks — normalizer handles text extraction.
        """
        from src.agent.context_assembler import AssembledContext

        # Build user parts with context files and images
        user_parts: list[types.Part] = []

        if context.context_files:
            snippets: list[str] = []
            for fp in context.context_files:
                result = read_file(fp)
                if "content" in result:
                    snippets.append(f"=== {fp} ===\n{result['content']}")
                else:
                    log.warning("context_file_unreadable", path=fp, error=result.get("error"))
            if snippets:
                block = "[Context files injected by user]\n\n" + "\n\n".join(snippets)
                user_parts.append(types.Part(text=block))

        # Build messages list, injecting user parts into the last user message
        messages = list(context.messages)
        if messages and messages[-1].get("role") == "user":
            user_parts.append(types.Part(text=messages[-1]["content"]))
            messages[-1] = {"role": "user", "content": "", "_parts": user_parts}

        if context.images:
            for img in context.images:
                try:
                    raw_bytes = base64.b64decode(img["data"])
                    user_parts.append(
                        types.Part.from_bytes(data=raw_bytes, mime_type=img["mime_type"])
                    )
                except Exception as exc:
                    log.warning("image_decode_failed", error=str(exc))

        # Convert messages to Gemini Content objects
        self._conversation_state = _coerce_history_for_gemini(messages)

        # If we have enriched user parts, replace the last user Content
        if user_parts and self._conversation_state:
            last = self._conversation_state[-1]
            if last.role == "user":
                self._conversation_state[-1] = types.Content(role="user", parts=user_parts)

        # Use schemas from orchestrator — already in Gemini FunctionDeclaration format.
        # When use_tools=False, context.tool_schemas is None → no tools.
        declarations = context.tool_schemas if context.tool_schemas is not None else []
        gemini_tools = types.Tool(function_declarations=declarations) if declarations else None

        config_kwargs: dict = {}
        if context.system_prompt:
            config_kwargs["system_instruction"] = context.system_prompt
        if gemini_tools is not None:
            config_kwargs["tools"] = [gemini_tools]
        config_kwargs["temperature"] = self._temperature

        log.info(
            "gemini_stream_start",
            model=self._model,
            temperature=self._temperature,
            messages_count=len(self._conversation_state),
            has_system_prompt=bool(context.system_prompt),
            system_prompt_len=len(context.system_prompt or ""),
            tool_declarations_count=len(declarations),
            tool_declaration_names=_declaration_names(declarations),
            has_images=bool(context.images),
            has_context_files=bool(context.context_files),
        )

        yield from self._consume_stream(
            self._client.models.generate_content_stream(
                model=self._model,
                contents=self._conversation_state,
                config=types.GenerateContentConfig(**config_kwargs),
            ),
            where="stream",
        )

    def stream_with_tools(
        self,
        context: "AssembledContext",
        tool_calls: list["ToolCall"],
        tool_results: list["ToolResult"],
    ) -> Iterator[Any]:
        """
        Continue streaming after tool execution.
        Yields raw SDK chunks.
        """
        from src.agent.context_assembler import AssembledContext

        log.debug(
            "gemini_stream_with_tools_start",
            model=self._model,
            temperature=self._temperature,
            tool_calls_count=len(tool_calls),
            tool_call_names=[tc.name for tc in tool_calls],
            tool_results_count=len(tool_results),
            tool_results_errors=[tr.name for tr in tool_results if tr.is_error],
        )

        # Build tool call message (assistant Content with function_call parts)
        parts: list[types.Part] = []
        for tc in tool_calls:
            parts.append(types.Part(
                function_call=types.FunctionCall(
                    name=tc.name, args=tc.arguments, id=tc.id,
                )
            ))
            log.debug(
                "gemini_tool_call_sent",
                tool_name=tc.name,
                tool_call_id=tc.id,
                args_keys=list(tc.arguments.keys()),
            )
        tool_call_content = types.Content(role="model", parts=parts)
        self._conversation_state.append(tool_call_content)

        # Build tool result message (user Content with function_response parts)
        result_parts: list[types.Part] = []
        for tr in tool_results:
            try:
                import ast
                response_dict = ast.literal_eval(tr.content)
            except (ValueError, SyntaxError):
                response_dict = {"content": tr.content}
            result_parts.append(types.Part(
                function_response=types.FunctionResponse(
                    name=tr.name,
                    response=response_dict,
                    id=tr.tool_call_id,
                )
            ))
            log.debug(
                "gemini_tool_result_sent",
                tool_name=tr.name,
                tool_call_id=tr.tool_call_id,
                result_size=len(tr.content),
                is_error=tr.is_error,
            )
        tool_result_content = types.Content(role="user", parts=result_parts)
        self._conversation_state.append(tool_result_content)

        # Use schemas from orchestrator — already in Gemini FunctionDeclaration format.
        # When use_tools=False, context.tool_schemas is None → no tools.
        declarations = context.tool_schemas if context.tool_schemas is not None else []
        gemini_tools = types.Tool(function_declarations=declarations) if declarations else None

        config_kwargs: dict = {}
        if context.system_prompt:
            config_kwargs["system_instruction"] = context.system_prompt
        if gemini_tools is not None:
            config_kwargs["tools"] = [gemini_tools]
        config_kwargs["temperature"] = self._temperature

        yield from self._consume_stream(
            self._client.models.generate_content_stream(
                model=self._model,
                contents=self._conversation_state,
                config=types.GenerateContentConfig(**config_kwargs),
            ),
            where="stream_with_tools",
        )
