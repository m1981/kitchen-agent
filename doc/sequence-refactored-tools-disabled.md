# Chat Turn — Refactored — Tools Disabled

## Changes from current architecture
- `ChatTurnRequest` **eliminated** — `TurnInput` is the single DTO (carries `session_id`)
- `TurnOutput` has `tool_details` instead of `updated_api_history` — **raw facts only**
- `ChatService` **owns history building** via `_build_api_history()`
- `TurnOrchestrator._execute_turn()` is a **single generator** — `run()` and `stream()` are thin wrappers

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
    participant Prov as LLMProvider
    participant Norm as ResponseNormalizer

    Client->>API: POST /api/chat<br/>{message, session_id, mode_id,<br/>tools_enabled: false}

    Note over API: Bind request context

    API->>PM: get_system_instruction(mode_id)
    PM-->>API: system_instruction
    API->>PM: get_mode(mode_id)
    PM-->>API: mode_obj

    Note over API: use_tools = false

    rect rgb(255, 240, 255)
        Note over API,TO: Priority 1 — Single DTO<br/>API builds TurnInput directly (no ChatTurnRequest)
        API->>CS: handle_turn(TurnInput{<br/>session_id, user_message,<br/>system_prompt, mode,<br/>images, context_files,<br/>use_tools: false, provider, model})
    end

    rect rgb(255, 240, 240)
        Note over CS,Repo: Phase 1 — Load Session
        CS->>Repo: load_session(turn_input.session_id)
        Repo-->>CS: (api_history_json, ui_history_json, saved_system_prompt)
        CS->>CS: hydrate_history(api_history_json)
    end

    rect rgb(240, 240, 255)
        Note over CS,Prov: Phase 2 — Execute Turn (single generator)
        CS->>TO: run(session, turn_input)

        Note over TO: _resolve_provider(turn_input)
        Note over TO: _setup_context(session, turn_input)

        TO->>CA: assemble(session, mode, user_message)
        CA-->>TO: AssembledContext

        Note over TO: use_tools=false → skip tool_schemas

        TO->>Prov: complete(context)
        Prov-->>TO: raw_response
        TO->>Norm: normalize(raw_response)
        Norm-->>TO: NormalizedResponse

        Note over TO: has_tool_calls + use_tools=false<br/>→ strip tool calls, log warning

        Note over TO: Calculate token_breakdown

        Note over TO: Phase 3 — Citation check (skipped, no tools)
    end

    rect rgb(230, 255, 230)
        Note over CS,Repo: Phase 4 — Build & Persist (ChatService owns this)
        Note over CS: priority 2 — history building moved here
        CS->>CS: _build_api_history(<br/>existing=api_history,<br/>turn_input=turn_input,<br/>output=turn_output)
        Note over CS: Append: user msg → assistant msg<br/>with token counts
        CS->>CS: _build_ui_history(...)
        CS->>Repo: save_session(session_id, title,<br/>dehydrate(api_history), ui_history)
    end

    CS-->>API: ChatTurnResponse
    API-->>Client: 200 OK {text, provider, model, turn_ids}
```

### What changed vs. current

| Aspect | Before | After |
|---|---|---|
| **DTO chain** | `ChatRequest → ChatTurnRequest → TurnInput` | `ChatRequest → TurnInput` |
| **History built by** | `TurnOrchestrator.run()` | `ChatService._build_api_history()` |
| **TurnOutput** | contains `updated_api_history` | contains `tool_details` (raw facts) |
| **run()/stream()** | two separate ~250-line methods | thin wrappers over `_execute_turn()` |
