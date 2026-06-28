# Sequence Diagrams — After Refactoring

## Tools Disabled

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant API as api/chat.py
    participant CS as ChatService
    participant Repo as SQLite
    participant TO as TurnOrchestrator
    participant CA as ContextAssembler
    participant Prov as LLMProvider
    participant Norm as Normalizer

    Client->>API: POST /api/chat<br/>{tools_enabled: false}

    Note over API: Single DTO: TurnInput<br/>(no ChatTurnRequest)
    API->>CS: handle_turn(TurnInput)

    rect rgb(255, 240, 240)
        CS->>Repo: load_session(id)
        Repo-->>CS: (api_history, ui_history, system_prompt)
    end

    rect rgb(240, 240, 255)
        Note over TO: run() — thin wrapper
        CS->>TO: run(session, turn_input)
        TO->>TO: _resolve_provider()
        TO->>TO: _setup_context()
        TO->>CA: assemble(...)
        CA-->>TO: AssembledContext

        Note over TO: _execute_turn(streaming=false)
        TO->>Prov: complete(context)
        Prov-->>TO: raw_response
        TO->>Norm: normalize(raw)
        Norm-->>TO: NormalizedResponse

        Note over TO: has_tool_calls + use_tools=false<br/>→ strip tool calls
        Note over TO: Build token_breakdown
        TO->>TO: yield __done__
    end

    TO-->>CS: TurnOutput{text, tool_details, token_breakdown}

    rect rgb(230, 255, 230)
        Note over CS: History building — ChatService owns this
        CS->>CS: _build_api_history(existing, input, output)
        CS->>CS: _build_ui_history(...)
        CS->>Repo: save_session(...)
    end

    CS-->>API: ChatTurnResponse
    API-->>Client: 200 OK
```

## Tools Enabled

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant API as api/chat.py
    participant CS as ChatService
    participant Repo as SQLite
    participant TO as TurnOrchestrator
    participant CA as ContextAssembler
    participant TR as ToolRegistry
    participant TE as ToolExecutor
    participant Prov as LLMProvider
    participant Norm as Normalizer

    Client->>API: POST /api/chat<br/>{tools_enabled: true}

    Note over API: Single DTO: TurnInput
    API->>CS: handle_turn(TurnInput)

    rect rgb(255, 240, 240)
        CS->>Repo: load_session(id)
        Repo-->>CS: (api_history, ui_history, system_prompt)
    end

    rect rgb(240, 240, 255)
        Note over TO: run() — thin wrapper
        CS->>TO: run(session, turn_input)

        TO->>TO: _resolve_provider()
        TO->>TO: _setup_context()
        TO->>CA: assemble(...)
        CA-->>TO: AssembledContext
        TO->>TR: schemas_for_provider()
        TR-->>TO: [FunctionDecl, ...]

        Note over TO: _execute_turn(streaming=false)

        TO->>Prov: complete(context + tools)
        Prov-->>TO: raw_response
        TO->>Norm: normalize(raw)
        Norm-->>TO: NormalizedResponse{has_tool_calls: true}

        loop While has_tool_calls (max 10)
            TO->>TE: execute_all(tool_calls)
            TE-->>TO: [ToolResult, ...]
            Note over TO: Record ToolCallDetail
            Note over TO: Enforce token budget

            TO->>Prov: complete_with_tools(ctx, calls, results)
            Prov-->>TO: raw_response
            TO->>Norm: normalize(raw)
            Norm-->>TO: NormalizedResponse
        end

        Note over TO: Citation check
        Note over TO: Build token_breakdown
        TO->>TO: yield __done__
    end

    TO-->>CS: TurnOutput{text, tool_details[], token_breakdown}

    rect rgb(230, 255, 230)
        Note over CS: History building — ChatService owns this
        CS->>CS: _build_api_history(existing, input, output)
        Note over CS: user → [tool_call→tool_result]* → assistant
        CS->>CS: _build_ui_history(...)
        CS->>Repo: save_session(...)
    end

    CS-->>API: ChatTurnResponse
    API-->>Client: 200 OK
```

## Streaming (same _execute_turn, streaming=true)

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant API as api/chat.py
    participant CS as ChatService
    participant TO as TurnOrchestrator
    participant Prov as LLMProvider

    Client->>API: POST /api/chat/stream

    API->>CS: stream_turn(TurnInput)
    CS->>CS: load session

    CS->>TO: stream(session, turn_input)

    Note over TO: stream() — thin wrapper<br/>forwards _execute_turn events

    TO->>TO: _execute_turn(streaming=true)

    loop _execute_turn generator
        Prov-->>TO: stream chunk
        TO-->>CS: text_delta / tool_call / tool_result
        CS-->>Client: SSE event
    end

    TO-->>CS: done event
    CS->>CS: _build_api_history, persist
    CS-->>Client: SSE: done
```

## Responsibility Map

```
TurnOrchestrator (832 lines → ~250 lines of logic)
├── _resolve_provider()          — 12 lines
├── _setup_context()             — 20 lines
├── _execute_turn()              — 100 lines (THE core, shared by run/stream)
├── _force_text_response()       — 30 lines
├── run()                        — 25 lines (thin wrapper)
├── stream()                     — 30 lines (thin wrapper)
├── _stream_and_collect()        — 30 lines
├── _stream_and_collect_with_tools() — 30 lines
├── _execute_tool_calls()        — existing helper
├── _count_and_truncate()        — existing helper
├── _check_citation_compliance() — existing helper
└── NO history building          ✅ moved to ChatService
└── NO DTO transformation        ✅ TurnInput used directly

ChatService
├── _load_session()              — load + hydrate from repo
├── _build_api_history()         — NEW: builds from TurnOutput raw facts
├── _build_ui_history()          — builds UI messages
├── _persist()                   — serialize + save
├── handle_turn(request: TurnInput)  — sync orchestrator
└── stream_turn(request: TurnInput)  — streaming orchestrator
```
