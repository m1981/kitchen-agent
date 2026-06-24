"""
src/providers/anthropic_provider.py
=====================================
AnthropicProvider — wraps the Anthropic Claude SDK agentic loop.

Anthropic messages API vs Gemini
---------------------------------
The Anthropic API is fundamentally different from Gemini in several ways:

1. **History format** — history is a list of plain ``MessageParam``-shaped
   dicts, not SDK objects.

2. **Tool schema format** — Anthropic uses its own ``ToolParam`` schema
   (``{"name", "description", "input_schema"}``) rather than Gemini's
   ``FunctionDeclaration``.  Conversion lives in ``schema_converter.py``.

3. **System instruction** — passed as the top-level ``system`` kwarg, not
   inside the messages list.

4. **max_tokens** — required by the Anthropic API (Gemini does not require it).
"""
from __future__ import annotations

import base64
import json
from typing import Any, Iterator

import anthropic
import structlog
from dotenv import load_dotenv

from src.config import settings
from src.logger import log_timing
from src.agent.tool_executor import ToolCall, ToolExecutor, ToolResult
from src.providers.normalizer import ResponseNormalizer
from src.tools.schema_converter import ToolSchemaConverter
from src.tools.file_ops import read_file

load_dotenv()

logger = structlog.get_logger(__name__)


class AnthropicProvider:
    """
    LLM provider backed by the Anthropic Claude SDK.

    Implements the ``LLMProvider`` Protocol so ``TurnOrchestrator`` can use
    it via ``complete()`` and ``complete_with_tools()``.

    Tool schemas are built once at construction time from the captured
    declarations.
    """

    def __init__(
        self,
        model_override: str | None = None,
        registry: Any | None = None,
        config: "AnthropicConfig | None" = None,
    ) -> None:
        from src.providers.config import AnthropicConfig

        self._config = config or AnthropicConfig()
        api_key = self._config.api_key or None
        self._client = anthropic.Anthropic(api_key=api_key)
        # Resolved at construction; visible to tests via provider._model.
        self._model: str = model_override or self._config.model
        self._temperature: float = self._config.temperature
        self._max_tokens: int = self._config.max_tokens
        self._normalizer = ResponseNormalizer()

        if registry is not None:
            self._registry = registry
        else:
            from src.tools.registry import build_default_registry
            self._registry = build_default_registry()

        self._tool_executor = ToolExecutor(registry=self._registry)

    # ── Common format → Anthropic format conversion ──────────────────

    @staticmethod
    def _common_to_anthropic(msg: dict, user_content: list | None = None) -> dict:
        """
        Convert a common format message to Anthropic format.

        Common format:
            {"role": "user", "content": "Hello"}
            {"role": "assistant", "content": "", "tool_calls": [...]}
            {"role": "tool", "tool_call_id": "...", "content": "result"}

        Anthropic format:
            {"role": "user", "content": "Hello"}
            {"role": "assistant", "content": [{"type": "tool_use", ...}]}
            {"role": "user", "content": [{"type": "tool_result", ...}]}
        """
        role = msg.get("role", "user")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        tool_call_id = msg.get("tool_call_id")

        # Handle tool response messages
        if role == "tool" and tool_call_id:
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content,
                }],
            }

        # Handle assistant messages with tool calls
        if tool_calls:
            blocks: list[dict[str, Any]] = []
            if content and isinstance(content, str):
                blocks.append({"type": "text", "text": content})
            for tc in tool_calls:
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": tc.get("name", "unknown"),
                    "input": tc.get("arguments", {}),
                })
            return {"role": "assistant", "content": blocks}

        # Handle user messages with optional enrichment
        if role == "user" and user_content:
            enriched = list(user_content)
            enriched.append({"type": "text", "text": content})
            return {"role": "user", "content": enriched}

        # Regular messages — pass through only role and content.
        # Strip extra fields (turn_id, provider, model, etc.) that are
        # stored in UI history but not accepted by the Anthropic API.
        return {"role": role, "content": content}

    # ── LLMProvider interface (for TurnOrchestrator) ─────────────────────

    def complete(self, context: "AssembledContext") -> Any:
        """
        Single turn completion via the Anthropic Messages API.
        Returns raw SDK response — normalizer handles parsing.
        """
        from src.agent.context_assembler import AssembledContext

        # Build user content with context files and images
        user_content: list[dict[str, Any]] = []

        if context.context_files:
            snippets: list[str] = []
            for fp in context.context_files:
                result = read_file(fp)
                if "content" in result:
                    snippets.append(f"=== {fp} ===\n{result['content']}")
                else:
                    logger.warning("context_file_unreadable", path=fp, error=result.get("error"))
            if snippets:
                block = "[Context files injected by user]\n\n" + "\n\n".join(snippets)
                user_content.append({"type": "text", "text": block})

        if context.images:
            for img in context.images:
                try:
                    base64.b64decode(img["data"], validate=True)
                    user_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img["mime_type"],
                            "data": img["data"],
                        },
                    })
                except Exception as exc:
                    logger.warning("image_decode_failed", error=str(exc))

        # Build conversation state from context messages
        # Convert from common format to Anthropic format
        self._conversation_state: list[dict[str, Any]] = []
        for msg in context.messages:
            converted = self._common_to_anthropic(msg, user_content)
            self._conversation_state.append(converted)
            if msg.get("role") == "user" and user_content:
                user_content = []  # Only enrich once

        if user_content:
            self._conversation_state.append({"role": "user", "content": user_content})

        # Use schemas from orchestrator (context.tool_schemas) — these are
        # already in Anthropic format from ToolRegistry.schemas_for_provider().
        # When use_tools=False, context.tool_schemas will be None.
        tool_schemas = context.tool_schemas if context.tool_schemas is not None else []

        logger.info(
            "anthropic_complete_start",
            model=self._model,
            max_tokens=self._max_tokens,
            messages_count=len(self._conversation_state),
            has_system_prompt=bool(context.system_prompt),
            tool_schemas_count=len(tool_schemas),
            has_images=bool(context.images),
            has_context_files=bool(context.context_files),
        )

        with log_timing(logger, "anthropic_complete_end") as timing:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                tools=tool_schemas,
                messages=self._conversation_state,
                system=context.system_prompt or None,
            )

        # Log response metadata
        if hasattr(response, "usage") and response.usage:
            timing["input_tokens"] = response.usage.input_tokens
            timing["output_tokens"] = response.usage.output_tokens
            timing["total_tokens"] = response.usage.input_tokens + response.usage.output_tokens
        timing["stop_reason"] = response.stop_reason

        # Log tool calls in response
        tool_call_names: list[str] = []
        for block in response.content:
            if block.type == "tool_use":
                tool_call_names.append(block.name)
                logger.debug(
                    "anthropic_tool_call",
                    tool_name=block.name,
                    tool_call_id=block.id,
                    args_keys=list(block.input.keys()) if isinstance(block.input, dict) else [],
                )
        if tool_call_names:
            timing["tool_calls"] = tool_call_names

        logger.debug(
            "anthropic_complete_result",
            text_length=sum(len(b.text) for b in response.content if b.type == "text"),
            tool_calls_count=len(tool_call_names),
            stop_reason=response.stop_reason,
        )

        # Store response in conversation state for tool loop continuity
        assistant_content: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        self._conversation_state.append({"role": "assistant", "content": assistant_content})

        return response

    def complete_with_tools(
        self,
        context: "AssembledContext",
        tool_calls: list["ToolCall"],
        tool_results: list["ToolResult"],
    ) -> Any:
        """
        Continue generation after tool execution.
        Builds tool result message, appends to conversation state.
        """
        from src.agent.context_assembler import AssembledContext

        # Build tool result message
        result_content: list[dict[str, Any]] = []
        for tr in tool_results:
            result_content.append({
                "type": "tool_result",
                "tool_use_id": tr.tool_call_id,
                "content": tr.content,
            })
            logger.debug(
                "anthropic_tool_result_sent",
                tool_name=tr.name,
                tool_call_id=tr.tool_call_id,
                result_size=len(tr.content),
                is_error=tr.is_error,
            )
        self._conversation_state.append({"role": "user", "content": result_content})

        # Only send tools if orchestrator has set tool_schemas on context.
        tool_schemas = context.tool_schemas if context.tool_schemas is not None else []

        logger.debug(
            "anthropic_complete_with_tools_start",
            model=self._model,
            tool_calls_count=len(tool_calls),
            tool_results_count=len(tool_results),
        )

        with log_timing(logger, "anthropic_complete_with_tools_end") as timing:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                tools=tool_schemas,
                messages=self._conversation_state,
                system=context.system_prompt or None,
            )

        if hasattr(response, "usage") and response.usage:
            timing["input_tokens"] = response.usage.input_tokens
            timing["output_tokens"] = response.usage.output_tokens
        timing["stop_reason"] = response.stop_reason

        # Store response in conversation state for next iteration
        assistant_content: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        self._conversation_state.append({"role": "assistant", "content": assistant_content})

        return response

    def stream(self, context: "AssembledContext") -> Iterator[Any]:
        """
        Stream a single turn via the Anthropic Messages API.
        Yields raw SDK events — normalizer handles text extraction.
        """
        from src.agent.context_assembler import AssembledContext

        # Build user content with context files and images
        user_content: list[dict[str, Any]] = []

        if context.context_files:
            snippets: list[str] = []
            for fp in context.context_files:
                result = read_file(fp)
                if "content" in result:
                    snippets.append(f"=== {fp} ===\n{result['content']}")
                else:
                    logger.warning("context_file_unreadable", path=fp, error=result.get("error"))
            if snippets:
                block = "[Context files injected by user]\n\n" + "\n\n".join(snippets)
                user_content.append({"type": "text", "text": block})

        if context.images:
            for img in context.images:
                try:
                    base64.b64decode(img["data"], validate=True)
                    user_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img["mime_type"],
                            "data": img["data"],
                        },
                    })
                except Exception as exc:
                    logger.warning("image_decode_failed", error=str(exc))

        # Build conversation state from context messages
        self._conversation_state: list[dict[str, Any]] = []
        for msg in context.messages:
            converted = self._common_to_anthropic(msg, user_content)
            self._conversation_state.append(converted)
            if msg.get("role") == "user" and user_content:
                user_content = []  # Only enrich once

        if user_content:
            self._conversation_state.append({"role": "user", "content": user_content})

        # Only send tools if orchestrator has set tool_schemas on context.
        # When use_tools=False, context.tool_schemas will be None.
        tool_schemas = context.tool_schemas if context.tool_schemas is not None else []

        logger.info(
            "anthropic_stream_start",
            model=self._model,
            max_tokens=self._max_tokens,
            messages_count=len(self._conversation_state),
            has_system_prompt=bool(context.system_prompt),
            tool_schemas_count=len(tool_schemas),
            has_images=bool(context.images),
            has_context_files=bool(context.context_files),
        )

        # Use messages.stream() for streaming
        with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            tools=tool_schemas,
            messages=self._conversation_state,
            system=context.system_prompt or None,
        ) as stream:
            for event in stream:
                yield event

        # After streaming, get the final message for conversation state
        # The stream context manager provides access to the final message
        try:
            final_message = stream.get_final_message()

            # Yield __final_message__ so orchestrator can detect tool calls
            # without trying to normalize the last raw stream event.
            yield {"type": "__final_message__", "message": final_message}

            assistant_content: list[dict[str, Any]] = []
            for block in final_message.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            self._conversation_state.append({"role": "assistant", "content": assistant_content})
        except Exception:
            logger.warning("anthropic_stream_final_message_failed")

    def stream_with_tools(
        self,
        context: "AssembledContext",
        tool_calls: list["ToolCall"],
        tool_results: list["ToolResult"],
    ) -> Iterator[Any]:
        """
        Continue streaming after tool execution.
        Yields raw SDK events.
        """
        from src.agent.context_assembler import AssembledContext

        # Build tool result message
        result_content: list[dict[str, Any]] = []
        for tr in tool_results:
            result_content.append({
                "type": "tool_result",
                "tool_use_id": tr.tool_call_id,
                "content": tr.content,
            })
            logger.debug(
                "anthropic_tool_result_sent",
                tool_name=tr.name,
                tool_call_id=tr.tool_call_id,
                result_size=len(tr.content),
                is_error=tr.is_error,
            )
        self._conversation_state.append({"role": "user", "content": result_content})

        # Only send tools if orchestrator has set tool_schemas on context.
        tool_schemas = context.tool_schemas if context.tool_schemas is not None else []

        logger.debug(
            "anthropic_stream_with_tools_start",
            model=self._model,
            tool_calls_count=len(tool_calls),
            tool_results_count=len(tool_results),
        )

        # Use messages.stream() for streaming
        with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            tools=tool_schemas,
            messages=self._conversation_state,
            system=context.system_prompt or None,
        ) as stream:
            for event in stream:
                yield event

        # After streaming, get the final message for conversation state
        try:
            final_message = stream.get_final_message()

            # Yield __final_message__ so orchestrator can detect tool calls
            yield {"type": "__final_message__", "message": final_message}

            # Log tool calls from final message
            tool_call_names: list[str] = []
            assistant_content: list[dict[str, Any]] = []
            for block in final_message.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    tool_call_names.append(block.name)
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            if tool_call_names:
                logger.debug(
                    "anthropic_stream_with_tools_result",
                    tool_calls_count=len(tool_call_names),
                    tool_names=tool_call_names,
                )
            self._conversation_state.append({"role": "assistant", "content": assistant_content})
        except Exception:
            logger.warning("anthropic_stream_final_message_failed")
