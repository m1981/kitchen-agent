# System Overview — Kitchen Agent

## What This Is

Kitchen Agent is a **minimal-looping LLM agent** designed as a domain-specific knowledge worker. It is NOT a general-purpose autonomous agent. It follows a tight, predictable cycle:

```
User asks → Agent searches KB → Agent responds from expertise + KB → Optionally updates KB
```

The LLM does not plan multi-step strategies, spawn sub-agents, or reason about complex tool chains. It is a **chat with tools** — specifically, a chat that can read and write markdown files in a knowledge base.

---

## The Four Capabilities

### 1. Role-Specific Prompt

Each conversation starts with a **system prompt** that defines the LLM's persona and expertise. The system has three modes:

| Mode       | Persona           | Use Case                             |
| ---------- | ----------------- | ------------------------------------ |
| `general`  | Versatile advisor | SOPs, pricing, templates             |
| `design`   | Kitchen designer  | Ergonomics, layouts, materials       |
| `assembly` | Master carpenter  | Build instructions, hardware fitting |

The system prompt is assembled from two parts:

- **Base rules** (`base_agent_rules.md`) — universal instructions: how to search, how to cite, critical rules
- **Mode content** (`general.md`, `design.md`, `assembly.md`) — persona-specific expertise and behavior

The key design principle: **the LLM uses its own expertise as the base; the knowledge base provides company-specific modifiers, not replacements.** The LLM knows how hinges work — the KB tells it which specific Blum part numbers this company uses and at what price.

### 2. Search & Consume Content

The agent has five tools, but for knowledge-base work only three matter:

| Tool                    | Category        | Purpose                                                                                     |
| ----------------------- | --------------- | ------------------------------------------------------------------------------------------- |
| `get_repo_map`          | Discovery       | List all KB files and their headings — use FIRST when the user doesn't specify a file       |
| `search_knowledge_base` | Search          | Regex search across all markdown files — returns file paths, line numbers, matching content |
| `read_file`             | File Operations | Read a specific file's full content                                                         |

The search tool is the primary knowledge retrieval mechanism. It:

- Uses regex patterns with `|` for OR logic (e.g., `Blum|Antaro|Merivobox`)
- Returns file paths and line numbers for citation
- Supports `context_lines` parameter to show surrounding text
- Routes through `SearchCoordinator` (extensible to BM25, embeddings in the future)

The tool loop is **budget-enforced**: tool results consume tokens from a dedicated `TOOL_RESULTS` slot (5% of total context). When the budget is exceeded, results are truncated and the LLM is forced to answer from partial content.

### 3. Respond from Training Data, Narrowed by KB

This is the core design insight. The LLM does NOT blindly copy from the knowledge base. The response generation follows this pattern:

```
LLM's own knowledge (training data)
    +
Knowledge base findings (company-specific data)
    ↓
Answer that uses general expertise, narrowed/overridden by company specifics
```

Example:

- **User asks:** "What are Blum drawer systems?"
- **LLM knows:** General drawer system categories, how they work, trade-offs
- **KB provides:** Specific models this company uses (Tandembox Antaro, Merivobox, Legrabox), local pricing (Wrocław 2026), company-specific dimension tables
- **Response:** General expertise about drawer systems + company-specific part numbers, pricing, and dimension rules — with citations

The system prompt enforces this with explicit instructions:

> "Start with your own knowledge. Search the knowledge base for company-specific details. Merge general expertise + company-specific data in your answer."

### 4. Optional Document Updates

The agent can modify the knowledge base when the user requests it:

| Tool          | Purpose                                                    |
| ------------- | ---------------------------------------------------------- |
| `edit_file`   | Modify existing content (search-and-replace on exact text) |
| `create_file` | Create new documents for new topics                        |

These tools are **write operations** — they modify the markdown files on disk. The system enforces safety rules:

- Must `read_file` before `edit_file` (no blind edits)
- Must `get_repo_map` before writing when no file path is given (no guessing)
- All edits create backup files with revert capability
- Path traversal is blocked

---

## How One Turn Works

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. USER MESSAGE arrives at /api/chat                                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│ 2. CHAT SERVICE loads session state                                 │
│    - API history (for LLM)                                          │
│    - UI history (for frontend)                                      │
│    - Saved system prompt override (if any)                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│ 3. CONTEXT ASSEMBLER builds the context window                      │
│    - System prompt (base rules + mode content)                      │
│    - Conversation history (budgeted, oldest-first trimming)         │
│    - User message + images                                          │
│    - Context files (if attached)                                    │
│    - Notes (if referenced)                                          │
│    - Tool schemas (provider-specific format)                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│ 4. LLM PROVIDER sends request to API                                │
│    - Gemini / Anthropic / MiMo (OpenAI-compatible)                  │
│    - Response normalized to common format                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│ 5. TOOL LOOP (if LLM requests tools)                               │
│    ┌──────────────────────────────────────────────────────┐         │
│    │ a. Execute tool calls (search, read, edit, create)   │         │
│    │ b. Count tokens — truncate if over budget            │         │
│    │ c. Feed results back to LLM                          │         │
│    │ d. LLM responds — may request more tools or answer   │         │
│    │ e. Repeat (max 10 iterations)                        │         │
│    └──────────────────────────────────────────────────────┘         │
│    Budget exceeded → force text response from partial results       │
│    Max iterations exceeded → raise error                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│ 6. CHAT SERVICE persists and returns                                │
│    - Save updated API history (dehydrated)                          │
│    - Save updated UI history (JSON)                                 │
│    - Log turn to prompt_log.md                                      │
│    - Return ChatTurnResponse to API layer                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Layer                                │
│  FastAPI routes — thin, HTTP concerns only                      │
│  api/chat · api/sessions · api/files · api/notes · api/prompts  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      Service Layer                              │
│  Business logic — session lifecycle, persistence                │
│  ChatService · ExportService · MessageEditService               │
│  PromptManager · TokenCounter                                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     Agent Layer                                 │
│  Turn execution — context assembly, tool loop, normalization    │
│  TurnOrchestrator · ContextAssembler · ToolExecutor             │
│  ResponseNormalizer                                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   Provider Layer                                │
│  LLM API clients — each implements LLMProvider protocol         │
│  GeminiProvider · AnthropicProvider · MimoProvider              │
│  ToolSchemaConverter (Gemini ↔ Anthropic ↔ OpenAI formats)     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                 Content & Tools Layer                           │
│  Knowledge base operations                                      │
│  FileManager · NoteManager · SearchCoordinator                  │
│  ToolRegistry · file_ops · repo_map                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   Data Layer                                    │
│  Persistence — SQLite for sessions/notes                        │
│  SessionRepository · NoteRepository · SQLiteConnection          │
│  Markdown files on disk (knowledge base)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### Why "Minimal Looping"?

This is NOT a ReAct agent, a chain-of-thought planner, or an autonomous system. The tool loop is **reactive** — the LLM requests tools when it needs data, executes them, and responds. There is no:

- Multi-step planning
- Sub-agent spawning
- Self-reflection or retry strategies
- Complex reasoning chains

The loop is bounded (max 10 iterations) and budget-enforced (5% of context for tool results). This makes behavior **predictable and debuggable**.

### Why Protocol-Based Interfaces?

Every major component is defined by a Protocol (structural typing):

| Protocol                | Implementations         |
| ----------------------- | ----------------------- |
| `LLMProvider`           | Gemini, Anthropic, MiMo |
| `SessionRepository`     | SQLiteSessionRepository |
| `NoteRepository`        | SQLiteNoteRepository    |
| `TokenCounterProtocol`  | TokenCounter            |
| `PromptManagerProtocol` | PromptManager           |
| `ToolRegistryProtocol`  | ToolRegistry            |

This enables:

- Swapping providers without changing agent code
- Testing with fake implementations (no API calls)
- Adding new backends (embeddings, vector DB) without refactoring

### Why Normalized Response Format?

Each LLM provider returns data in its own format:

- Gemini: `functionCall` parts in `Content`
- Anthropic: `tool_use` content blocks
- MiMo/OpenAI: `tool_calls` array with `function.name`

The `ResponseNormalizer` converts all of these to a single `NormalizedResponse(text, has_tool_calls, tool_calls, usage)`. The orchestrator never sees provider-specific types.

### Why Token Budget Enforcement?

Without budget enforcement, a single tool call (e.g., `get_repo_map` returning 17K tokens) can exhaust the context window, causing:

1. LLM receives truncated, incomplete data
2. LLM produces confused or empty responses
3. Subsequent tool calls fail

The budget system allocates 5% of total context to tool results. When exceeded:

1. Current result is truncated with a warning
2. Remaining results in the batch are zeroed out
3. LLM is forced to produce a text response from partial content
4. If LLM returns tool calls instead of text, a synthetic summary is generated

### Why Common History Format?

Session history must survive serialization (JSON) and round-trip across providers. The common format uses simple dicts:

```json
{"role": "user", "content": "..."}
{"role": "assistant", "content": "...", "tool_calls": [{"id": "...", "name": "...", "arguments": {...}}]}
{"role": "tool", "tool_call_id": "...", "content": "..."}
```

Each provider converts this to its own format before sending to the API (via `_common_to_anthropic()`, `_coerce_history_for_gemini()`, etc.).

---

## Knowledge Base Structure

The knowledge base is a directory of markdown files organized by topic:

```
data/
├── 00_Dokumenty_Strategiczne/    # Strategic documents
├── 00_Inbox_i_Zadania/           # Inbox and tasks
├── 01_Biznes_i_Sprzedaz/         # Business and sales
├── 02_Projektowanie_i_Style/     # Design and styles
├── 03_Materialy_i_Katalogi/      # Materials and catalogs
├── 04_Okucia_i_Akcesoria/        # Hardware and accessories
├── 04_Podwykonawcy_CRM/          # Subcontractors CRM
├── 05_Montaz_i_Sprzet/           # Assembly and equipment
├── 06_Realizacje/                # Realizations
├── 07_SOP_Montaz/                # Assembly SOPs
├── 08_Filmy/                     # Videos
├── 08_Szkolenia_Corpus/          # Corpus training
├── chats.db                      # SQLite database
└── prompt_log.md                 # Activity log
```

The LLM accesses this through:

1. `get_repo_map` — discovers file structure and headings
2. `search_knowledge_base` — finds specific content by regex
3. `read_file` — reads full file content

---

## What This System Is NOT

| Not This                 | Why                                            |
| ------------------------ | ---------------------------------------------- |
| Autonomous agent         | No planning, no self-directed goals            |
| General-purpose chatbot  | Domain-specific (furniture/kitchen industry)   |
| RAG with embeddings      | Uses regex search, not vector similarity       |
| Multi-agent system       | Single agent, single turn loop                 |
| Real-time knowledge base | Static markdown files, updated by user request |

---

## Extension Points

The architecture supports these future enhancements without refactoring:

| Extension                  | Where                | How                                      |
| -------------------------- | -------------------- | ---------------------------------------- |
| Vector search (embeddings) | `SearchCoordinator`  | Add a new `SearchBackend` implementation |
| New LLM provider           | `providers/`         | Implement `LLMProvider` protocol         |
| New tool                   | `tools/registry.py`  | Add `ToolEntry` to `_ALL_ENTRIES`        |
| New prompt mode            | `prompts/modes.json` | Add entry + markdown file                |
| New content type           | `content/`           | Add manager implementing protocol        |
| Web search                 | `ToolCategory.WEB`   | Register new tool entry                  |
