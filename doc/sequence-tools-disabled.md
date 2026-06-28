# Chat Turn — Tools Disabled

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
    participant Prov as LLMProvider<br/>(Gemini/Anthropic/MiMo)
    participant Norm as ResponseNormalizer

    Client->>API: POST /api/chat<br/>{message, session_id, mode_id,<br/>tools_enabled: false}

    Note over API: Bind request context<br/>(session_id, mode, provider)

    API->>PM: get_system_instruction(mode_id)
    PM-->>API: system_instruction

    API->>PM: get_mode(mode_id)
    PM-->>API: mode_obj (tools_enabled_default)

    Note over API: use_tools = request.tools_enabled<br/>AND mode.tools_enabled_default<br/>→ false

    API->>CS: handle_turn(ChatTurnRequest)

    rect rgb(255, 240, 240)
        Note over CS,Repo: Phase 1 — Load Session
        CS->>Repo: load_session(session_id)
        Repo-->>CS: (api_history_json, ui_history_json, saved_system_prompt)
        CS->>CS: hydrate_history(api_history_json)
        CS->>CS: resolve system_prompt<br/>(request override > saved > None)
    end

    CS->>TO: run(session, TurnInput)

    rect rgb(240, 240, 255)
        Note over TO,Prov: Phase 2 — Resolve Provider
        alt provider override in TurnInput
            TO->>Prov: get_provider(override_name, model)
        else use default
            Note over TO: use self._provider (cached)
        end
    end

    rect rgb(240, 255, 240)
        Note over TO,CA: Phase 3 — Assemble Context
        TO->>CA: assemble(session, mode, user_message)
        CA->>CA: _build_system(mode) — trim to budget
        CA->>CA: _trim_history(messages) — newest-first, fit budget
        CA->>CA: _attach_content(notes, files)
        CA-->>TO: AssembledContext {system_prompt, messages, slots_used}

        Note over TO: Override system_prompt if TurnInput has one
        Note over TO: Propagate images + context_files
        Note over TO: use_tools=false → SKIP tool_schemas injection
    end

    rect rgb(255, 255, 230)
        Note over TO,Prov: Phase 4 — LLM Call (single, no tools)
        TO->>Prov: complete(context)
        Prov-->>TO: raw_response
        TO->>Norm: normalize(raw_response, provider_name)
        Norm-->>TO: NormalizedResponse {text, has_tool_calls?, usage}
    end

    rect rgb(255, 245, 238)
        Note over TO: Phase 5 — Tool Guard
        alt has_tool_calls AND use_tools=false
            Note over TO: ⚠️ LLM hallucinated tools!<br/>Log warning, strip tool calls
            TO->>TO: Force NormalizedResponse(has_tool_calls=false)
        else has_tool_calls=false
            Note over TO: ✅ Expected — text-only response
        end
    end

    Note over TO: Phase 6 — Build TurnOutput
    TO->>TO: Generate user_turn_id, assistant_turn_id
    TO->>TO: Build updated_api_history<br/>(append user + assistant msgs)
    TO->>TO: Calculate token_breakdown

    TO-->>CS: TurnOutput {assistant_message, updated_api_history,<br/>turn_ids, tokens_used, provider_name, model_name}

    rect rgb(245, 245, 245)
        Note over CS: Phase 7 — Persist & Respond
        CS->>CS: _build_ui_history(existing, user + assistant)
        CS->>Repo: save_session(session_id, title,<br/>dehydrate(api_history), ui_history, system_prompt)
        CS->>CS: log_turn(user_message, [], session_id, title)
    end

    CS-->>API: ChatTurnResponse

    API->>API: Convert to ChatResponse<br/>(ToolLog objects, TokenBreakdown)
    API-->>Client: 200 OK {text, provider, model,<br/>user_turn_id, assistant_turn_id}
```

### Key Points (No Tools)

| Aspect | Behavior |
|---|---|
| **LLM calls** | Exactly 1 — `provider.complete(context)` |
| **Tool schemas** | Not injected into context (`tool_schemas=None`) |
| **Hallucinated tools** | Detected and stripped with warning log |
| **Token budget** | Only system prompt + history + content slots |
| **History** | `user → assistant` (2 messages appended) |
| **Latency** | Single LLM round-trip |
