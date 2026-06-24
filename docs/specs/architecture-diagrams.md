# Kitchen Agent — Architecture Diagrams

Mermaid diagrams documenting the system architecture. Render in GitHub,
GitLab, Obsidian, or any Mermaid-compatible Markdown viewer.

---

## 1. High-Level Architecture Overview

```mermaid
graph TB
    subgraph Frontend["Frontend (Svelte 5)"]
        RootPage["/+page.svelte<br/>(redirect to /chat/{uuid})"]
        ChatPage["/chat/[id]/+page.svelte<br/>(URL-driven session)"]
        Stores["Stores (runes)"]
        Components["Components"]
        API["api.ts (fetch client)"]
    end

    subgraph Backend["Backend (FastAPI)"]
        subgraph API_Layer["API Layer"]
            ChatRoute["api/chat.py"]
            SessionRoute["api/sessions.py"]
            ImportRoute["api/import_chat.py"]
            ProviderRoute["api/providers.py"]
            NoteRoute["api/notes.py"]
            FileRoute["api/files.py"]
            PromptRoute["api/prompts.py"]
            FolderRoute["api/folders.py"]
        end

        subgraph Service_Layer["Service Layer"]
            ChatSvc["ChatService"]
            MsgEditor["MessageEditService"]
            ExportSvc["ExportService"]
            ImportSvc["ImportService"]
            FolderSvc["FolderService"]
        end

        subgraph Agent_Layer["Agent Layer"]
            Orchestrator["TurnOrchestrator"]
            Context["ContextAssembler"]
            ToolExec["ToolExecutor"]
        end

        subgraph Provider_Layer["Provider Layer"]
            LLMProvider["LLMProvider (Protocol)"]
            Gemini["GeminiProvider"]
            Anthropic["AnthropicProvider"]
            Mimo["MimoProvider"]
            Normalizer["ResponseNormalizer"]
        end

        subgraph Content_Layer["Content Layer"]
            NoteMgr["NoteManager"]
            FileMgr["FileManager"]
            SearchCoord["SearchCoordinator"]
        end

        subgraph Data_Layer["Data Layer"]
            SessionRepo["SessionRepository"]
            NoteRepo["NoteRepository"]
            FolderRepo["FolderRepository"]
            SQLite["SQLite"]
        end

        DI["dependencies.py"]
        Config["config.py / Settings"]
        Schemas["schemas.py (Pydantic)"]
        Prompts["PromptManager"]
    end

    RootPage -->|"goto(/chat/{uuid})"| ChatPage
    ChatPage --> Stores
    Stores --> API
    Components --> Stores
    API -->|HTTP/SSE| ChatRoute
    API -->|HTTP| SessionRoute
    API -->|HTTP| ImportRoute
    API -->|HTTP| ProviderRoute
    API -->|HTTP| FolderRoute

    ChatRoute --> ChatSvc
    SessionRoute --> MsgEditor
    SessionRoute --> ExportSvc
    ImportRoute --> ImportSvc
    FolderRoute --> FolderSvc

    ChatSvc --> Orchestrator
    Orchestrator --> Context
    Orchestrator --> ToolExec
    Orchestrator --> LLMProvider
    Orchestrator --> Normalizer

    LLMProvider -.-> Gemini
    LLMProvider -.-> Anthropic
    LLMProvider -.-> Mimo

    Context --> Prompts
    Context --> NoteMgr
    Context --> FileMgr

    ChatSvc --> SessionRepo
    MsgEditor --> SessionRepo
    ExportSvc --> SessionRepo
    ImportSvc --> SessionRepo
    FolderSvc --> FolderRepo
    NoteMgr --> NoteRepo
    SessionRepo --> SQLite
    NoteRepo --> SQLite
    FolderRepo --> SQLite

    DI --> ChatSvc
    DI --> ImportSvc
    DI --> FolderSvc
    DI --> Orchestrator
    DI --> LLMProvider

    style Frontend fill:#e8f4f8,stroke:#2196F3
    style API_Layer fill:#fff3e0,stroke:#FF9800
    style Service_Layer fill:#e8f5e9,stroke:#4CAF50
    style Agent_Layer fill:#fce4ec,stroke:#E91E63
    style Provider_Layer fill:#f3e5f5,stroke:#9C27B0
    style Content_Layer fill:#fff8e1,stroke:#FFC107
    style Data_Layer fill:#efebe9,stroke:#795548
```

---

## 2. Provider System

```mermaid
classDiagram
    class LLMProvider {
        <<Protocol>>
        +complete(context: AssembledContext) Any
        +complete_with_tools(context, tool_calls, tool_results) Any
        +stream(context: AssembledContext) Iterator
        +stream_with_tools(context, tool_calls, tool_results) Iterator
    }

    class GeminiProvider {
        -_model: str
        -_client: genai.Client
        -_config: GeminiConfig
        -_normalizer: ResponseNormalizer
        +complete(context) Any
        +stream(context) Iterator
    }

    class AnthropicProvider {
        -_model: str
        -_client: Anthropic
        -_config: AnthropicConfig
        +complete(context) Any
        +stream(context) Iterator
    }

    class MimoProvider {
        -_model: str
        -_client: OpenAI
        -_config: MimoConfig
        +complete(context) Any
        +stream(context) Iterator
    }

    class GeminiConfig {
        <<frozen dataclass>>
        +model: str = "gemini-3.1-pro-preview"
        +temperature: float = 0.2
    }

    class AnthropicConfig {
        <<frozen dataclass>>
        +api_key: str | None
        +model: str = "claude-sonnet-4-6"
        +temperature: float = 0.2
        +max_tokens: int = 8096
    }

    class MimoConfig {
        <<frozen dataclass>>
        +api_key: str | None
        +base_url: str
        +model: str = "mimo-v2.5-pro"
        +temperature: float = 0.2
        +max_tokens: int = 8096
    }

    class ResponseNormalizer {
        +normalize(raw, provider) NormalizedResponse
        +normalize_chunk(chunk, provider) str
    }

    class NormalizedResponse {
        <<frozen dataclass>>
        +text: str
        +has_tool_calls: bool
        +tool_calls: list~ToolCall~
        +usage: dict
        +raw: Any
    }

    class get_provider {
        <<function>>
        +get_provider(provider_name, model_override) LLMProvider
    }

    GeminiProvider ..|> LLMProvider
    AnthropicProvider ..|> LLMProvider
    MimoProvider ..|> LLMProvider

    GeminiProvider --> GeminiConfig
    AnthropicProvider --> AnthropicConfig
    MimoProvider --> MimoConfig

    GeminiProvider --> ResponseNormalizer
    AnthropicProvider --> ResponseNormalizer
    ResponseNormalizer --> NormalizedResponse

    get_provider --> GeminiProvider : creates
    get_provider --> AnthropicProvider : creates
    get_provider --> MimoProvider : creates
```

---

## 3. Agent Layer — Turn Lifecycle

```mermaid
sequenceDiagram
    participant CS as ChatService
    participant TO as TurnOrchestrator
    participant CA as ContextAssembler
    participant LLM as LLMProvider
    participant NR as ResponseNormalizer
    participant TE as ToolExecutor
    participant SR as SessionRepository

    CS->>SR: load_session(session_id)
    SR-->>CS: api_history, ui_history, system_prompt

    CS->>TO: run(session, turn_input)

    TO->>CA: assemble(session, mode, user_message)
    CA-->>TO: AssembledContext

    TO->>LLM: complete(context) or stream(context)
    LLM-->>TO: raw response

    TO->>NR: normalize(raw, provider)
    NR-->>TO: NormalizedResponse

    alt has_tool_calls
        loop Tool Loop (max iterations)
            TO->>TE: execute_all(tool_calls)
            TE-->>TO: tool_results
            TO->>LLM: complete_with_tools(context, tool_calls, tool_results)
            LLM-->>TO: raw response
            TO->>NR: normalize(raw, provider)
            NR-->>TO: NormalizedResponse
        end
    end

    TO-->>CS: TurnOutput

    CS->>SR: save_session(session_id, title, api_history, ui_history)
```

---

## 4. Chat Request Data Flow

```mermaid
flowchart LR
    subgraph Client["Frontend"]
        Composer["ChatComposer"]
        Store["chatStore"]
        SSE["SSE Parser"]
    end

    subgraph Server["Backend"]
        Route["POST /api/chat/stream"]
        Service["ChatService.stream_turn()"]
        Orchestrator["TurnOrchestrator.stream()"]
        Provider["LLMProvider.stream()"]
        Tools["ToolExecutor"]
        Repo["SessionRepository"]
    end

    Composer -->|"user message"| Store
    Store -->|"ChatRequest (SSE)"| Route
    Route --> Service

    Service -->|"1. Load session"| Repo
    Repo -->|"api_history, ui_history"| Service

    Service -->|"2. Execute turn"| Orchestrator
    Orchestrator -->|"AssembledContext"| Provider
    Provider -->|"text_delta"| Orchestrator
    Provider -->|"tool_call"| Orchestrator
    Orchestrator -->|"execute"| Tools
    Tools -->|"tool_result"| Orchestrator
    Orchestrator -->|"done event"| Service

    Service -->|"3. Persist"| Repo
    Service -->|"SSE events"| Route
    Route -->|"text_delta, tool_call, done"| SSE
    SSE -->|"update messages[]"| Store
```

---

## 5. Frontend Store Topology

```mermaid
graph TB
    subgraph Stores["Svelte 5 Rune Stores — 8 focused stores"]
        ChatStore["chatStore<br/><i>chat.svelte.ts</i><br/>session, messaging"]
        ProviderStore["providerStore<br/><i>provider.svelte.ts</i><br/>provider/model, app info"]
        PromptStore["promptStore<br/><i>prompt.svelte.ts</i><br/>modes, tools"]
        EditorStore["editorStore<br/><i>editor.svelte.ts</i><br/>message & prompt editing"]
        TokenStore["tokenStore<br/><i>token.svelte.ts</i><br/>token counting"]
        FolderStore["folderStore (class-based)<br/><i>folder.svelte.ts</i><br/>folders, session cache, drag-drop, pendingOps"]
        SessionStore["sessionStore<br/><i>sessions.svelte.ts</i>"]
        NotesStore["notesStore<br/><i>notes.svelte.ts</i>"]
    end

    subgraph ChatState["chatStore owns (core only)"]
        CS_Session["sessionId, messages"]
        CS_Async["chatState (AsyncState)"]
        CS_Images["pastedImages"]
        CS_Context["contextFiles"]
    end

    subgraph ProviderState["providerStore owns"]
        PS_Providers["providers (catalog)"]
        PS_Selected["selectedProvider, selectedModel"]
        PS_App["appTitle, appDescription"]
    end

    subgraph PromptState["promptStore owns"]
        PR_Mode["selectedModeId, modesState"]
        PR_Tools["toolsEnabled"]
        PR_Inspector["promptDetail*, inspectorOpen"]
    end

    subgraph EditorState["editorStore owns"]
        ES_Edit["editingTurnId, editDraft, editState"]
        ES_System["sessionSystemPrompt (loaded on session switch)"]
    end

    subgraph TokenState["tokenStore owns"]
        TS_Count["sessionTokenCount, fallback"]
        TS_Cache["contextFileTokenEstimate, systemPromptText"]
    end

    subgraph SessionState["sessionStore owns"]
        SS_Tree["tree (SessionNode[])"]
        SS_Flat["flat (derived)"]
        SS_Active["activeId"]
    end

    subgraph FolderState["folderStore owns (class-based, SvelteMap/SvelteSet)"]
        FS_Folders["folders, sortedFolders (derived)"]
        FS_Sessions["folderSessions (SvelteMap)"]
        FS_Expanded["expandedFolders, folderedSessionIds (SvelteSet)"]
        FS_Drag["dragPayload, dropTarget"]
        FS_Pending["pendingOps (SvelteMap)"]
    end

    subgraph NotesState["notesStore owns"]
        NS_BySession["bySession (Record&lt;string, Note[]&gt;)"]
        NS_Fetch["fetchStates"]
    end

    subgraph Consumers["Component Consumers (Direct Imports)"]
        ChatPage["/chat/[id]/+page.svelte"]
        ComposerActions["ComposerActions"]
        ChatComposer["ChatComposer"]
        TokenIndicator["TokenIndicator"]
        SidebarLayout["SidebarLayout"]
        SessionPanel["SessionPanel"]
        ArchivedPanel["ArchivedPanel"]
        FolderTree["FolderTree"]
        FolderItem["FolderItem"]
        DraggableSession["DraggableSession"]
        NotePopup["NotePopup"]
        NotesPanel["NotesPanel"]
    end

    %% Direct imports — no facade pattern
    ChatPage -->|"loadSession, sendMessage"| ChatStore
    ChatPage -->|"providers, appTitle"| ProviderStore
    ChatPage -->|"selectedModeId, loadModes"| PromptStore
    ChatPage -->|"editState, startEditing"| EditorStore

    ComposerActions -->|"toolsEnabled, toggleTools"| PromptStore
    ChatComposer -->|"pastedImages, chatState"| ChatStore
    TokenIndicator -->|"sessionTokenCount"| TokenStore
    TokenIndicator -->|"contextWindowK"| ProviderStore

    SidebarLayout -->|"refresh"| FolderStore
    SessionPanel -->|"tree, activeId"| SessionStore
    ArchivedPanel -->|"tree, archived_at"| SessionStore
    FolderTree -->|"sortedFolders"| FolderStore
    FolderItem -->|"getSessions, pendingOps"| FolderStore
    DraggableSession -->|"startDrag, endDrag"| FolderStore

    NotePopup -->|"create, delete"| NotesStore
    NotesPanel -->|"forSession(), load()"| NotesStore

    style ChatStore fill:#e3f2fd,stroke:#1565C0
    style ProviderStore fill:#f3e5f5,stroke:#9C27B0
    style PromptStore fill:#fce4ec,stroke:#E91E63
    style EditorStore fill:#fff8e1,stroke:#FFC107
    style TokenStore fill:#e8f5e9,stroke:#2E7D32
    style FolderStore fill:#e8f5e9,stroke:#2E7D32
    style SessionStore fill:#e8f5e9,stroke:#2E7D32
    style NotesStore fill:#fff3e0,stroke:#E65100
```

---

## 6. Dependency Injection Graph

```mermaid
graph TD
    subgraph Singletons["@lru_cache — Process Lifetime"]
        Settings["get_settings()"]
        DB["get_db_connection()"]
        ToolRegistry["get_tool_registry()"]
        PromptMgr["get_prompt_manager()"]
        Normalizer["get_response_normalizer()"]
        TokenCounter["get_token_counter()"]
        SearchCoord["get_search_coordinator()"]
        NoteMgr["get_note_manager()"]
        FileMgr["get_file_manager()"]
        ContextBudget["get_context_budget()"]
        ContextAssembler["get_context_assembler()"]
        ToolExec["get_tool_executor()"]
        Orchestrator["get_turn_orchestrator()"]
    end

    subgraph RequestScoped["Request Lifetime"]
        SessionRepo["get_session_repo()"]
        NoteRepo["get_note_repo()"]
        FolderRepo["get_folder_repo()"]
        ChatSvc["get_chat_service()"]
        MsgEditor["get_message_editor()"]
        ExportSvc["get_export_service()"]
        ImportSvc["get_import_service()"]
        FolderSvc["get_folder_service()"]
    end

    Settings --> DB
    Settings --> ContextBudget
    Settings --> Orchestrator
    DB --> SessionRepo
    DB --> NoteRepo
    DB --> FolderRepo
    SearchCoord --> ToolRegistry
    PromptMgr --> ContextAssembler
    TokenCounter --> ContextAssembler
    NoteMgr --> ContextAssembler
    FileMgr --> ContextAssembler
    ContextBudget --> ContextAssembler
    ContextAssembler --> Orchestrator
    ToolExec --> Orchestrator
    Normalizer --> Orchestrator
    SessionRepo --> ChatSvc
    Orchestrator --> ChatSvc
    SessionRepo --> MsgEditor
    SessionRepo --> ExportSvc
    SessionRepo --> ImportSvc
    FolderRepo --> FolderSvc
    TokenCounter --> ImportSvc

    style Singletons fill:#e8f5e9,stroke:#2E7D32
    style RequestScoped fill:#fff3e0,stroke:#E65100
```

---

## 7. URL-Based Session Routing

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant SvelteKit as SvelteKit Router
    participant ChatPage as /chat/[id]/+page.svelte
    participant ChatStore as chatStore
    participant Backend as FastAPI

    Note over User,Browser: ── SCENARIO 1: New Chat ──

    User->>Browser: Opens app (/)
    Browser->>SvelteKit: Navigate to /
    SvelteKit->>ChatPage: Mount +page.svelte (redirect)
    ChatPage->>SvelteKit: goto(/chat/{new-uuid})
    SvelteKit->>ChatPage: Mount /chat/[id]/+page.svelte
    ChatPage->>ChatPage: $effect → currentSessionId = params.id
    ChatPage->>ChatStore: loadSession(uuid)
    ChatStore->>Backend: GET /api/sessions/{uuid}
    Backend-->>ChatStore: 404 Not Found
    ChatStore->>ChatStore: Reset to empty state
    ChatStore-->>ChatPage: Empty chat ready
    User->>ChatPage: Types message
    ChatPage->>ChatStore: sendMessage(text)
    ChatStore->>Backend: POST /api/chat/stream
    Backend->>Backend: Create session in SQLite
    Backend-->>ChatStore: SSE stream
    ChatStore-->>ChatPage: Update messages[]

    Note over User,Browser: ── SCENARIO 2: Browser Refresh ──

    User->>Browser: Press F5 (refresh)
    Browser->>SvelteKit: Reload /chat/{id}
    SvelteKit->>ChatPage: Mount /chat/[id]/+page.svelte
    ChatPage->>ChatPage: $effect → currentSessionId = params.id
    ChatPage->>ChatStore: loadSession(id)
    ChatStore->>Backend: GET /api/sessions/{id}
    Backend-->>ChatStore: 200 OK (messages from DB)
    ChatStore-->>ChatPage: Restored session!

    Note over User,Browser: ── SCENARIO 3: Sidebar Navigation ──

    User->>ChatPage: Click session in sidebar
    ChatPage->>SvelteKit: goto(/chat/{other-id})
    SvelteKit->>ChatPage: $page.params.id changes
    ChatPage->>ChatPage: $effect fires
    ChatPage->>ChatStore: loadSession(other-id)
    ChatStore->>Backend: GET /api/sessions/{other-id}
    Backend-->>ChatStore: 200 OK
    ChatStore-->>ChatPage: Session loaded

    Note over User,Browser: ── SCENARIO 4: Streaming + Navigation Guard ──

    User->>ChatPage: Types message
    ChatPage->>ChatStore: sendMessage(text)
    ChatStore->>Backend: POST /api/chat/stream
    Backend-->>ChatStore: SSE streaming...
    User->>ChatPage: Clicks different session
    ChatPage->>ChatPage: beforeNavigate → cancel()
    ChatPage-->>User: Navigation blocked!
    Backend-->>ChatStore: SSE done
    ChatStore-->>ChatPage: isStreaming = false
    User->>ChatPage: Clicks different session
    ChatPage->>SvelteKit: goto(/chat/{other-id})
```

---

## 8. URL Routing State Machine

```mermaid
stateDiagram-v2
    [*] --> Root: User opens /
    Root --> NewChat: goto(/chat/{uuid})

    state NewChat {
        [*] --> LoadingSession
        LoadingSession --> EmptyChat: 404 (new UUID)
        LoadingSession --> ExistingChat: 200 (session exists)
        EmptyChat --> FirstMessage: User sends message
        FirstMessage --> Streaming: POST /api/chat/stream
        Streaming --> SessionSaved: SSE done + saved to DB
        SessionSaved --> [*]
    }

    state ExistingChat {
        [*] --> MessagesLoaded
        MessagesLoaded --> UserAction
        UserAction --> SendMessage: Type & send
        UserAction --> NavigateAway: Click sidebar
        UserAction --> Refresh: Press F5
        SendMessage --> Streaming
        Refresh --> [*]
    }

    NewChat --> ExistingChat: Session now exists
    ExistingChat --> NavigateToSession: goto(/chat/{id})
    NavigateToSession --> ExistingChat

    state "Streaming Guard" as StreamGuard {
        [*] --> Idle
        Idle --> Streaming: sendMessage()
        Streaming --> Blocked: Navigation attempt
        Blocked --> Streaming: Cancel navigation
        Streaming --> Idle: SSE done
        Idle --> [*]
    }
```

---

## 9. Title Generation Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend as chatStore
    participant API as POST /title/generate
    participant Provider as claude-haiku-4-5
    participant DB as SQLite

    Note over User,DB: ── Automatic: After First Message ──

    User->>Frontend: sendMessage("Jakie zawiasy...")
    Frontend->>API: POST /api/chat/stream
    API-->>Frontend: SSE stream (response)
    Frontend-->>User: Assistant response displayed

    Note over Frontend: messages.length <= 3 → first turn
    Frontend->>Frontend: generateTitleInBackground()

    rect rgb(240, 248, 255)
        Note right of Frontend: Background (non-blocking)
        Frontend->>API: POST /api/sessions/{id}/title/generate
        API->>DB: Load first + last message pairs
        DB-->>API: ui_messages JSON
        API->>Provider: Generate title (max 50 chars)
        Provider-->>API: "Zawiasy Blum do szafek"
        API->>DB: UPDATE sessions SET title = ...
        API-->>Frontend: { generated: true, title: "..." }
        Frontend->>Frontend: sessionStore.refresh()
        Frontend-->>User: Sidebar updates with new title
    end

    Note over User,DB: ── Manual: Context Menu ──

    User->>Frontend: Right-click session → "✨ Regenerate Title"
    Frontend->>API: POST /api/sessions/{id}/title/generate
    API->>Provider: Generate title
    Provider-->>API: New title
    API->>DB: UPDATE sessions SET title = ...
    API-->>Frontend: { generated: true, title: "..." }
    Frontend->>Frontend: sessionStore.refresh()
```

### Title Generation Prompt Structure

```mermaid
graph LR
    subgraph Input["Context Sent to LLM"]
        System["System: You are a title generator."]
        Prompt["Generate title (max 50 chars)\nSame language as conversation"]
        First["User: First msg[:300]\nAssistant: First response[:300]"]
        Last["User: Last msg[:300]\nAssistant: Last response[:300]"]
    end

    subgraph Output["LLM Response"]
        Title["Zawiasy Blum do szafek"]
    end

    System --> Provider["claude-haiku-4-5"]
    Prompt --> Provider
    First --> Provider
    Last --> Provider
    Provider --> Title

    style Input fill:#e8f4f8,stroke:#2196F3
    style Output fill:#e8f5e9,stroke:#4CAF50
```

---

## 10. Token Indicator Architecture

```mermaid
graph TB
    subgraph Stores["Svelte Stores"]
        ChatStore["chatStore"]
        TokenStore["tokenStore"]
    end

    subgraph Components["Components"]
        Composer["ChatComposer"]
        Indicator["TokenIndicator"]
    end

    subgraph Backend["Backend API"]
        TokenAPI["GET /sessions/{id}/tokens"]
    end

    subgraph Data["Token Data"]
        Session["Session Tokens\n(cumulated)"]
        Input["Input Tokens\n(estimated)"]
        Context["Context Window\n(percentage)"]
    end

    Composer -->|"messageText prop"| Indicator
    Indicator -->|"reads"| ChatStore
    ChatStore -->|"delegates"| TokenStore
    TokenStore -->|"refreshSessionTokens()"| TokenAPI
    TokenAPI -->|"SessionTokensResponse"| TokenStore

    TokenStore --> Session
    TokenStore --> Input
    TokenStore --> Context

    Indicator -->|"📊 sessionTokens"| Session
    Indicator -->|"→ ~inputTokens"| Input
    Indicator -->|"██░░ 32%"| Context

    style Indicator fill:#e3f2fd,stroke:#1565C0
    style TokenStore fill:#fff8e1,stroke:#FFC107
    style TokenAPI fill:#fff3e0,stroke:#FF9800
```

### Token Indicator Display

```mermaid
graph LR
    subgraph Composer["ChatComposer"]
        TI["TokenIndicator"]
        PB["Progress Bar"]
        ST["📊 4,271"]
        IT["→ ~127"]
        PCT["32%"]
    end

    TI --> PB
    TI --> ST
    TI --> IT
    TI --> PCT

    PB -->|"width"| Calc["Math.min(100, pct)%"]
    Calc -->|"color"| Color{"contextWindowColor()"}
    Color -->|"< 70%"| Green["bg-accent"]
    Color -->|"70-90%"| Yellow["bg-amber-500"]
    Color -->|"> 90%"| Red["bg-red-500"]

    style TI fill:#e3f2fd,stroke:#1565C0
    style Green fill:#e8f5e9,stroke:#4CAF50
    style Yellow fill:#fff8e1,stroke:#FFC107
    style Red fill:#fce4ec,stroke:#E91E63
```

---

## 11. Session Title Lifecycle

```mermaid
stateDiagram-v2
    [*] --> NoTitle: New session (URL only)

    state NoTitle {
        [*] --> ShowSessionID
        ShowSessionID: Display "Session {id[:8]}"
    }

    NoTitle --> AutoTitle: First message sent

    state AutoTitle {
        [*] --> BasicTitle
        BasicTitle: First 30 chars of message
        BasicTitle --> AITitle: Background generation
        AITitle: claude-haiku-4-5 generates title
    }

    AutoTitle --> ManualEdit: User clicks title

    state ManualEdit {
        [*] --> InputVisible
        InputVisible: Input field with current title
        InputVisible --> Save: Enter / blur
        InputVisible --> Cancel: Escape
        Save --> [*]
        Cancel --> [*]
    }

    ManualEdit --> AITitleRegen: Context menu → "✨ Regenerate"

    state AITitleRegen {
        [*] --> Generating
        Generating: Loading spinner
        Generating --> NewTitle: API success
        Generating --> Error: API failure
        NewTitle --> [*]
        Error --> [*]
    }

    AITitleRegen --> ManualEdit

    note right of NoTitle
        Fallback: Session ID
    end note

    note right of AutoTitle
        Automatic after first turn
    end note

    note right of ManualEdit
        Inline editing
    end note

    note right of AITitleRegen
        On-demand via context menu
    end note
```

### Title Display Logic

```mermaid
flowchart TD
    Start([Header Render]) --> Check{title prop?}

    Check -->|"title != null"| ShowTitle["Display: {title}"]
    Check -->|"title == null"| ShowID["Display: Session {id[:8]}"]

    ShowTitle --> Badge["🔧 General"]
    ShowID --> Badge

    Badge --> Click{User clicks?}

    Click -->|"Click title"| EditMode["Show input field"]
    Click -->|"No click"| Done([Done])

    EditMode --> Action{User action}

    Action -->|"Enter / blur"| Save{Empty?}
    Action -->|"Escape"| Cancel["Revert"]

    Save -->|"Not empty"| API["PATCH /sessions/{id}/title"]
    Save -->|"Empty"| Cancel

    API --> Refresh["sessionStore.refresh()"]
    Refresh --> Done
    Cancel --> Done

    style Start fill:#e3f2fd,stroke:#1565C0
    style ShowTitle fill:#e8f5e9,stroke:#4CAF50
    style ShowID fill:#fff8e1,stroke:#FFC107
    style EditMode fill:#f3e5f5,stroke:#9C27B0
    style API fill:#fff3e0,stroke:#FF9800
```

---

## 12. Import/Export Data Flow

```mermaid
sequenceDiagram
    participant Client as Client
    participant API as POST /api/sessions/import
    participant IS as ImportService
    participant TC as TokenCounter
    participant DG as derive_title()
    participant SR as SessionRepository
    participant SQLite as SQLite

    Client->>API: ImportRequest {title?, messages[], system_prompt?}
    API->>IS: import_chat(request)

    IS->>IS: Validate messages not empty

    loop For each message
        IS->>IS: Generate turn_id (UUID)
        IS->>TC: count(content)
        TC-->>IS: token_count
        IS->>IS: Build api_history item
        IS->>IS: Build ui_history item
    end

    alt title not provided
        IS->>DG: derive_title(ui_messages)
        DG-->>IS: Auto-generated title
    end

    IS->>SR: save_session(session_id, title, api_json, ui_json, system_prompt)
    SR->>SQLite: INSERT INTO sessions
    SQLite-->>SR: OK
    SR-->>IS: OK

    IS-->>API: ImportResponse {session_id, title, message_count, turn_count}
    API-->>Client: 201 Created
```

### Export Data Flow

```mermaid
sequenceDiagram
    participant Client as Client
    participant API as GET /api/sessions/{id}/export
    participant ES as ExportService
    participant SR as SessionRepository
    participant EX as exporter.py

    Client->>API: GET /api/sessions/{id}/export
    API->>ES: export_markdown(session_id)

    ES->>SR: get_export_data(session_id)
    SR-->>ES: {title, ui_history_json, ...}

    ES->>ES: json.loads(ui_history_json)
    ES->>EX: export_session_to_markdown(ui_messages, title)
    EX-->>ES: Markdown string

    ES-->>API: Markdown
    API-->>Client: text/markdown

    Note over Client,API: ── LLM JSON Export ──

    Client->>API: GET /api/sessions/{id}/export/llm
    API->>ES: export_llm_json(session_id)

    ES->>SR: get_export_data(session_id)
    SR-->>ES: {title, api_history_json, system_prompt, ...}

    ES->>ES: json.loads(api_history_json)
    ES->>EX: export_session_to_llm_json(api_items, title, ...)
    EX-->>ES: {metadata, config, turns}

    ES-->>API: LLM JSON
    API-->>Client: application/json
```

### Import/Export Architecture

```mermaid
graph TB
    subgraph Import["Import Path"]
        ImportRequest["ImportRequest<br/>{title?, messages[], system_prompt?}"]
        ImportService["ImportService"]
        BuildHistories["_build_histories()<br/>Generate turn_ids<br/>Estimate tokens"]
        TitleGen["derive_title()<br/>First user message"]
    end

    subgraph Export["Export Path"]
        ExportService["ExportService"]
        MarkdownExport["export_session_to_markdown()<br/>Human-readable"]
        LLMExport["export_session_to_llm_json()<br/>LLM replay format"]
    end

    subgraph Storage["SQLite Storage"]
        Sessions["sessions table"]
        APIHistory["api_history_json<br/>{role, content, turn_id}"]
        UIHistory["ui_history_json<br/>{role, content, turn_id,<br/>provider, model, token_count}"]
    end

    ImportRequest --> ImportService
    ImportService --> BuildHistories
    BuildHistories --> TitleGen
    ImportService --> Sessions
    Sessions --> APIHistory
    Sessions --> UIHistory

    Sessions --> ExportService
    UIHistory --> MarkdownExport
    APIHistory --> LLMExport

    style Import fill:#e3f2fd,stroke:#1565C0
    style Export fill:#e8f5e9,stroke:#2E7D32
    style Storage fill:#fff3e0,stroke:#FF9800
```

---

## Diagram Maintenance

When the architecture changes:

1. **Adding a new provider** → Update Diagram 2 (Provider System)
2. **Adding a new API endpoint** → Update Diagram 1 (High-Level) and Diagram 4 (Data Flow)
3. **Changing turn orchestration** → Update Diagram 3 (Agent Layer)
4. **Adding a new store** → Update Diagram 5 (Store Topology). All stores are imported directly by components. chatStore owns session state and coordinates cross-store operations.
5. **Adding a new DI dependency** → Update Diagram 6 (DI Graph)
6. **Changing routing/navigation** → Update Diagram 7 (URL Routing) and Diagram 8 (State Machine)
7. **Changing import/export** → Update Diagram 12 (Import/Export Data Flow) and docs/specs/f002-import-export.md
8. **Session state changes** → Update docs/specs/session-state-machine.md and session-states-flow.md

### Recent Changes

| Date       | Change                                                                       | Diagrams Updated       |
| ---------- | ---------------------------------------------------------------------------- | ---------------------- |
| 2026-06-17 | Session state machine: tree operations for History/Folder/Archive            | 1, 5, 10 (updated)     |
| 2026-06-17 | DOM access timing fixes: waitForTimeout removal, proper waiting patterns     | - (E2E tests)          |
| 2026-06-17 | Refactor v2 complete: direct imports, Dialog, SidebarLayout, ComposerActions | 1, 5, 10 (updated)     |
| 2026-06-16 | Class-based folderStore, drag-drop bug fix, ModelSelector extraction         | 1, 5, 6 (updated)      |
| 2026-06-14 | Import chats from external JSON (POST /api/sessions/import)                  | 1, 6, 12 (new)         |
| 2026-06-14 | Shared title derivation (src/title_generator.py)                             | 9 (updated)            |
| 2026-06-12 | URL-based session routing (`/chat/[id]`)                                     | 1, 5, 7 (new), 8 (new) |
| 2026-06-12 | TokenIndicator in ChatComposer                                               | 5, 10 (new)            |
| 2026-06-12 | Session title display & inline editing                                       | 11 (new)               |
| 2026-06-12 | AI title regeneration (POST /title/generate)                                 | 9 (new), 11 (new)      |
| 2026-06-12 | Auto-generate title on first message                                         | 9 (updated)            |
