# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Gemini streaming lost tool calls** — `GeminiProvider.stream()` /
  `stream_with_tools()` now emit `{"type": "__final_message__"}` with all
  accumulated parts, like the Anthropic and MiMo providers already did.
  Previously the orchestrator normalized whichever chunk arrived last —
  usually the usage-only chunk — so a `function_call` sent in an earlier
  chunk was reported as `tool_calls=0`.
- **Gemini streaming lost text** — `ResponseNormalizer._gemini_chunk_text()`
  read only `parts[0].text`, dropping the answer whenever a thought or
  `function_call` part came first. It now scans every part.
- **Thought parts leaked into answers** — reasoning parts (`part.thought`)
  are excluded from both streamed deltas and normalized text.
- **Misleading provider/model in stream logs** — `stream_turn_started` bound
  the request context *after* logging, so a reused worker thread stamped the
  previous request's model onto the new turn's log lines.

### Added

- `gemini-3.7-flash` in both provider catalogues, pinned to `temperature: 0`
  via `MODEL_TEMPERATURES` / `resolve_temperature()` in `providers/config.py`.
- **LLM turn tracing** — `gemini_stream_chunk` (per chunk: part kinds,
  finish_reason, usage), `gemini_stream_end`, `gemini_complete_result`,
  `gemini_stream_tool_call`, plus `tool_declaration_names` on every request
  log so it is visible whether tool schemas actually reached the API.
- **`gemini_empty_response` warning** — one line carrying finish_reason,
  prompt_block_reason, part kinds and thought tokens whenever a turn
  produces neither text nor a tool call.
- **`orchestrator_no_tool_calls` / `orchestrator_empty_llm_response`
  warnings** and a `stream_collected` summary (chunks, deltas, text length,
  `used_final_message`, tool calls, usage).
- **`LOG_LLM_TRACE=1`** env flag — dumps every raw Gemini response and
  stream chunk as JSON.

- `TurnInput.session_id` field — `TurnInput` now carries the session
  identifier so it can serve as the single DTO across all layers.
- `TurnOutput.tool_details: list[ToolCallDetail]` — raw tool call
  details exposed for history construction by downstream consumers.
- `ChatService._build_api_history()` — builds the provider-agnostic
  history list (user → [tool_call → tool_result]* → assistant) from
  raw orchestrator output.
- `TurnOrchestrator._execute_turn()` — unified generator implementing
  the full turn lifecycle (context assembly → LLM call → tool loop →
  response). Both `run()` and `stream()` delegate to it.
- `TurnOrchestrator._resolve_provider()` — extracted provider
  resolution (override vs default) into a testable helper.
- `TurnOrchestrator._setup_context()` — extracted context assembly
  and tool schema injection into a testable helper.
- `TurnOrchestrator._force_text_response()` — extracted the
  "budget exceeded → force LLM text response" logic into a dedicated
  method.

### Changed

- **`TurnInput` is now the single request DTO** — `ChatTurnRequest`
  was eliminated. `TurnInput` flows from `api/chat.py` through
  `ChatService` to `TurnOrchestrator` without transformation.
  `ChatService.handle_turn()` and `stream_turn()` accept `TurnInput`
  directly.
- **History building moved from `TurnOrchestrator` to `ChatService`** —
  the orchestrator returns raw facts (`tool_details`, `token_breakdown`);
  `ChatService` constructs the API history and UI history. This enforces
  a clean boundary: orchestration returns facts, the service persists
  them.
- **`run()` and `stream()` are thin wrappers** — both delegate to
  `_execute_turn(session, turn_input, streaming=bool)`. `run()`
  collects events into `TurnOutput`; `stream()` forwards them as
  SSE-compatible dicts. This eliminates ~250 lines of duplicated
  tool-loop logic.
- **`conversation_total` calculated by `ChatService`** — the
  orchestrator's `TokenBreakdown` no longer includes
  `conversation_total` (always 0). `ChatService` computes it from
  the built history after the turn completes.
- **`FakeOrchestrator` test double returns raw facts** — no longer
  builds `updated_api_history`; returns `tool_details` and
  `token_breakdown` matching the real orchestrator contract.

### Removed

- `ChatTurnRequest` dataclass — replaced by `TurnInput`.
- `ChatService._build_turn_input()` — no longer needed since
  `TurnInput` is used directly.
- `TurnOutput.updated_api_history` — replaced by `TurnOutput.tool_details`.
  History construction is now `ChatService`'s responsibility.
- Duplicated tool-loop code in `TurnOrchestrator.stream()` — replaced
  by the shared `_execute_turn()` generator.
