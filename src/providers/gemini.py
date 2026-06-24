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
from typing import Any, Iterator

import structlog
from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.config import settings
from src.logger import log_timing
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
        from src.providers.config import GeminiConfig

        self._config = config or GeminiConfig()
        self._client = genai.Client()
        # Resolved at construction so it is stable for the lifetime of this
        # instance and visible to tests via provider._model.
        self._model: str = model_override or self._config.model
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
        config_kwargs["temperature"] = settings.gemini_temperature

        log.info(
            "gemini_complete_start",
            model=self._model,
            temperature=settings.gemini_temperature,
            messages_count=len(self._conversation_state),
            has_system_prompt=bool(context.system_prompt),
            tool_declarations_count=len(declarations),
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

        log.debug(
            "gemini_complete_result",
            text_length=sum(
                len(p.text)
                for p in (response.candidates[0].content.parts if response.candidates and response.candidates[0].content else [])
                if hasattr(p, "text") and p.text
            ),
            tool_calls_count=len(tool_call_names),
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
            tool_calls_count=len(tool_calls),
            tool_results_count=len(tool_results),
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
        config_kwargs["temperature"] = settings.gemini_temperature

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

        # Store response in conversation state for next iteration
        if response.candidates and response.candidates[0].content:
            self._conversation_state.append(response.candidates[0].content)

        return response

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
        config_kwargs["temperature"] = settings.gemini_temperature

        log.info(
            "gemini_stream_start",
            model=self._model,
            messages_count=len(self._conversation_state),
            has_system_prompt=bool(context.system_prompt),
            tool_declarations_count=len(declarations),
            has_images=bool(context.images),
            has_context_files=bool(context.context_files),
        )

        # Use generate_content_stream for streaming
        accumulated_content = None
        chunk_count = 0
        for chunk in self._client.models.generate_content_stream(
            model=self._model,
            contents=self._conversation_state,
            config=types.GenerateContentConfig(**config_kwargs),
        ):
            chunk_count += 1
            # Accumulate content for conversation state
            if chunk.candidates and chunk.candidates[0].content:
                content = chunk.candidates[0].content
                if accumulated_content is None:
                    accumulated_content = content
                else:
                    # Append parts to accumulated content
                    if content.parts:
                        accumulated_content.parts.extend(content.parts)

                # Log tool calls as they stream in
                for part in content.parts or []:
                    if part.function_call:
                        log.debug(
                            "gemini_stream_tool_call",
                            tool_name=part.function_call.name,
                            tool_call_id=getattr(part.function_call, "id", None),
                        )
            yield chunk

        # Log stream completion
        tool_calls_found = []
        if accumulated_content and accumulated_content.parts:
            tool_calls_found = [
                p.function_call.name
                for p in accumulated_content.parts
                if p.function_call
            ]
        log.debug(
            "gemini_stream_end",
            chunks_received=chunk_count,
            tool_calls_count=len(tool_calls_found),
            tool_names=tool_calls_found if tool_calls_found else None,
        )

        # Store accumulated content in conversation state
        if accumulated_content:
            self._conversation_state.append(accumulated_content)

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
            tool_calls_count=len(tool_calls),
            tool_results_count=len(tool_results),
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
        config_kwargs["temperature"] = settings.gemini_temperature

        # Use generate_content_stream for streaming
        accumulated_content = None
        for chunk in self._client.models.generate_content_stream(
            model=self._model,
            contents=self._conversation_state,
            config=types.GenerateContentConfig(**config_kwargs),
        ):
            # Accumulate content for conversation state
            if chunk.candidates and chunk.candidates[0].content:
                content = chunk.candidates[0].content
                if accumulated_content is None:
                    accumulated_content = content
                else:
                    if content.parts:
                        accumulated_content.parts.extend(content.parts)
            yield chunk

        # Store accumulated content in conversation state
        if accumulated_content:
            self._conversation_state.append(accumulated_content)
