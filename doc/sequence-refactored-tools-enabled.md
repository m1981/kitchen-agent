# Chat Turn — Refactored — Tools Enabled

## Architecture changes (same as tools-disabled diagram)
1. `ChatTurnRequest` eliminated — `TurnInput` is single DTO
2. `TurnOutput` returns raw `tool_details`, NOT `updated_api_history`
3. `ChatService` owns history building
4. `TurnOrchestrator._execute_turn()` is unified generator

```mermaid
sequenceDiagram
    autonumber
    participant Client as Frontend
    participant API as api/chat.py
    participant PM as PromptManager
    participant CS as ChatService
    participant Repo as SessionRepository<br/>(SQLite)
    participant TO as TurnOrchestrator
    participant CA as ContextAssembler
    participant TR as ToolRegistry
    participant TE as ToolExecutor
    participant TC as TokenCounter
    participant Prov as LLMProvider
    participant Norm as ResponseNormalizer

    Client->>API: POST /api/chat<br/>{message, session_id, mode_id,<br/>tools_enabled: true}

    Note over API: use_tools = request AND mode default → true

    rect rgb(255, 240, 255)
        Note over API,CS: Priority 1 — Single DTO
        API->>CS: handle_turn(TurnInput{<br/>session_id, user_message,<br/>use_tools: true, ...})
    end

    rect rgb(255, 240, 240)
        Note over CS,Repo: Phase 1 — Load Session
        CS->>Repo: load_session(session_id)
        Repo-->>CS: (api_history_json, ui_history_json, saved_system_prompt)
        CS->>CS: hydrate_history(api_history_json)
    end

    rect rgb(240, 240, 255)
        Note over CS,Prov: Phase 2 — Execute Turn

        CS->>TO: run(session, turn_input)
        Note over TO: run() is a thin wrapper:<br/>collects _execute_turn() events<br/>→ builds TurnOutput

        Note over TO: _resolve_provider(turn_input)
        Note over TO: _setup_context(session, turn_input)

        TO->>CA: assemble(session, mode, user_message)
        CA-->>TO: AssembledContext

        TO->>TR: schemas_for_provider(provider_name)
        TR-->>TO: [FunctionDeclaration, ...]
        Note over TO: context.tool_schemas = schemas

        Note over TO: ── _execute_turn generator ──

        TO->>Prov: complete(context + tool_schemas)
        Prov-->>TO: raw_response
        TO->>Norm: normalize(raw_response)
        Norm-->>TO: NormalizedResponse{has_tool_calls: true}

        loop While has_tool_calls (max 10)
            TO->>TE: execute_all(tool_calls)
            TE-->>TO: [ToolResult, ...]

            Note over TO: Record ToolCallDetail<br/>(id, name, args, result, tokens)

            Note over TO,TC: Token budget enforcement
            TO->>TC: count(result.content)
            alt over budget
                TO->>TC: trim_to(content, remaining)
                Note over TO: was_truncated = true → stop loop
            end

            alt was_truncated
                TO->>Prov: complete_with_tools(context, calls, results)
                Prov-->>TO: raw_response
                Note over TO: Force text or build<br/>_build_truncation_summary()
            else budget OK
                TO->>Prov: complete_with_tools(context, calls, results)
                Prov-->>TO: raw_response (may have more tool_calls)
                TO->>Norm: normalize(raw_response)
                Norm-->>TO: NormalizedResponse
            end
        end

        Note over TO: Citation compliance check
        Note over TO: Calculate token_breakdown
    end

    TO-->>CS: TurnOutput {<br/>assistant_message,<br/>tool_calls_made,<br/>tool_details (raw),<br/>tool_logs,<br/>token_breakdown,<br/>provider_name, model_name}

    rect rgb(230, 255, 230)
        Note over CS,Repo: Phase 3 — Build & Persist<br/>(ChatService owns this — Priority 2)

        CS->>CS: _build_api_history(<br/>existing=api_history,<br/>turn_input=turn_input,<br/>output=turn_output)
        Note over CS: Append: user →<br/>[assistant(tool_call) → tool(result)]* →<br/>assistant(text)

        CS->>CS: _build_ui_history(<br/>existing=ui_history,<br/>turn_input=turn_input,<br/>output=turn_output)
        Note over CS: Append: user entry +<br/>assistant entry with tool_logs

        CS->>Repo: save_session(session_id, title,<br/>dehydrate(api_history), ui_history)
        CS->>CS: log_turn(user_message, tool_logs)
    end

    CS-->>API: ChatTurnResponse
    API-->>Client: 200 OK {text, tools_used[], provider, model,<br/>user_turn_id, assistant_turn_id, token_breakdown}
```

## Streaming path (Priority 3 — same `_execute_turn()`)

```mermaid
sequenceDiagram
    autonumber
    participant Client as Frontend
    participant API as api/chat.py
    participant CS as ChatService
    participant TO as TurnOrchestrator
    participant Prov as LLMProvider

    Client->>API: POST /api/chat/stream

    rect rgb(255, 240, 255)
        Note over API,CS: Same DTO path (TurnInput)
        API->>CS: stream_turn(TurnInput)
    end

    CS->>CS: load session, build TurnInput

    CS->>TO: stream(session, turn_input)
    Note over TO: stream() is a thin wrapper:<br/>forwards _execute_turn() events

    TO->>TO: _execute_turn(session, turn_input,<br/>streaming=true)

    loop For each _execute_turn event
        alt text_delta
            TO-->>CS: {"type": "text_delta", "content": "..."}
            CS-->>Client: SSE: {"type": "text", "content": "..."}
        else tool_call
            TO-->>CS: {"type": "tool_call", "name": "..."}
            CS-->>Client: SSE: {"type": "tool_call", ...}
        else tool_result
            TO-->>CS: {"type": "tool_result", "name": "..."}
            CS-->>Client: SSE: {"type": "tool_result", ...}
        else __done__ (internal)
            Note over TO: Converts to "done" event
            TO-->>CS: {"type": "done", ...}
        end
    end

    Note over CS: Phase 3 — Build & Persist<br/>(same as sync path)

    CS-->>Client: SSE: {"type": "done", ...}
    CS->>CS: _build_api_history, _build_ui_history
    CS->>CS: save_session
```

## What the unified `_execute_turn()` looks like

```
_execute_turn(session, turn_input, *, streaming=False):

    # ── Setup (shared) ──────────────────────────────────────────
    provider, provider_name = _resolve_provider(turn_input)
    context = _setup_context(session, turn_input)

    # ── Initial LLM call ────────────────────────────────────────
    if streaming:
        for event in _stream_llm(context, provider, provider_name):
            if event is __normalized__: normalized = event.response
            else: yield event          # text_delta to caller
    else:
        raw = provider.complete(context)
        normalized = normalizer.normalize(raw)

    # ── Tool loop (shared structure) ────────────────────────────
    while normalized.has_tool_calls and use_tools:
        iterations += 1; guard max_iterations

        calls, results = _execute_tool_calls(normalized, tool_details)
        results, was_truncated = _enforce_budget(results, ...)

        for tc, tr in zip(calls, results):
            yield {"type": "tool_call", ...}
            yield {"type": "tool_result", ...}

        if was_truncated:
            # force text response
            break

        if streaming:
            for event in _stream_llm_with_tools(context, calls, results, ...):
                if event is __normalized__: normalized = event.response
                else: yield event
        else:
            raw = provider.complete_with_tools(context, calls, results)
            normalized = normalizer.normalize(raw)

    # ── Done signal ─────────────────────────────────────────────
    yield {"type": "__done__", "text": ..., "tool_details": ..., ...}
```

## Responsibility map after refactoring

```
┌─────────────────────────────────────────────────────────────────┐
│ TurnOrchestrator                                                │
│  ✅ _resolve_provider()     — provider override vs default      │
│  ✅ _setup_context()        — assemble + inject tool schemas    │
│  ✅ _execute_turn()         — unified generator (the real work) │
│  ✅ run()                   — thin wrapper: collect events       │
│  ✅ stream()                — thin wrapper: forward events       │
│  ✅ _execute_tool_calls()   — tool dispatch + detail recording   │
│  ✅ _enforce_budget()       — token budget for tool results      │
│  ✅ _check_citation_compliance() — quality check (log only)      │
│                                                                 │
│  ❌ NO history building     — moved to ChatService               │
│  ❌ NO session persistence  — already in ChatService             │
│  ❌ NO DTO transformation   — TurnInput used directly            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ ChatService                                                     │
│  ✅ _load_session()         — load + hydrate from repo           │
│  ✅ _build_api_history()    — NEW: builds from TurnOutput raw    │
│  ✅ _build_ui_history()     — builds UI messages                  │
│  ✅ _persist()              — serialize + save + log              │
│  ✅ handle_turn()           — sync path orchestrator              │
│  ✅ stream_turn()           — streaming path orchestrator         │
│                                                                 │
│  ❌ NO DTO transformation   — takes TurnInput directly           │
│  ❌ NO _build_turn_input()  — eliminated                         │
└─────────────────────────────────────────────────────────────────┘
```
