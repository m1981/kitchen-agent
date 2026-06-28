# Chat Turn — Tools Enabled

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
    participant TC as TokenCounter
    participant TE as ToolExecutor
    participant Prov as LLMProvider<br/>(Gemini/Anthropic/MiMo)
    participant Norm as ResponseNormalizer

    Client->>API: POST /api/chat<br/>{message, session_id, mode_id,<br/>tools_enabled: true}

    Note over API: Bind request context<br/>(session_id, mode, provider)

    API->>PM: get_system_instruction(mode_id)
    PM-->>API: system_instruction

    API->>PM: get_mode(mode_id)
    PM-->>API: mode_obj (tools_enabled_default)

    Note over API: use_tools = request.tools_enabled (true)<br/>AND mode.tools_enabled_default (true)<br/>→ true

    API->>CS: handle_turn(ChatTurnRequest)

    rect rgb(255, 240, 240)
        Note over CS,Repo: Phase 1 — Load Session
        CS->>Repo: load_session(session_id)
        Repo-->>CS: (api_history_json, ui_history_json, saved_system_prompt)
        CS->>CS: hydrate_history(api_history_json)
        CS->>CS: resolve system_prompt
    end

    CS->>TO: run(session, TurnInput{use_tools: true})

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
        CA->>CA: _build_system(mode)
        CA->>CA: _trim_history(messages)
        CA->>CA: _attach_content(notes, files)
        CA-->>TO: AssembledContext {system_prompt, messages, slots_used}

        Note over TO: Override system_prompt if TurnInput has one
        Note over TO: Propagate images + context_files

        Note over TO,TR: 🔧 Inject Tool Schemas
        TO->>TR: schemas_for_provider(provider_name)
        TR-->>TO: [FunctionDeclaration, ...]
        Note over TO: context.tool_schemas = schemas
    end

    rect rgb(255, 255, 230)
        Note over TO,Prov: Phase 4 — Initial LLM Call
        TO->>Prov: complete(context + tool_schemas)
        Prov-->>TO: raw_response (may include tool_calls)
        TO->>Norm: normalize(raw_response, provider_name)
        Norm-->>TO: NormalizedResponse {text, has_tool_calls, tool_calls, usage}
    end

    rect rgb(230, 255, 230)
        Note over TO,Prov: Phase 5 — Agentic Tool Loop

        loop While has_tool_calls (max 10 iterations)
            alt Iteration > max_tool_iterations
                TO-->>CS: ❌ MaxToolIterationsError
            end

            Note over TO: Iteration N — LLM requested tools

            TO->>TE: execute_all(normalized.tool_calls)
            Note over TE: Resolve handler from ToolRegistry<br/>Run each tool function
            TE-->>TO: [ToolResult, ...]

            Note over TO: Record ToolCallDetail<br/>(id, name, args, result, tokens)

            rect rgb(255, 250, 240)
                Note over TO,TC: Token Budget Enforcement
                TO->>TO: _get_tool_budget_tokens()
                alt tool_tokens > budget
                    TO->>TC: trim_to(content, remaining_budget)
                    Note over TO: ⚠️ Truncate result + add warning suffix
                    Note over TO: Zero out remaining results in batch
                    Note over TO: was_truncated = true
                end
            end

            alt was_truncated
                Note over TO: Budget exceeded — force text response
                TO->>Prov: complete_with_tools(context, calls, results)
                Prov-->>TO: raw_response
                TO->>Norm: normalize(raw_response)
                Norm-->>TO: NormalizedResponse

                alt LLM returned more tool_calls OR empty text
                    TO->>TO: _build_truncation_summary(tool_details)
                    Note over TO: Synthetic response from partial results
                else LLM returned text
                    Note over TO: Use LLM text, stop loop
                end

                Note over TO: Break — no more tool iterations
            else Budget OK
                TO->>Prov: complete_with_tools(context, calls, results)
                Prov-->>TO: raw_response (may have more tool_calls)
                TO->>Norm: normalize(raw_response)
                Norm-->>TO: NormalizedResponse
                Note over TO: If has_tool_calls → loop again
            end
        end
    end

    Note over TO: Phase 6 — Citation Compliance Check
    TO->>TO: _check_citation_compliance(text, tool_details)
    Note over TO: Warn if response lacks citations<br/>after using knowledge base tools

    Note over TO: Phase 7 — Build TurnOutput
    TO->>TO: Generate user_turn_id, assistant_turn_id
    TO->>TC: count(user_message), count(assistant_text)
    TO->>TO: Build updated_api_history:<br/>user → [tool_call → tool_result]* → assistant
    TO->>TO: Calculate token_breakdown<br/>(user + tool_calls + tool_results + assistant)
    TO->>TO: _build_output_from_details(tool_details)

    TO-->>CS: TurnOutput {assistant_message, updated_api_history,<br/>turn_ids, tool_calls_made, tool_logs,<br/>tokens_used, token_breakdown}

    rect rgb(245, 245, 245)
        Note over CS: Phase 8 — Persist & Respond
        CS->>CS: _build_ui_history(existing,<br/>user + assistant + tool_logs)
        CS->>Repo: save_session(session_id, title,<br/>dehydrate(api_history), ui_history, system_prompt)
        CS->>CS: log_turn(user_message, tool_logs,<br/>session_id, title)
    end

    CS-->>API: ChatTurnResponse

    API->>API: Convert to ChatResponse<br/>(ToolLog objects, TokenBreakdown)
    API-->>Client: 200 OK {text, tools_used[], provider, model,<br/>user_turn_id, assistant_turn_id,<br/>token_breakdown}
```

### Key Points (With Tools)

| Aspect | Behavior |
|---|---|
| **LLM calls** | 1 + N (where N = tool iterations, max 10) |
| **Tool schemas** | Injected from `ToolRegistry.schemas_for_provider()` |
| **Tool loop** | `complete → execute → complete_with_tools → normalize → repeat` |
| **Token budget** | Per-slot: system prompt, history, notes, files, tool results |
| **Budget exceeded** | Truncate + force text response from partial results |
| **Citation check** | Warns if response lacks `## Źródła` / `[1]` markers after tool use |
| **History** | `user → [tool_call → tool_result]* → assistant` (variable length) |
| **Latency** | Multiple LLM round-trips (1 + N iterations) |

### Tool Loop Detail

```
Iteration 1:  LLM → tool_calls(read_file, search_kb)
              ↓
              ToolExecutor.run(read_file) → file content
              ToolExecutor.run(search_kb) → search results
              ↓
              Check token budget (truncate if needed)
              ↓
              LLM → tool_calls(read_file) or text

Iteration 2:  LLM → tool_calls(read_file)
              ↓
              ToolExecutor.run(read_file) → file content
              ↓
              LLM → text (final answer)

...up to max 10 iterations
```
