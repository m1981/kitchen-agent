# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Agent file writes could land outside the knowledge base** — `read_file`,
  `edit_file` and `create_file` resolved the model's path with bare
  `Path(filepath)`, i.e. relative to the server's working directory and with no
  jail, while the REST layer resolves against `data_dir`. A path without the
  `data/` prefix silently wrote to the repo root, where nothing in the app can
  see it. The registry now binds `settings.data_dir` (as it already did for
  search), both conventions are accepted, and absolute paths and `..` are
  refused.
- **Write results echoed the requested path, not the resolved one** — a wrong
  path came back as a confident "Successfully created". `create_file` now
  reports the canonical KB-relative path and byte count, `edit_file` reports
  how many occurrences it replaced and warns when that is more than one.
- **Agent edits are now revertible** — the registry passes `backup_dir`, which
  only the REST endpoints did before.

### Added

- `create_file` flags a same-named file elsewhere in the knowledge base, and
  flags an extension that `get_repo_map` / `search_knowledge_base` do not index
  (only `.md`), so the model can tell the user the file will not show up in the
  browser or in later searches.

- **`400 INVALID_ARGUMENT: Function call is missing a thought_signature`** —
  `complete_with_tools()` / `stream_with_tools()` rebuilt the model's
  function-call turn from `ToolCall` and appended it *again*, after
  `complete()` / `_consume_stream()` had already stored the model's own
  `Content`. The duplicate carried no `thought_signature`, which Gemini 3
  thinking models require back on every replayed call. The existing turn is
  now reused (`_ensure_tool_call_turn()`); the rebuild survives as a fallback
  and restores the signature from the stored history.
- **Signatures now survive session storage** — `thought_signature` travels
  `ToolCall` → `ToolCallDetail` → common history (base64) →
  `_coerce_history_for_gemini()`, so follow-up turns replay a valid context.
- **Sessions recorded before that** are no longer a dead end: the missing
  signature 400 is caught once, the unsigned call/result pairs are dropped
  from the replayed context, and the request is retried
  (`gemini_retry_without_unsigned_tool_calls`).

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
