"""
tests/helpers.py
================
Shared test doubles used across unit, contract, and integration tests.

Keep this module minimal — only fakes that are genuinely shared between
multiple test files belong here.  Single-use fakes stay in their test file.
"""
from __future__ import annotations

from src.agent.context_assembler import ContextSlot
from src.agent.turn_orchestrator import ToolCall, ToolCallDetail, TokenBreakdown, TurnInput, TurnOutput


class FakeOrchestrator:
    """
    Minimal fake TurnOrchestrator for ChatService and integration tests.
    Records calls. Returns controllable output.
    Supports both run() and stream().
    """

    def __init__(
        self,
        text: str = "response text",
        tool_details: list[ToolCallDetail] | None = None,
    ) -> None:
        self._text = text
        self._tool_details = tool_details or []
        self.run_call_count = 0
        self.stream_call_count = 0
        self.last_turn_input: TurnInput | None = None
        self.last_session: dict | None = None

    def run(self, session: dict, turn_input: TurnInput) -> TurnOutput:
        self.run_call_count += 1
        self.last_turn_input = turn_input
        self.last_session = session

        # Build tool_logs and tool_calls_made from tool_details
        tool_logs = []
        tool_calls_made = []
        tool_calls_tokens = 0
        tool_results_tokens = 0
        for d in self._tool_details:
            tool_calls_made.append(
                ToolCall(id=d.id, name=d.name, arguments=d.arguments, token_count=d.call_tokens)
            )
            tool_calls_tokens += d.call_tokens
            tool_results_tokens += d.result_tokens
            tool_logs.append({
                "name": d.name,
                "args": d.arguments,
                "result": {"content": d.result_content} if not d.is_error else {"error": d.result_content},
                "token_count": d.call_tokens + d.result_tokens,
            })

        # Simulate token counts
        user_tokens = max(1, len(turn_input.user_message) // 4)
        assistant_tokens = max(1, len(self._text) // 4)
        turn_total = user_tokens + tool_calls_tokens + tool_results_tokens + assistant_tokens

        # Build updated_api_history with token counts
        updated_api_history = list(session.get("messages", []))
        updated_api_history.append({"role": "user", "content": turn_input.user_message, "token_count": user_tokens})
        for d in self._tool_details:
            updated_api_history.append({
                "role": "assistant",
                "content": [{"type": "tool_use", "id": d.id, "name": d.name, "input": d.arguments}],
                "token_count": d.call_tokens,
            })
            updated_api_history.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": d.id, "content": d.result_content}],
                "token_count": d.result_tokens,
            })
        updated_api_history.append({
            "role": "assistant",
            "content": [{"type": "text", "text": self._text}],
            "token_count": assistant_tokens,
        })

        # Calculate conversation total
        conversation_total = sum(msg.get("token_count", 0) for msg in updated_api_history if isinstance(msg, dict))

        return TurnOutput(
            assistant_message=self._text,
            updated_api_history=updated_api_history,
            user_turn_id="test-user-turn-id",
            assistant_turn_id="test-assistant-turn-id",
            tool_calls_made=tool_calls_made,
            tool_logs=tool_logs,
            tokens_used={"input": 10, "output": 5, "total": 15},
            context_slots={ContextSlot.SYSTEM_PROMPT: 20},
            token_breakdown=TokenBreakdown(
                user_message_tokens=user_tokens,
                tool_calls_tokens=tool_calls_tokens,
                tool_results_tokens=tool_results_tokens,
                assistant_tokens=assistant_tokens,
                turn_total=turn_total,
                conversation_total=conversation_total,
            ),
        )

    def stream(self, session: dict, turn_input: TurnInput):
        """Fake streaming — yields text_delta events then done."""
        from typing import Iterator
        self.stream_call_count += 1
        self.last_turn_input = turn_input
        self.last_session = session

        # Build tool_logs
        tool_logs = []
        tool_calls_made = []
        tool_calls_tokens = 0
        tool_results_tokens = 0
        for d in self._tool_details:
            tool_calls_made.append(d.name)
            tool_calls_tokens += d.call_tokens
            tool_results_tokens += d.result_tokens
            tool_logs.append({
                "name": d.name,
                "args": d.arguments,
                "result": {"content": d.result_content} if not d.is_error else {"error": d.result_content},
                "token_count": d.call_tokens + d.result_tokens,
            })
            yield {
                "type": "tool_call",
                "name": d.name,
                "args": d.arguments,
                "id": d.id,
            }
            yield {
                "type": "tool_result",
                "name": d.name,
                "args": d.arguments,
                "result": {"content": d.result_content} if not d.is_error else {"error": d.result_content},
                "id": d.id,
            }

        # Yield text in chunks
        yield {"type": "text_delta", "content": self._text}

        # Simulate token counts
        user_tokens = max(1, len(turn_input.user_message) // 4)
        assistant_tokens = max(1, len(self._text) // 4)
        turn_total = user_tokens + tool_calls_tokens + tool_results_tokens + assistant_tokens

        # Done event with tool_details and token_breakdown
        yield {
            "type": "done",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "user_turn_id": "test-user-turn-id",
            "assistant_turn_id": "test-assistant-turn-id",
            "tool_calls_made": tool_calls_made,
            "tool_details": self._tool_details,
            "token_breakdown": {
                "user_message_tokens": user_tokens,
                "tool_calls_tokens": tool_calls_tokens,
                "tool_results_tokens": tool_results_tokens,
                "assistant_tokens": assistant_tokens,
                "turn_total": turn_total,
            },
        }
