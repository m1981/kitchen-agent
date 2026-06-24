# Tool Call Lifecycle — End-to-End Across All Providers

How a tool call flows through the system, from the user pressing Enter to
the LLM receiving the tool result. Every format conversion, every provider
difference, every nuance.

---

## Table of Contents

1. [Overview — The 9 Phases](#1-overview--the-9-phases)
2. [Phase 1: Tool Registration](#2-phase-1-tool-registration)
3. [Phase 2: Schema Conversion](#3-phase-2-schema-conversion)
4. [Phase 3: Sending Tools to the LLM](#4-phase-3-sending-tools-to-the-llm)
5. [Phase 4: LLM Returns Tool Calls](#5-phase-4-llm-returns-tool-calls)
6. [Phase 5: Response Normalization](#6-phase-5-response-normalization)
7. [Phase 6: Tool Execution](#7-phase-6-tool-execution)
8. [Phase 7: Sending Tool Results Back](#8-phase-7-sending-tool-results-back)
9. [Phase 8: History Persistence](#9-phase-8-history-persistence)
10. [Phase 9: Subsequent Turns — History Reload](#10-phase-9-subsequent-turns--history-reload)
11. [Streaming Differences](#11-streaming-differences)
12. [Side-by-Side Format Comparison](#12-side-by-side-format-comparison)
13. [Known Gotchas](#13-known-gotchas)

---

## 1. Overview — The 9 Phases

```
User types message
       │
       ▼
┌──────────────────────┐
│ 1. Tool Registration │  ToolEntry(FunctionDeclaration + fn + category)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 2. Schema Conversion │  ToolRegistry.schemas_for_provider("gemini"|"anthropic"|"mimo")
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 3. Send to LLM       │  provider.complete(context) or provider.stream(context)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 4. LLM Response      │  Raw SDK object (provider-specific shape)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 5. Normalize         │  ResponseNormalizer → NormalizedResponse(tool_calls: list[ToolCall])
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 6. Execute Tools     │  ToolExecutor.execute_all(tool_calls) → list[ToolResult]
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 7. Send Results Back │  provider.complete_with_tools(context, calls, results)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 8. Persist History   │  dehydrate_history → SQLite (common format)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 9. Next Turn Reload  │  hydrate_history → provider._build_messages() → API format
└──────────────────────┘
```

---

## 2. Phase 1: Tool Registration

**File:** `src/tools/registry.py`

Every tool is a `ToolEntry` binding three things:

```python
@dataclass(frozen=True)
class ToolEntry:
    declaration: types.FunctionDeclaration   # Schema sent to Gemini API
    fn: Callable[..., dict]                  # Python implementation
    category: ToolCategory                   # DISCOVERY / FILE_OPERATIONS / SEARCH
```

Five tools are registered:

| Tool                    | Category        | Description                      |
| ----------------------- | --------------- | -------------------------------- |
| `get_repo_map`          | DISCOVERY       | Scan `.md` files, return headers |
| `search_knowledge_base` | SEARCH          | Regex search across all markdown |
| `read_file`             | FILE_OPERATIONS | Read a single file               |
| `edit_file`             | FILE_OPERATIONS | Search-and-replace (exact match) |
| `create_file`           | FILE_OPERATIONS | Create new markdown file         |

**Key design:** `base_dir` is baked into lambdas at registration time — never
exposed to the LLM (path-traversal prevention).

```python
# The LLM sees "filepath": "data/notes.md"
# The actual path is always settings.data_dir / "data/notes.md"
fn=lambda: get_repo_map(base_dir=str(settings.data_dir)),
```

---

## 3. Phase 2: Schema Conversion

**File:** `src/tools/schema_converter.py`

The `ToolRegistry` stores tools as Gemini `FunctionDeclaration` objects.
When the orchestrator requests schemas for a specific provider, conversion
happens via `ToolSchemaConverter`:

### Gemini — No conversion

```python
# Input = output (identity)
types.FunctionDeclaration(
    name="read_file",
    description="Reads a file...",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "filepath": types.Schema(type=types.Type.STRING, description="..."),
        },
        required=["filepath"],
    ),
)
```

### Anthropic — `ToolParam` dict

```python
{
    "name": "read_file",
    "description": "Reads a file...",
    "input_schema": {
        "type": "object",
        "properties": {
            "filepath": {"type": "string", "description": "..."}
        },
        "required": ["filepath"]
    }
}
```

**Difference:** Anthropic uses `input_schema` (not `parameters`), and the
schema is a plain JSON dict (not a typed SDK object).

### Mimo (OpenAI-compatible) — `function` wrapper

```python
{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Reads a file...",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "..."}
            },
            "required": ["filepath"]
        }
    }
}
```

**Difference:** OpenAI wraps everything under `"function"` with a `"type": "function"` discriminator.

### Conversion flow

```
ToolRegistry.schemas_for_provider(provider="mimo")
  └─ ToolSchemaConverter.to_openai_compat(declaration)
       └─ _schema_to_dict(declaration.parameters)  # recursive Schema → dict
```

---

## 4. Phase 3: Sending Tools to the LLM

Each provider wraps tools differently in the API call.

### Gemini

```python
gemini_tools = types.Tool(function_declarations=declarations)
config = types.GenerateContentConfig(
    tools=[gemini_tools],
    system_instruction=context.system_prompt,
    temperature=0.2,
)
response = client.models.generate_content(
    model="gemini-3.1-pro-preview",
    contents=self._conversation_state,   # list[types.Content]
    config=config,
)
```

**Nuance:** Tools are wrapped in `types.Tool(function_declarations=[...])`.
System instruction is a separate config field.

### Anthropic

```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=8096,
    tools=tool_schemas,              # list[dict] — ToolParam format
    messages=self._conversation_state,  # list[dict]
    system=context.system_prompt,     # top-level kwarg
)
```

**Nuance:** `system` is a top-level kwarg (not inside messages).
`max_tokens` is required (Gemini doesn't need it).

### Mimo (OpenAI-compatible)

```python
response = client.chat.completions.create(
    model="mimo-v2.5-pro",
    messages=self._conversation_state,  # list[dict]
    tools=tool_schemas,                 # list[dict] — function-calling format
    temperature=0.2,
    max_tokens=8096,
)
```

**Nuance:** `tools` is a direct list (not wrapped like Gemini's `types.Tool`).
System prompt is the first message with `role: "system"` (not a separate kwarg).

---

## 5. Phase 4: LLM Returns Tool Calls

This is where provider formats diverge the most.

### Gemini — `function_call` parts

```python
response.candidates[0].content = types.Content(
    role="model",
    parts=[
        types.Part(
            function_call=types.FunctionCall(
                name="search_knowledge_base",
                args={"query": "hinge|blum"},
                id="call-abc123",           # Gemini adds IDs
            )
        )
    ]
)
```

**Nuance:**

- Tool calls are `Part` objects inside a `Content`
- `args` is a dict (not a JSON string)
- `id` is optional; Gemini generates it when tools have `id` support
- Role is `"model"` (not `"assistant"`)

### Anthropic — `tool_use` blocks

```python
response.content = [
    TextBlock(type="text", text="Let me search..."),
    ToolUseBlock(
        type="tool_use",
        id="toolu_abc123",
        name="search_knowledge_base",
        input={"query": "hinge|blum"},      # dict, not JSON string
    )
]
```

**Nuance:**

- Tool calls are blocks in `response.content` alongside text blocks
- `input` is a dict (not a JSON string)
- Can mix text and tool calls in a single response
- `id` always present (generated by Anthropic)

### Mimo (OpenAI-compatible) — `tool_calls` array

```python
response.choices[0].message = ChatCompletionMessage(
    content="Let me search...",        # or None
    tool_calls=[
        ChoiceToolCall(
            id="call_abc123",
            type="function",
            function=Function(
                name="search_knowledge_base",
                arguments='{"query": "hinge|blum"}',  # JSON STRING, not dict
            )
        )
    ]
)
```

**Nuance:**

- `arguments` is a **JSON string** (not a dict) — this is unique to OpenAI format
- `tool_calls` is a separate field on the message (not inside content)
- `type: "function"` discriminator on each tool call
- Can have `content` AND `tool_calls` simultaneously

---

## 6. Phase 5: Response Normalization

**File:** `src/providers/normalizer.py`

All provider responses are converted to a single shape:

```python
@dataclass
class NormalizedResponse:
    text: str
    has_tool_calls: bool
    tool_calls: list[ToolCall]     # always: id, name, arguments (dict)
    usage: dict                    # always: {input, output, total}
    raw: Any                       # original SDK object
```

### Provider-specific extraction logic

| Provider  | Text source                       | Tool call extraction                               | Arguments conversion                        |
| --------- | --------------------------------- | -------------------------------------------------- | ------------------------------------------- |
| Gemini    | `part.text` in parts              | `part.function_call.{name, args, id}`              | `dict(fc.args)` (already dict)              |
| Anthropic | `block.text` where `type=="text"` | `block.{id, name, input}` where `type=="tool_use"` | `block.input` (already dict)                |
| Mimo      | `message.content`                 | `tc.{id, function.name, function.arguments}`       | `json.loads(arguments)` (parse JSON string) |

**Key normalization:** Mimo's `arguments` JSON string is parsed to a dict
so that `ToolCall.arguments` is always a dict regardless of provider.

### Usage extraction

| Provider  | Source                                                                                    |
| --------- | ----------------------------------------------------------------------------------------- |
| Gemini    | `response.usage_metadata.{prompt_token_count, candidates_token_count, total_token_count}` |
| Anthropic | `response.usage.{input_tokens, output_tokens}`                                            |
| Mimo      | `response.usage.{prompt_tokens, completion_tokens}`                                       |

---

## 7. Phase 6: Tool Execution

**File:** `src/agent/tool_executor.py`

Provider-agnostic. Takes `list[ToolCall]`, returns `list[ToolResult]`.

```python
@dataclass
class ToolCall:
    id: str           # provider-generated ID (e.g., "call-abc123")
    name: str         # tool name (e.g., "search_knowledge_base")
    arguments: dict   # always a dict after normalization

@dataclass
class ToolResult:
    tool_call_id: str  # same ID from the ToolCall
    name: str          # tool name
    content: str       # str(dict) — always a string
    is_error: bool = False
```

**Execution flow:**

```python
handler = registry.get_handler(tool_call.name)  # → search_knowledge_base
result = handler(**tool_call.arguments)           # → {"content": "..."}
return ToolResult(
    tool_call_id=tool_call.id,
    name=tool_call.name,
    content=str(result),       # "{'content': '...'}"
    is_error=False,
)
```

**Error safety:** Any exception is caught and wrapped:

```python
ToolResult(
    tool_call_id=tool_call.id,
    name=tool_call.name,
    content=f"Tool error: {type(e).__name__}: {e}",
    is_error=True,
)
```

---

## 8. Phase 7: Sending Tool Results Back

This is the **most divergent** part across providers.

### Gemini — `function_response` parts

```python
# Tool call message (assistant/model role)
tool_call_content = types.Content(
    role="model",
    parts=[
        types.Part(function_call=types.FunctionCall(
            name="search_knowledge_base",
            args={"query": "hinge"},
            id="call-abc123",
        ))
    ]
)

# Tool result message (user role!)
tool_result_content = types.Content(
    role="user",                           # ← USER role, not "model"
    parts=[
        types.Part(function_response=types.FunctionResponse(
            name="search_knowledge_base",   # function name repeated
            response={"content": "..."},    # dict, not string
            id="call-abc123",               # links to function_call.id
        ))
    ]
)
```

**Nuances:**

- Tool results use **role `"user"`** (not `"model"` or `"tool"`)
- Tool call message must also be sent (role `"model"`)
- `response` is a **dict** (not a string)
- `name` on the response must match the function name
- Both messages are `types.Content` SDK objects

### Anthropic — `tool_result` blocks in a user message

```python
# Tool call message (already in conversation from the LLM response)
assistant_content = [
    {"type": "text", "text": "Let me search..."},
    {"type": "tool_use", "id": "toolu_abc123", "name": "search_knowledge_base", "input": {...}},
]

# Tool result message (user role with tool_result blocks)
tool_result_message = {
    "role": "user",
    "content": [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_abc123",    # links to tool_use.id
            "content": "{'content': '...'}",   # string
        }
    ]
}
```

**Nuances:**

- Tool results are `{"type": "tool_result"}` blocks inside a `"role": "user"` message
- `tool_use_id` links to the `tool_use.id` from the assistant message
- `content` is a **string** (not a dict)
- The assistant message with tool calls is already in `_conversation_state` from step 4
- Messages are plain dicts (not SDK objects)

### Mimo (OpenAI-compatible) — separate `tool` role message

```python
# Tool call message (already in conversation from the LLM response)
assistant_message = {
    "role": "assistant",
    "content": "Let me search...",
    "tool_calls": [
        {
            "id": "call-abc123",
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "arguments": '{"query": "hinge"}',  # JSON string!
            }
        }
    ]
}

# Tool result message
tool_result_message = {
    "role": "tool",                        # ← dedicated "tool" role
    "tool_call_id": "call-abc123",         # links to tool_calls[].id
    "content": "{'content': '...'}",       # string
}
```

**Nuances:**

- Tool results use a **dedicated `"tool"` role** (not `"user"` like Gemini/Anthropic)
- `tool_call_id` links to `tool_calls[].id` in the assistant message
- `arguments` in the assistant message must be a **JSON string** (not dict)
- Messages are plain dicts

### Side-by-side: Tool result message format

| Aspect                          | Gemini                     | Anthropic                  | Mimo (OpenAI)    |
| ------------------------------- | -------------------------- | -------------------------- | ---------------- |
| **Role**                        | `"user"`                   | `"user"`                   | `"tool"`         |
| **ID field name**               | `id` (on FunctionResponse) | `tool_use_id`              | `tool_call_id`   |
| **Content type**                | `dict`                     | `string`                   | `string`         |
| **Content location**            | `response` kwarg           | `content` field            | `content` field  |
| **Message type**                | `types.Content` (SDK)      | `dict`                     | `dict`           |
| **Requires tool call msg?**     | Yes (role="model")         | Already in state           | Already in state |
| **tool_calls on assistant msg** | Part.function_call         | content[].type=="tool_use" | `tool_calls` key |

---

## 9. Phase 8: History Persistence

**File:** `src/serializers.py`

After the turn completes, `TurnOrchestrator.run()` builds
`updated_api_history` in **common format**:

```python
updated_api_history = list(session.get("messages", []))
updated_api_history.append({"role": "user", "content": "Find info about hinges"})

for detail in tool_details:
    updated_api_history.append({
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": detail.id,
            "name": detail.name,
            "arguments": detail.arguments,     # dict (not JSON string)
        }],
    })
    updated_api_history.append({
        "role": "tool",
        "tool_call_id": detail.id,
        "content": detail.result_content,      # string
    })

updated_api_history.append({"role": "assistant", "content": "Here's what I found..."})
```

**Common format** (what gets stored in SQLite):

```json
[
    { "role": "user", "content": "Find info about hinges", "turn_id": "uuid-1" },
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-abc123",
                "name": "search_knowledge_base",
                "arguments": { "query": "hinge" }
            }
        ],
        "turn_id": "uuid-2"
    },
    {
        "role": "tool",
        "tool_call_id": "call-abc123",
        "content": "{'content': '=== data/hinges.md ===...'}",
        "turn_id": "uuid-2"
    },
    { "role": "assistant", "content": "Here's what I found about hinges...", "turn_id": "uuid-3" }
]
```

**Key: common format uses:**

- `role: "tool"` (OpenAI convention)
- `tool_call_id` (OpenAI convention)
- `arguments` as **dict** (not JSON string)
- Extra fields (`turn_id`, `provider`, `model`) are stored but not part of the API format

### Serialization (dehydrate)

`dehydrate_history()` ensures every message has a `turn_id`:

```python
def dehydrate_history(history: list) -> str:
    for item in history:
        if "turn_id" not in item:
            item["turn_id"] = str(uuid.uuid4())
    return json.dumps(history)
```

---

## 10. Phase 9: Subsequent Turns — History Reload

This is where **the bug was** (fixed in `58b98c1`). When a new turn starts,
the persisted common-format history must be converted back to each
provider's native format.

### Flow

```
SQLite → hydrate_history() → common format dicts
  → ContextAssembler.assemble() → AssembledContext.messages
    → provider._build_messages() → provider-native format
```

### Gemini — `_coerce_history_for_gemini()`

**File:** `src/providers/gemini.py`

Converts common format dicts to `types.Content` objects:

| Common format                                | Gemini format                                                     |
| -------------------------------------------- | ----------------------------------------------------------------- |
| `{"role": "user", "content": "..."}`         | `types.Content(role="user", parts=[Part(text="...")])`            |
| `{"role": "assistant", "content": "..."}`    | `types.Content(role="model", parts=[Part(text="...")])`           |
| `{"role": "assistant", "tool_calls": [...]}` | `types.Content(role="model", parts=[Part(function_call=...)])`    |
| `{"role": "tool", "tool_call_id": "..."}`    | `types.Content(role="user", parts=[Part(function_response=...)])` |

**Key mappings:**

- `"assistant"` → `"model"` (Gemini uses "model" role)
- `"tool"` → `"user"` (Gemini uses "user" for tool responses)
- `tool_call_id` → FunctionResponse.id
- `arguments` dict → FunctionCall.args (stays as dict)

### Anthropic — `_common_to_anthropic()`

**File:** `src/providers/anthropic_provider.py`

Converts common format dicts to Anthropic message format:

| Common format                                | Anthropic format                                                                       |
| -------------------------------------------- | -------------------------------------------------------------------------------------- |
| `{"role": "user", "content": "..."}`         | `{"role": "user", "content": "..."}`                                                   |
| `{"role": "assistant", "content": "..."}`    | `{"role": "assistant", "content": "..."}`                                              |
| `{"role": "assistant", "tool_calls": [...]}` | `{"role": "assistant", "content": [{"type": "text", ...}, {"type": "tool_use", ...}]}` |
| `{"role": "tool", "tool_call_id": "..."}`    | `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "..."}]}`         |

**Key mappings:**

- `tool_calls[].id` → `tool_use.id`
- `tool_calls[].arguments` dict → `tool_use.input` (stays as dict)
- `tool_call_id` → `tool_use_id`
- `role: "tool"` → `role: "user"` (Anthropic uses "user" for tool results)

### Mimo — `_common_to_openai()`

**File:** `src/providers/mimo_provider.py`

Converts common format dicts to OpenAI message format:

| Common format                                | OpenAI format                                                                                                           |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `{"role": "user", "content": "..."}`         | `{"role": "user", "content": "..."}`                                                                                    |
| `{"role": "assistant", "content": "..."}`    | `{"role": "assistant", "content": "..."}`                                                                               |
| `{"role": "assistant", "tool_calls": [...]}` | `{"role": "assistant", "content": null, "tool_calls": [{"id", "type": "function", "function": {"name", "arguments"}}]}` |
| `{"role": "tool", "tool_call_id": "..."}`    | `{"role": "tool", "tool_call_id": "...", "content": "..."}`                                                             |

**Key mappings:**

- `tool_calls[].arguments` dict → `function.arguments` **JSON string** (`json.dumps()`)
- `tool_calls[].name` → `function.name` (nested under `function`)
- Added `"type": "function"` discriminator
- `role: "tool"` stays `"tool"` (same convention)
- Extra fields (`turn_id`) stripped

---

## 11. Streaming Differences

### Chunk structure

| Aspect            | Gemini                                      | Anthropic                                         | Mimo (OpenAI)                                            |
| ----------------- | ------------------------------------------- | ------------------------------------------------- | -------------------------------------------------------- |
| **Text delta**    | `chunk.candidates[0].content.parts[0].text` | `chunk.delta.text` (when `type=="text_delta"`)    | `chunk.choices[0].delta.content`                         |
| **Tool calls**    | In final chunk only (same as non-streaming) | In final message via `stream.get_final_message()` | Accumulated across chunks via `delta.tool_calls[].index` |
| **Final message** | Last chunk has full content                 | `get_final_message()` after stream ends           | Accumulated from all chunks                              |

### Mimo tool call accumulation

```python
# Tool calls arrive incrementally across chunks
accumulated_tool_calls: dict[int, dict] = {}

for chunk in stream:
    if chunk.choices[0].delta.tool_calls:
        for tc in chunk.choices[0].delta.tool_calls:
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
```

**Nuance:** Tool call fields arrive **incrementally** — `name` and `arguments`
are built up across multiple chunks. The `id` usually arrives in the first chunk.

### Event types yielded by `TurnOrchestrator.stream()`

```python
yield {"type": "text_delta", "content": "..."}
yield {"type": "tool_call", "name": "...", "args": {...}, "id": "..."}
yield {"type": "tool_result", "name": "...", "result": {...}, "id": "..."}
yield {"type": "done", "provider": "...", "model": "...", ...}
```

---

## 12. Side-by-Side Format Comparison

### Tool schema sent to LLM

```jsonc
// Gemini: types.FunctionDeclaration (SDK object)
// → wrapped in types.Tool(function_declarations=[...])

// Anthropic: dict
{
  "name": "read_file",
  "description": "Reads a file...",
  "input_schema": { "type": "object", "properties": { "filepath": {"type": "string"} }, "required": ["filepath"] }
}

// Mimo: dict
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Reads a file...",
    "parameters": { "type": "object", "properties": { "filepath": {"type": "string"} }, "required": ["filepath"] }
  }
}
```

### LLM response with tool call

```jsonc
// Gemini: types.Content with function_call part
Content(role="model", parts=[
  Part(function_call=FunctionCall(name="read_file", args={"filepath": "data/notes.md"}, id="call-1"))
])

// Anthropic: mixed content blocks
{
  "role": "assistant",
  "content": [
    {"type": "text", "text": "Let me read that file."},
    {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"filepath": "data/notes.md"}}
  ]
}

// Mimo: message with tool_calls field
{
  "role": "assistant",
  "content": "Let me read that file.",
  "tool_calls": [
    {"id": "call-1", "type": "function", "function": {"name": "read_file", "arguments": "{\"filepath\":\"data/notes.md\"}"}}
  ]
}
```

### Tool result sent back to LLM

```jsonc
// Gemini: function_response in user Content
Content(role="user", parts=[
  Part(function_response=FunctionResponse(
    name="read_file",
    response={"content": "# Notes\nSome content..."},
    id="call-1"
  ))
])

// Anthropic: tool_result in user message
{
  "role": "user",
  "content": [
    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "{'content': '# Notes\nSome content...'}"}
  ]
}

// Mimo: dedicated tool role message
{
  "role": "tool",
  "tool_call_id": "call-1",
  "content": "{'content': '# Notes\nSome content...'}"
}
```

### Persisted common format (SQLite)

```jsonc
// All providers use this single format
[
    { "role": "user", "content": "Read the notes file", "turn_id": "uuid-1" },
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            { "id": "call-1", "name": "read_file", "arguments": { "filepath": "data/notes.md" } }
        ],
        "turn_id": "uuid-2"
    },
    {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": "{'content': '# Notes...'}",
        "turn_id": "uuid-2"
    },
    { "role": "assistant", "content": "Here are your notes...", "turn_id": "uuid-3" }
]
```

---

## 13. Known Gotchas

### 1. `arguments` type inconsistency

| Context                                          | Type             |
| ------------------------------------------------ | ---------------- |
| `ToolCall.arguments` (normalized)                | `dict`           |
| Common format (persisted)                        | `dict`           |
| Gemini `FunctionCall.args`                       | `dict`           |
| Anthropic `tool_use.input`                       | `dict`           |
| OpenAI `function.arguments`                      | **`str` (JSON)** |
| OpenAI `tool_calls[].arguments` on assistant msg | **`str` (JSON)** |

**Impact:** When converting common format → OpenAI format, you MUST
`json.dumps(arguments)`. When converting OpenAI → normalized, you MUST
`json.loads(arguments)`.

### 2. Role naming

| Role         | Gemini    | Anthropic     | OpenAI (Mimo) | Common format |
| ------------ | --------- | ------------- | ------------- | ------------- |
| LLM response | `"model"` | `"assistant"` | `"assistant"` | `"assistant"` |
| Tool result  | `"user"`  | `"user"`      | `"tool"`      | `"tool"`      |

Common format uses OpenAI conventions (`"assistant"`, `"tool"`).

### 3. Tool call message required

When sending tool results back:

- **Gemini:** You MUST send both the tool call message (role="model") AND the tool result message (role="user")
- **Anthropic:** The tool call is already in `_conversation_state` from the LLM response; you only append the tool result
- **Mimo:** The tool call is already in `_conversation_state` from the LLM response; you only append the tool result

### 4. System prompt location

| Provider  | Location                                                  |
| --------- | --------------------------------------------------------- |
| Gemini    | `config.system_instruction` (GenerateContentConfig kwarg) |
| Anthropic | `system` kwarg on `messages.create()`                     |
| Mimo      | First message with `role: "system"`                       |

### 5. The `tool_call_id` bug (fixed)

**Bug:** `MimoProvider._build_messages()` did `{"role": role, "content": content}`,
dropping `tool_calls` and `tool_call_id` from persisted history.

**Fix:** Added `_common_to_openai()` that properly converts:

- `tool_calls` → OpenAI format with `type: "function"` wrapper
- `arguments` dict → JSON string via `json.dumps()`
- `tool_call_id` preserved on tool result messages

**Prevention:** All providers must have a format converter:

- Gemini: `_coerce_history_for_gemini()`
- Anthropic: `_common_to_anthropic()`
- Mimo: `_common_to_openai()`

### 6. Content type in tool results

| Provider                           | `content`/`response` type |
| ---------------------------------- | ------------------------- |
| Gemini `FunctionResponse.response` | `dict`                    |
| Anthropic `tool_result.content`    | `str`                     |
| OpenAI `tool` message `content`    | `str`                     |
| Common format                      | `str`                     |

Gemini needs `ast.literal_eval()` or `json.loads()` to convert the
persisted string back to a dict for `FunctionResponse.response`.

---

## Diagram: Format Conversions

```
                    ┌─────────────────────────┐
                    │    Common Format         │
                    │  (persisted in SQLite)   │
                    │                          │
                    │  role: "assistant"       │
                    │  tool_calls: [...]       │
                    │  arguments: dict         │
                    │  role: "tool"            │
                    │  tool_call_id: "..."     │
                    └────────┬────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
   │    Gemini    │ │  Anthropic   │ │  Mimo (OAI)  │
   │              │ │              │ │              │
   │ role→"model" │ │ role→"user"  │ │ role→"tool"  │
   │ args→dict    │ │ input→dict   │ │ args→JSON str│
   │ SDK objects  │ │ plain dicts  │ │ plain dicts  │
   │              │ │              │ │              │
   │ tool result: │ │ tool result: │ │ tool result: │
   │ role="user"  │ │ role="user"  │ │ role="tool"  │
   │ response=dict│ │ content=str  │ │ content=str  │
   └──────────────┘ └──────────────┘ └──────────────┘
```
