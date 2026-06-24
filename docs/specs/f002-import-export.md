# F002: Import/Export Chat Sessions

## Overview

Feature for importing chat sessions from external JSON files (other LLM providers)
and exporting sessions in multiple formats.

**Status**: Implemented (import) + Existing (export)  
**Date**: 2026-06-14  
**Author**: Architecture review + implementation

---

## 1. Critical Architecture Decisions

### 1.1 Dual History Pattern

The system maintains **two parallel history formats** for each session:

| Format             | Location | Purpose                                | Consumers                   |
| ------------------ | -------- | -------------------------------------- | --------------------------- |
| `api_history_json` | SQLite   | Provider-native format for LLM context | TurnOrchestrator, Providers |
| `ui_history_json`  | SQLite   | Frontend-optimized with metadata       | Frontend, Export            |

**Why two formats?**

- API history preserves provider-specific structures (Gemini Content objects, Anthropic Message blocks)
- UI history includes metadata (provider, model, token_count) for frontend display
- Both share `turn_id` (UUID) as the join key

### 1.2 Turn ID as Identity

Every message carries a `turn_id` (UUID) that enables:

- Message editing (`edit_message` by turn_id)
- Message deletion (by turn_id, optionally paired user+assistant)
- Truncation (remove last N turns)
- Fork point identification

**Critical**: Turn IDs must be preserved across all operations.

### 1.3 Import Constraints

Imported chats have specific limitations:

- **No tool calls** — plain text only (role + content)
- **No Gemini Content objects** — must use common format (dict)
- **Provider/model stored as metadata** — not used for LLM routing

---

## 2. Data Flow: Import

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           POST /api/sessions/import                         │
│                                                                             │
│  Input: ImportRequest {                                                     │
│    title?: string              // Optional; auto-generated if absent        │
│    messages: ImportMessage[]   // {role, content, provider?, model?}        │
│    system_prompt?: string      // Optional system prompt                    │
│  }                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ImportService.import_chat()                        │
│                                                                             │
│  1. Validate messages not empty                                             │
│  2. Call _build_histories(messages)                                         │
│  3. Derive title (from first user message or use provided)                  │
│  4. Generate session_id (UUID)                                              │
│  5. Persist via SessionRepository.save_session()                            │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ImportService._build_histories()                       │
│                                                                             │
│  For each message:                                                          │
│    1. Generate turn_id (UUID)                                               │
│    2. Build api_history item: {role, content, turn_id}                      │
│    3. Build ui_history item: {role, content, turn_id, provider, model,      │
│                               token_count}                                  │
│    4. Estimate token_count via TokenCounter.count()                         │
│                                                                             │
│  Returns: (api_history[], ui_history[])                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SessionRepository                                   │
│                                                                             │
│  save_session(                                                              │
│    session_id, title,                                                       │
│    api_history_json = json.dumps(api_history),                              │
│    ui_history_json = json.dumps(ui_history),                                │
│    system_prompt                                                             │
│  )                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Flow: Export

### 3.1 Markdown Export

```
GET /api/sessions/{id}/export
         │
         ▼
ExportService.export_markdown(session_id)
         │
         ├─► SessionRepository.get_export_data(session_id)
         │   └─► Returns: {session_id, title, ui_history_json, ...}
         │
         ├─► json.loads(ui_history_json)
         │
         └─► exporter.export_session_to_markdown(ui_messages, title)
             └─► Returns: Markdown string
```

### 3.2 LLM JSON Export

```
GET /api/sessions/{id}/export/llm
         │
         ▼
ExportService.export_llm_json(session_id, tool_schemas?)
         │
         ├─► SessionRepository.get_export_data(session_id)
         │   └─► Returns: {session_id, title, api_history_json, system_prompt, ...}
         │
         ├─► json.loads(api_history_json)
         │
         └─► exporter.export_session_to_llm_json(api_items, title, ...)
             └─► Returns: {metadata, config, turns}
```

---

## 4. Schema Definitions

### 4.1 Import Schemas (src/schemas.py)

```python
class ImportMessage(BaseModel):
    """Single message in an import payload."""
    role: str  # "user" or "assistant"
    content: str
    model: str | None = None
    provider: str | None = None

class ImportRequest(BaseModel):
    """Request body for POST /api/sessions/import."""
    title: str | None = None
    messages: list[ImportMessage]
    system_prompt: str | None = None

class ImportResponse(BaseModel):
    """Response for POST /api/sessions/import."""
    session_id: str
    title: str
    message_count: int
    turn_count: int
```

### 4.2 Database Schema

```sql
CREATE TABLE sessions (
    id               TEXT PRIMARY KEY,
    title            TEXT,
    api_history_json TEXT,      -- JSON array of provider-agnostic messages
    ui_history_json  TEXT,      -- JSON array of UI-enriched messages
    updated_at       TIMESTAMP,
    parent_id        TEXT,      -- Fork lineage
    fork_turn_index  INTEGER,   -- Fork point
    root_id          TEXT,      -- Tree root
    archived_at      TIMESTAMP, -- Soft delete
    system_prompt    TEXT       -- Per-session override
);
```

### 4.3 History Item Formats

**API History Item** (provider-agnostic):

```json
{
    "role": "user",
    "content": "How to design a kitchen?",
    "turn_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**UI History Item** (enriched for frontend):

```json
{
    "role": "user",
    "content": "How to design a kitchen?",
    "turn_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "provider": "openai",
    "model": "gpt-4",
    "token_count": 42
}
```

---

## 5. Critical Implementation Details

### 5.1 Title Generation

**Location**: `src/title_generator.py`

**Rules**:

- Auto-generated from first user message if not provided
- Truncated to 30 chars + "..." if longer
- Falls back to "New Chat" if no user message found
- Handles missing `content` key gracefully (skips message)

**Used by**:

- `ChatService` (backward-compatible wrapper `_make_title()`)
- `ImportService` (direct import)

### 5.2 Token Counting

**Import**: Uses `TokenCounter.count()` to estimate tokens per message  
**Export**: Does NOT re-count; uses stored `token_count` from ui_history

### 5.3 Provider/Model Metadata

**Storage**: Per-message in ui_history_json  
**Default**: `"imported"` / `"unknown"` when not specified  
**Usage**: Frontend display only; NOT used for LLM routing

---

## 6. API Reference

### 6.1 Import Endpoint

```
POST /api/sessions/import
Content-Type: application/json

Request Body:
{
  "title": "Optional Custom Title",
  "messages": [
    {"role": "user", "content": "Hello", "provider": "openai", "model": "gpt-4"},
    {"role": "assistant", "content": "Hi!", "provider": "openai", "model": "gpt-4"}
  ],
  "system_prompt": "Optional system prompt"
}

Response (201 Created):
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Optional Custom Title",
  "message_count": 2,
  "turn_count": 2
}

Error Responses:
- 400 Bad Request: Empty messages list
- 422 Unprocessable Entity: Invalid schema
- 500 Internal Server Error: Unexpected failure
```

### 6.2 Export Endpoints (Existing)

```
GET /api/sessions/{id}/export
Response: text/markdown (Markdown document)

GET /api/sessions/{id}/export/llm
Response: application/json (LLM replay format)
```

---

## 7. Testing Strategy

### 7.1 Unit Tests (26 tests)

**Location**: `tests/unit/services/test_import_service.py`

| Test Class                    | Coverage                                             |
| ----------------------------- | ---------------------------------------------------- |
| `TestImportChat`              | Main flow, title generation, persistence, validation |
| `TestBuildHistories`          | History format, turn IDs, metadata, serialization    |
| `TestBuildHistoriesEdgeCases` | Unicode, empty content, large imports                |

### 7.2 Contract Tests (15 tests)

**Location**: `tests/integration/test_import_endpoint.py`

| Test Class                  | Coverage                                          |
| --------------------------- | ------------------------------------------------- |
| `TestRequestValidation`     | Missing fields, empty messages, schema validation |
| `TestResponseSchema`        | Required fields, correct types                    |
| `TestErrorHandling`         | 400/500 error responses                           |
| `TestProviderModelMetadata` | Optional fields acceptance                        |

### 7.3 Integration Tests (16 tests)

**Location**: `tests/integration/test_import_roundtrip.py`

| Test Class                   | Coverage                                   |
| ---------------------------- | ------------------------------------------ |
| `TestImportThenList`         | Session appears in list with correct title |
| `TestImportThenExport`       | Markdown and LLM JSON export work          |
| `TestImportThenOperations`   | Delete, update title, archive/unarchive    |
| `TestImportThenFork`         | Fork creates child with truncated history  |
| `TestImportWithSystemPrompt` | System prompt persistence and export       |
| `TestMultipleImports`        | Unique IDs, independent content            |

---

## 8. Future Development Guide

### 8.1 Adding New Import Formats

To support additional input formats (e.g., OpenAI export, Anthropic export):

1. Create format adapter in `src/import_adapters/`
2. Adapter transforms external format → `ImportRequest`
3. Reuse existing `ImportService.import_chat()`
4. Add new endpoint if needed (e.g., `POST /api/sessions/import/openai`)

### 8.2 Adding Tool Call Support

If imported chats need tool calls:

1. Extend `ImportMessage` schema with optional `tool_calls` field
2. Update `_build_histories()` to include tool_calls in api_history
3. Add tool message handling (role="tool", tool_call_id)
4. Update tests

### 8.3 Batch Import

For importing multiple sessions at once:

1. Create `BatchImportRequest` with `sessions: ImportRequest[]`
2. Create `BatchImportResponse` with results per session
3. Use transactions for atomicity
4. Add progress tracking for large imports

### 8.4 Import Validation

Current validation is minimal. Consider adding:

- Message count limits
- Content length limits
- Duplicate detection (idempotency)
- Rate limiting

---

## 9. Known Limitations

| Limitation              | Impact                                        | Workaround                       |
| ----------------------- | --------------------------------------------- | -------------------------------- |
| No tool calls in import | Cannot import agentic chats                   | Export from source as plain text |
| No batch import         | One session at a time                         | Make multiple API calls          |
| Token estimation only   | Approximate token counts                      | Acceptable for most use cases    |
| No deduplication        | Same chat imported twice creates two sessions | Track session IDs externally     |

---

## 10. File Reference

| File                                         | Purpose                        |
| -------------------------------------------- | ------------------------------ |
| `src/import_service.py`                      | Core import logic              |
| `src/title_generator.py`                     | Shared title derivation        |
| `src/schemas.py`                             | ImportRequest/Response schemas |
| `src/api/import_chat.py`                     | HTTP endpoint                  |
| `src/dependencies.py`                        | DI wiring (get_import_service) |
| `src/export_service.py`                      | Export logic (existing)        |
| `src/exporter.py`                            | Export formatters (existing)   |
| `tests/unit/services/test_import_service.py` | Unit tests                     |
| `tests/integration/test_import_endpoint.py`  | Contract tests                 |
| `tests/integration/test_import_roundtrip.py` | Integration tests              |

---

## 11. Diagram Maintenance

When import/export changes:

| Change            | Update                                |
| ----------------- | ------------------------------------- |
| New import format | Add to Section 2 (Data Flow: Import)  |
| New export format | Add to Section 3 (Data Flow: Export)  |
| Schema change     | Update Section 4 (Schema Definitions) |
| New endpoint      | Update Section 6 (API Reference)      |
| New test pattern  | Update Section 7 (Testing Strategy)   |
