"""
src/providers/mimo_provider.py
===============================
MimoProvider — wraps the Xiaomi Mimo API (OpenAI-compatible).

Xiaomi Mimo provides an OpenAI-compatible chat completions API.
This provider uses the ``openai`` SDK with a custom ``base_url``.

Models
------
- ``mimo-v2.5-pro`` — 1M context, 128K output, function calling
- ``mimo-v2.5``     — 1M context, lighter/cheaper

History format
--------------
Mimo uses OpenAI's message format: plain dicts with
``{"role": ..., "content": ...}`` — same as Anthropic's storage format.
"""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any, Iterator

import structlog
from dotenv import load_dotenv
from openai import OpenAI

from src.config import settings
from src.logger import log_timing
from src.agent.tool_executor import ToolCall, ToolExecutor, ToolResult
from src.tools.file_ops import read_file

load_dotenv()

logger = structlog.get_logger(__name__)


def _build_default_registry():
    """Lazy-load the default ToolRegistry."""
    from src.tools.registry import build_default_registry
    return build_default_registry()


class MimoProvider:
    """
    LLM provider backed by the Xiaomi Mimo API (OpenAI-compatible).

    Implements the ``LLMProvider`` Protocol so ``TurnOrchestrator`` can use
    it via ``complete()`` and ``complete_with_tools()``.
    """

    def __init__(
        self,
        model_override: str | None = None,
        config: "MimoConfig | None" = None,
    ) -> None:
        from src.providers.config import MimoConfig

        self._config = config or MimoConfig()
        self._client = OpenAI(
            api_key=self._config.api_key,
            base_url=self._config.base_url,
        )
        self._model: str = model_override or self._config.model
        self._temperature: float = self._config.temperature
        self._max_tokens: int = self._config.max_tokens
        self._registry = _build_default_registry()
        self._tool_executor = ToolExecutor(registry=self._registry)

    @staticmethod
    def _common_to_openai(msg: dict) -> dict:
        """
        Convert a common format message to OpenAI format.

        Common format (stored in DB):
            {"role": "user", "content": "Hello"}
            {"role": "assistant", "content": "", "tool_calls": [{"id": "...", "name": "...", "arguments": {...}}]}
            {"role": "tool", "tool_call_id": "...", "content": "result"}

        OpenAI format (sent to API):
            {"role": "user", "content": "Hello"}
            {"role": "assistant", "content": null, "tool_calls": [{"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}]}
            {"role": "tool", "tool_call_id": "...", "content": "result"}
        """
        role = msg.get("role", "user")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        tool_call_id = msg.get("tool_call_id")

        # Handle tool response messages — pass through tool_call_id
        if role == "tool" and tool_call_id:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }

        # Handle assistant messages with tool calls — convert to OpenAI format
        if tool_calls:
            openai_tool_calls = []
            for tc in tool_calls:
                arguments = tc.get("arguments", {})
                # OpenAI API expects arguments as a JSON string
                if isinstance(arguments, dict):
                    arguments = json.dumps(arguments)
                openai_tool_calls.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc.get("name", "unknown"),
                        "arguments": arguments,
                    },
                })
            return {
                "role": "assistant",
                "content": content or None,
                "tool_calls": openai_tool_calls,
            }

        # Regular messages — pass through role and content only
        return {"role": role, "content": content}

    def _build_messages(self, context: "AssembledContext") -> list[dict[str, Any]]:
        """Build OpenAI-format messages from AssembledContext."""
        messages: list[dict[str, Any]] = []

        # System prompt
        if context.system_prompt:
            messages.append({"role": "system", "content": context.system_prompt})

        # Context files injection
        context_block = ""
        if context.context_files:
            snippets: list[str] = []
            for fp in context.context_files:
                result = read_file(fp)
                if "content" in result:
                    snippets.append(f"=== {fp} ===\n{result['content']}")
                else:
                    logger.warning("context_file_unreadable", path=fp, error=result.get("error"))
            if snippets:
                context_block = "[Context files injected by user]\n\n" + "\n\n".join(snippets)

        # Conversation messages — convert from common format to OpenAI format
        for msg in context.messages:
            role = msg.get("role", "user")

            # Enrich last user message with context files and images
            if role == "user" and (context_block or context.images):
                parts: list[dict[str, Any]] = []
                if context_block:
                    parts.append({"type": "text", "text": context_block})
                    context_block = ""  # Only inject once
                if context.images:
                    for img in context.images:
                        try:
                            base64.b64decode(img["data"], validate=True)
                            parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{img['mime_type']};base64,{img['data']}",
                                },
                            })
                        except Exception as exc:
                            logger.warning("image_decode_failed", error=str(exc))
                    context.images = []  # Only inject once
                parts.append({"type": "text", "text": msg.get("content", "")})
                messages.append({"role": role, "content": parts})
            else:
                # Convert from common format to OpenAI format
                messages.append(self._common_to_openai(msg))

        return messages

    def complete(self, context: "AssembledContext") -> Any:
        """
        Single turn completion via the Mimo API.
        Returns raw OpenAI-style response — normalizer handles parsing.
        """
        from src.agent.context_assembler import AssembledContext

        messages = self._build_messages(context)

        # Only send tools if the orchestrator has set tool_schemas on the context.
        # When use_tools=False, context.tool_schemas will be None.
        # Use schemas from orchestrator — already in OpenAI format.
        tool_schemas = context.tool_schemas if context.tool_schemas is not None else []

        self._conversation_state = messages

        logger.info(
            "mimo_complete_start",
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            messages_count=len(messages),
            has_system_prompt=bool(context.system_prompt),
            tool_schemas_count=len(tool_schemas),
            has_images=bool(context.images),
            has_context_files=bool(context.context_files),
        )

        with log_timing(logger, "mimo_complete_end") as timing:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )

        # Log response metadata
        if response.usage:
            timing["input_tokens"] = response.usage.prompt_tokens
            timing["output_tokens"] = response.usage.completion_tokens
            timing["total_tokens"] = response.usage.total_tokens

        # Log tool calls and response details
        tool_call_names: list[str] = []
        if response.choices:
            msg = response.choices[0].message
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_call_names.append(tc.function.name)
                    logger.debug(
                        "mimo_tool_call",
                        tool_name=tc.function.name,
                        tool_call_id=tc.id,
                    )
            timing["finish_reason"] = response.choices[0].finish_reason

        if tool_call_names:
            timing["tool_calls"] = tool_call_names

        logger.debug(
            "mimo_complete_result",
            text_length=len(msg.content) if response.choices and msg.content else 0,
            tool_calls_count=len(tool_call_names),
            finish_reason=response.choices[0].finish_reason if response.choices else None,
        )

        # Store assistant response in conversation state
        if response.choices:
            msg = response.choices[0].message
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            self._conversation_state.append(assistant_msg)

        return response

    def complete_with_tools(
        self,
        context: "AssembledContext",
        tool_calls: list["ToolCall"],
        tool_results: list["ToolResult"],
    ) -> Any:
        """
        Continue generation after tool execution.
        Builds tool result messages, appends to conversation state.
        """
        from src.agent.context_assembler import AssembledContext

        # Append tool results as tool messages
        for tr in tool_results:
            self._conversation_state.append({
                "role": "tool",
                "tool_call_id": tr.tool_call_id,
                "content": tr.content,
            })
            logger.debug(
                "mimo_tool_result_sent",
                tool_name=tr.name,
                tool_call_id=tr.tool_call_id,
                result_size=len(tr.content),
                is_error=tr.is_error,
            )

        tool_schemas = context.tool_schemas if context.tool_schemas is not None else []

        logger.debug(
            "mimo_complete_with_tools_start",
            model=self._model,
            tool_calls_count=len(tool_calls),
            tool_results_count=len(tool_results),
        )

        with log_timing(logger, "mimo_complete_with_tools_end") as timing:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=self._conversation_state,
                tools=tool_schemas if tool_schemas else None,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )

        if response.usage:
            timing["input_tokens"] = response.usage.prompt_tokens
            timing["output_tokens"] = response.usage.completion_tokens
            timing["total_tokens"] = response.usage.total_tokens

        # Log tool calls in response
        tool_call_names: list[str] = []
        if response.choices:
            msg = response.choices[0].message
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_call_names.append(tc.function.name)
            timing["finish_reason"] = response.choices[0].finish_reason
        if tool_call_names:
            timing["tool_calls"] = tool_call_names

        # Store assistant response in conversation state
        if response.choices:
            msg = response.choices[0].message
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            self._conversation_state.append(assistant_msg)

        return response

    def stream(self, context: "AssembledContext") -> Iterator[Any]:
        """
        Stream a single turn via the Mimo API.
        Yields raw OpenAI-style chunks — normalizer handles text extraction.
        """
        from src.agent.context_assembler import AssembledContext

        messages = self._build_messages(context)

        # Only send tools if the orchestrator has set tool_schemas on the context.
        # Use schemas from orchestrator — already in OpenAI format.
        tool_schemas = context.tool_schemas if context.tool_schemas is not None else []

        self._conversation_state = messages

        logger.info(
            "mimo_stream_start",
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            messages_count=len(messages),
            has_system_prompt=bool(context.system_prompt),
            tool_schemas_count=len(tool_schemas),
            has_images=bool(context.images),
            has_context_files=bool(context.context_files),
        )

        # Use stream=True for streaming
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tool_schemas if tool_schemas else None,
            stream=True,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

        # Accumulate content and tool calls for conversation state
        accumulated_content = ""
        accumulated_tool_calls: dict[int, dict] = {}  # index -> tool_call_data
        chunk_count = 0

        for chunk in stream:
            chunk_count += 1
            # Extract content from chunk
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    accumulated_content += delta.content
                
                # Accumulate tool calls
                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in accumulated_tool_calls:
                            accumulated_tool_calls[idx] = {
                                "id": tc.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc.id:
                            accumulated_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                accumulated_tool_calls[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                accumulated_tool_calls[idx]["function"]["arguments"] += tc.function.arguments
            
            yield chunk

        # Log stream completion
        tool_names = [
            accumulated_tool_calls[i]["function"]["name"]
            for i in sorted(accumulated_tool_calls.keys())
        ] if accumulated_tool_calls else []
        logger.debug(
            "mimo_stream_end",
            chunks_received=chunk_count,
            text_length=len(accumulated_content),
            tool_calls_count=len(tool_names),
            tool_names=tool_names if tool_names else None,
        )

        # Build assistant message for conversation state
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": accumulated_content or None}
        if accumulated_tool_calls:
            assistant_msg["tool_calls"] = [
                accumulated_tool_calls[i] for i in sorted(accumulated_tool_calls.keys())
            ]
        self._conversation_state.append(assistant_msg)

        # Yield __final_message__ so orchestrator can detect tool calls.
        # Build a SimpleNamespace mimicking OpenAI response shape.
        tool_call_objects = None
        if accumulated_tool_calls:
            tool_call_objects = []
            for idx in sorted(accumulated_tool_calls.keys()):
                tc_data = accumulated_tool_calls[idx]
                tool_call_objects.append(SimpleNamespace(
                    id=tc_data["id"],
                    function=SimpleNamespace(
                        name=tc_data["function"]["name"],
                        arguments=tc_data["function"]["arguments"],
                    ),
                ))

        final_msg = SimpleNamespace(
            content=accumulated_content or None,
            tool_calls=tool_call_objects,
        )
        final_response = SimpleNamespace(
            choices=[SimpleNamespace(message=final_msg)],
            usage=None,
        )
        yield {"type": "__final_message__", "message": final_response}

    def stream_with_tools(
        self,
        context: "AssembledContext",
        tool_calls: list["ToolCall"],
        tool_results: list["ToolResult"],
    ) -> Iterator[Any]:
        """
        Continue streaming after tool execution.
        Yields raw OpenAI-style chunks.
        """
        from src.agent.context_assembler import AssembledContext

        # Append tool results as tool messages
        for tr in tool_results:
            self._conversation_state.append({
                "role": "tool",
                "tool_call_id": tr.tool_call_id,
                "content": tr.content,
            })
            logger.debug(
                "mimo_tool_result_sent",
                tool_name=tr.name,
                tool_call_id=tr.tool_call_id,
                result_size=len(tr.content),
                is_error=tr.is_error,
            )

        tool_schemas = context.tool_schemas if context.tool_schemas is not None else []

        logger.debug(
            "mimo_stream_with_tools_start",
            model=self._model,
            tool_calls_count=len(tool_calls),
            tool_results_count=len(tool_results),
        )

        # Use stream=True for streaming
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=self._conversation_state,
            tools=tool_schemas if tool_schemas else None,
            stream=True,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

        # Accumulate content and tool calls for conversation state
        accumulated_content = ""
        accumulated_tool_calls: dict[int, dict] = {}
        chunk_count = 0

        for chunk in stream:
            chunk_count += 1
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    accumulated_content += delta.content
                
                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in accumulated_tool_calls:
                            accumulated_tool_calls[idx] = {
                                "id": tc.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc.id:
                            accumulated_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                accumulated_tool_calls[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                accumulated_tool_calls[idx]["function"]["arguments"] += tc.function.arguments
            
            yield chunk

        # Log stream completion
        tool_names = [
            accumulated_tool_calls[i]["function"]["name"]
            for i in sorted(accumulated_tool_calls.keys())
        ] if accumulated_tool_calls else []
        logger.debug(
            "mimo_stream_with_tools_end",
            chunks_received=chunk_count,
            text_length=len(accumulated_content),
            tool_calls_count=len(tool_names),
            tool_names=tool_names if tool_names else None,
        )

        # Build assistant message for conversation state
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": accumulated_content or None}
        if accumulated_tool_calls:
            assistant_msg["tool_calls"] = [
                accumulated_tool_calls[i] for i in sorted(accumulated_tool_calls.keys())
            ]
        self._conversation_state.append(assistant_msg)

        # Yield __final_message__ so orchestrator can detect tool calls.
        tool_call_objects = None
        if accumulated_tool_calls:
            tool_call_objects = []
            for idx in sorted(accumulated_tool_calls.keys()):
                tc_data = accumulated_tool_calls[idx]
                tool_call_objects.append(SimpleNamespace(
                    id=tc_data["id"],
                    function=SimpleNamespace(
                        name=tc_data["function"]["name"],
                        arguments=tc_data["function"]["arguments"],
                    ),
                ))

        final_msg = SimpleNamespace(
            content=accumulated_content or None,
            tool_calls=tool_call_objects,
        )
        final_response = SimpleNamespace(
            choices=[SimpleNamespace(message=final_msg)],
            usage=None,
        )
        yield {"type": "__final_message__", "message": final_response}
