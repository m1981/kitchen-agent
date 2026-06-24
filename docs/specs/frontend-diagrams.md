# Kitchen Agent — Frontend Architecture Diagrams

Mermaid diagrams documenting the Svelte 5 frontend architecture.
Generated from `svelte-map` analysis, updated 2026-06-17 (post-refactor).

---

## 1. Component Hierarchy

```mermaid
graph TB
    subgraph Routes["SvelteKit Routes"]
        Layout["+layout.svelte<br/>favicon, global head"]
        RootPage["+page.svelte<br/>redirect → /chat/{uuid}"]
        ChatPage["chat/[id]/+page.svelte<br/>main orchestrator"]
        ErrorPage["chat/[id]/+error.svelte<br/>error boundary"]
    end

    subgraph ChatArea["Chat Area (left panel)"]
        ChatHeader["ChatHeader<br/>title, mode badge"]
        ChatMessageList["ChatMessageList<br/>scrollable messages"]
        ChatComposer["ChatComposer<br/>input orchestrator"]
    end

    subgraph Sidebar["Sidebar (left panel)"]
        SidebarLayout["SidebarLayout<br/>composes panels"]
        ContextSidebar["ContextSidebar<br/>files + notes"]
    end

    subgraph SidebarPanels["Sidebar Panels"]
        FolderTree["FolderTree<br/>folder list + drop zones"]
        SessionPanel["SessionPanel<br/>session forest"]
        ArchivedPanel["ArchivedPanel<br/>archived sessions"]
    end

    subgraph ComposerSubs["Composer Sub-Components"]
        ComposerActions["ComposerActions<br/>buttons, tools, send/stop"]
        ModelSelector["ModelSelector<br/>optgroup select"]
        TokenIndicator["TokenIndicator<br/>token bar"]
    end

    subgraph MessageSubs["Message Sub-Components"]
        MessageActions["MessageActions<br/>edit/delete/fork"]
        MessageEditor["MessageEditor<br/>inline edit"]
        SystemPromptBubble["SystemPromptBubble<br/>prompt display"]
        Markdown["Markdown<br/>parsed markdown"]
    end

    subgraph SessionSubs["Session Sub-Components"]
        DraggableSession["DraggableSession<br/>drag wrapper"]
        FolderItem["FolderItem<br/>single folder + sessions"]
        SessionTreeNode["SessionTreeNode<br/>recursive tree node"]
        SessionContextMenu["SessionContextMenu<br/>right-click menu"]
        CreateFolderDialog["CreateFolderDialog<br/>new folder modal"]
    end

    subgraph SidebarSubs["Sidebar Sub-Components"]
        NotesPanel["NotesPanel<br/>notes list"]
        NotePopup["NotePopup<br/>create note"]
        FileEditor["FileEditor<br/>edit context file"]
    end

    subgraph Shared["Shared / UI Components"]
        Dialog["Dialog<br/>base modal"]
        ConfirmDialog["ConfirmDialog<br/>modal confirm"]
        ArchiveConfirmDialog["ArchiveConfirmDialog<br/>archive with children/folder options"]
        MoveToFolderDialog["MoveToFolderDialog<br/>multi-folder select with children option"]
    end

    %% Route hierarchy
    Layout --> RootPage
    Layout --> ChatPage
    Layout --> ErrorPage

    %% Page composition
    ChatPage --> ChatHeader
    ChatPage --> ChatMessageList
    ChatPage --> ChatComposer
    ChatPage --> SidebarLayout
    ChatPage --> ContextSidebar
    ChatPage --> NotePopup

    %% Sidebar composition
    SidebarLayout --> FolderTree
    SidebarLayout --> SessionPanel
    SidebarLayout --> ArchivedPanel

    %% Chat area composition
    ChatMessageList --> MessageActions
    ChatMessageList --> MessageEditor
    ChatMessageList --> SystemPromptBubble
    ChatMessageList --> Markdown
    ChatMessageList --> ConfirmDialog

    ChatComposer --> ComposerActions
    ChatComposer --> TokenIndicator
    ComposerActions --> ModelSelector

    %% Shared UI
    ConfirmDialog --> Dialog
    CreateFolderDialog --> Dialog
    ArchiveConfirmDialog --> Dialog
    MoveToFolderDialog --> Dialog

    %% Session tree composition
    SessionPanel --> DraggableSession
    SessionPanel --> SessionTreeNode
    ArchivedPanel --> DraggableSession
    ArchivedPanel --> SessionTreeNode
    FolderTree --> FolderItem
    FolderTree --> CreateFolderDialog
    SessionTreeNode --> SessionContextMenu

    %% Context sidebar composition
    ContextSidebar --> NotesPanel
    ContextSidebar --> FileEditor

    %% NotePopup is a portal (renders at page level)
    NotePopup -.->|"portal"| ChatPage

    style Routes fill:#e8f4f8,stroke:#2196F3
    style ChatArea fill:#e3f2fd,stroke:#1565C0
    style Sidebar fill:#fff3e0,stroke:#FF9800
    style SidebarPanys fill:#fff3e0,stroke:#FF9800
    style ComposerSubs fill:#f3e5f5,stroke:#9C27B0
    style MessageSubs fill:#fce4ec,stroke:#E91E63
    style SessionSubs fill:#e8f5e9,stroke:#4CAF50
    style SidebarSubs fill:#fff8e1,stroke:#FFC107
    style Shared fill:#efebe9,stroke:#795548
```

---

## 2. Store Architecture

```mermaid
graph TB
    subgraph ChatStore["chatStore — Session State Only"]
        ChatCore["chat.svelte.ts<br/>closure-based factory"]
        ChatOwns["Owns:<br/>sessionId, messages<br/>chatState (AsyncState)<br/>pastedImages, contextFiles<br/>isStreaming, forkStatus"]
    end

    subgraph DirectStores["Direct Import Stores"]
        ProviderStore["providerStore<br/>closure-based<br/>providers, selectedProvider/Model<br/>appTitle, appDescription"]
        PromptStore["promptStore<br/>closure-based<br/>selectedModeId, modesState<br/>toolsEnabled"]
        EditorStore["editorStore<br/>closure-based<br/>editingTurnId, editDraft<br/>sessionSystemPrompt"]
        TokenStore["tokenStore<br/>closure-based<br/>sessionTokenCount, fallback<br/>contextFileTokenEstimate"]
    end

    subgraph Independent["Independent Stores"]
        FolderStore["folderStore<br/><b>class-based</b><br/>folders ($state)<br/>folderSessions, sessionsLoading, sessionsError (SvelteMap)<br/>expandedFolders, folderedSessionIds (SvelteSet)<br/>pendingOps (SvelteMap)<br/><i>Note: SvelteMap/SvelteSet NOT wrapped in $state</i>"]
        SessionStore["sessionStore<br/>closure-based<br/>tree (SessionNode[])<br/>flat (derived), activeId"]
        NotesStore["notesStore<br/>closure-based<br/>bySession (Record&lt;string, Note[]&gt;)<br/>fetchStates"]
    end

    subgraph Patterns["Store Patterns"]
        Closure["Closure Factory<br/>function createXStore() {<br/>  let state = $state(...);<br/>  return { get x() { return state; } }<br/>}"]
        ClassBased["Class-Based<br/>class XStore {<br/>  state = $state(...);<br/>  get derived() { ... }<br/>}"]
        SvelteReactivity["Svelte Reactivity<br/>SvelteMap — reactive .get()/.set()<br/>SvelteSet — reactive .has()/.add()"]
    end

    ChatCore -->|"cross-store coordination"| ProviderStore
    ChatCore -->|"loadModes triggers"| PromptStore
    ChatCore -->|"saveEdit, deleteMessage"| EditorStore
    ChatCore -->|"refreshSessionTokens"| TokenStore
    ChatCore -->|"refresh after mutations"| SessionStore

    FolderStore -.->|"uses"| ClassBased
    FolderStore -.->|"uses"| SvelteReactivity
    ChatCore -.->|"uses"| Closure
    ProviderStore -.->|"uses"| Closure

    style ChatStore fill:#e3f2fd,stroke:#1565C0
    style DirectStores fill:#f3e5f5,stroke:#9C27B0
    style Independent fill:#e8f5e9,stroke:#4CAF50
    style Patterns fill:#fff8e1,stroke:#FFC107
```

---

## 3. Store → Component Consumer Map (Post-Refactor)

```mermaid
graph LR
    subgraph Stores["Stores"]
        CS["chatStore"]
        PS["providerStore"]
        PR["promptStore"]
        ES["editorStore"]
        TS["tokenStore"]
        FS["folderStore"]
        SS["sessionStore"]
        NS["notesStore"]
    end

    subgraph Components["Components"]
        PG["+page.svelte"]
        CA["ComposerActions"]
        CP["ChatComposer"]
        TI["TokenIndicator"]
        SL["SidebarLayout"]
        SP["SessionPanel"]
        AP["ArchivedPanel"]
        FT["FolderTree"]
        FI["FolderItem"]
        DS["DraggableSession"]
        NP["NotePopup"]
        NPL["NotesPanel"]
    end

    %% +page.svelte direct imports
    CS -->|"loadSession, sendMessage"| PG
    PS -->|"providers, appTitle, loadProviders"| PG
    PR -->|"selectedModeId, loadModes"| PG
    ES -->|"editState, startEditing, saveEdit"| PG
    SS -->|"refresh, setActive"| PG

    %% ComposerActions direct imports
    PR -->|"toolsEnabled, toggleTools"| CA

    %% ChatComposer
    CS -->|"pastedImages, chatState"| CP

    %% TokenIndicator direct imports
    TS -->|"sessionTokenCount, estimateInputTokens()"| TI
    PS -->|"contextWindowK"| TI

    %% SidebarLayout
    FS -->|"refresh"| SL

    %% SessionPanel direct imports
    SS -->|"tree, activeId"| SP

    %% ArchivedPanel direct imports
    SS -->|"tree, archived_at"| AP

    %% FolderTree
    FS -->|"sortedFolders"| FT

    %% FolderItem
    FS -->|"getSessions, isExpanded, pendingOps"| FI

    %% DraggableSession
    FS -->|"startDrag, endDrag"| DS

    %% Notes
    NS -->|"create, delete"| NP
    NS -->|"forSession(), load()"| NPL

    %% Cross-store dependencies (store-to-store)
    PR -->|"promptStore"| TS
    SS -->|"sessionStore"| CS

    style Stores fill:#e8f5e9,stroke:#4CAF50
    style Components fill:#e3f2fd,stroke:#1565C0
```

---

## 4. Chat Data Flow (Send → Stream → Display)

```mermaid
sequenceDiagram
    participant User
    participant Actions as ComposerActions
    participant Composer as ChatComposer
    participant Store as chatStore
    participant API as api.ts
    participant Backend as FastAPI

    User->>Actions: Clicks Run button
    Actions->>Composer: onsend()
    Composer->>Composer: handleSend()
    Composer->>Store: sendMessage(text)

    Store->>Store: Optimistic: push user message to messages[]
    Store->>Store: chatState = { status: 'loading' }
    Store->>Store: isStreaming = true

    Store->>API: chatStream(ChatRequest)
    API->>Backend: POST /api/chat/stream (SSE)

    loop SSE Stream
        Backend-->>API: event: text_delta
        API-->>Store: yield { type: 'text_delta', content }
        Store->>Store: Append to last assistant message
        Store-->>Composer: Reactive update → re-render

        Backend-->>API: event: tool_call
        API-->>Store: yield { type: 'tool_call', name, args }
        Store->>Store: Add tool log to message

        Backend-->>API: event: tool_result
        API-->>Store: yield { type: 'tool_result', name, result }
        Store->>Store: Update tool log with result
    end

    Backend-->>API: event: done
    API-->>Store: yield { type: 'done', turn_ids, tokens }
    Store->>Store: Save turn_ids to messages
    Store->>Store: chatState = { status: 'idle' }
    Store->>Store: isStreaming = false
    Store->>Store: refreshSessionTokens()

    Note over Store: If first turn (messages.length ≤ 3):<br/>generateTitleInBackground()
```

---

## 5. Sidebar Architecture (Post-Refactor)

```mermaid
graph TB
    subgraph SidebarLayout["SidebarLayout — Top-Level Container"]
        FolderSection["Folder Section"]
        SessionSection["Session Section"]
        ArchivedSection["Archived Section"]
    end

    subgraph FolderSystem["Folder System"]
        FolderTree["FolderTree<br/>Creates drop zones per folder"]
        FolderItem["FolderItem<br/>Expandable folder with sessions"]
        CreateFolder["CreateFolderDialog → Dialog"]
        DropZone["use:droppable<br/>accepts: session"]
    end

    subgraph SessionSystem["Session Panel"]
        SessionPanel["SessionPanel<br/>Header + error toast + forest"]
        DraggableSession["DraggableSession<br/>use:draggable"]
        SessionTreeNode["SessionTreeNode<br/>Recursive: renders children"]
        ContextMenu["SessionContextMenu<br/>Right-click actions"]
    end

    subgraph ArchivedSystem["Archived Panel"]
        ArchivedPanel["ArchivedPanel<br/>Expand/collapse toggle"]
        ArchivedSessions["Archived session rendering"]
    end

    subgraph DragDrop["Drag & Drop Flow"]
        DragStart["Drag Start<br/>folderStore.startDrag(payload)"]
        DragOver["Drag Over<br/>folderStore.setDropTarget(target)"]
        Drop["Drop<br/>folderStore.assignSession(folderId, sessionId)"]
        DragEnd["Drag End<br/>folderStore.endDrag()"]
        PendingOps["pendingOps tracking<br/>SvelteMap for UX"]
    end

    subgraph folderStore["folderStore (class-based)"]
        Folders["$state: folders[]"]
        Expanded["SvelteSet: expandedFolders,<br/>folderedSessionIds<br/>(no $state — built-in reactivity)"]
        Sessions["SvelteMap: folderSessions,<br/>sessionsLoading, sessionsError<br/>(no $state — built-in reactivity)"]
        Drag["$state: dragPayload, dropTarget"]
        Pending["SvelteMap: pendingOps<br/>(no $state — built-in reactivity)"]
        Methods["assignSession(), invalidateSessions()<br/>toggleExpand(), isExpanded()<br/>getSessions() → queueMicrotask(fetchSessions)"]
    end

    FolderSection --> FolderTree
    FolderTree --> DropZone
    DropZone --> FolderItem
    FolderItem -->|"expanded"| Sessions
    FolderTree --> CreateFolder

    SessionSection --> SessionPanel
    SessionPanel --> DraggableSession
    DraggableSession --> SessionTreeNode
    SessionTreeNode --> ContextMenu
    SessionTreeNode -->|"children"| SessionTreeNode

    ArchivedSection --> ArchivedPanel
    ArchivedPanel --> ArchivedSessions

    DraggableSession -->|"ondragstart"| DragStart
    DropZone -->|"ondragenter"| DragOver
    DropZone -->|"ondrop"| Drop
    DraggableSession -->|"ondragend"| DragEnd

    DragStart --> Drag
    DragOver --> Drag
    Drop --> Methods
    Drop --> Sessions
    Drop --> PendingOps
    DragEnd --> Drag

    SidebarLayout --> folderStore
    FolderTree --> folderStore
    FolderItem --> folderStore
    DraggableSession --> folderStore

    style SidebarLayout fill:#e3f2fd,stroke:#1565C0
    style FolderSystem fill:#e8f5e9,stroke:#4CAF50
    style SessionSystem fill:#fff3e0,stroke:#FF9800
    style ArchivedSystem fill:#fce4ec,stroke:#E91E63
    style DragDrop fill:#f3e5f5,stroke:#9C27B0
    style folderStore fill:#fff8e1,stroke:#FFC107
```

---

## 6. Svelte 5 Features Usage Map

```mermaid
graph TB
    subgraph Runes["Runes (Reactivity Primitives)"]
        State["$state()"]
        Derived["$derived()"]
        Props["$props()"]
        Bindable["$bindable()"]
        Effect["$effect()"]
    end

    subgraph Reactivity["Svelte Reactivity Collections"]
        SvelteMap["SvelteMap<br/>folderSessions, sessionsLoading,<br/>sessionsError, pendingOps<br/><i>NOT wrapped in $state</i>"]
        SvelteSet["SvelteSet<br/>expandedFolders, folderedSessionIds<br/><i>NOT wrapped in $state</i>"]
    end

    subgraph Patterns["Svelte 5 Patterns"]
        QueueMicrotask["queueMicrotask()<br/>Defer side effects from $derived<br/>Used in: folderStore.getSessions()"]
    end

    subgraph Actions["Svelte Actions (use:)"]
        Draggable["use:draggable<br/>HTML5 drag start/end"]
        Droppable["use:droppable<br/>HTML5 drag enter/over/leave/drop"]
        PasteImage["use:pasteImage<br/>Ctrl+V image paste"]
        AutoResize["use:autoResize<br/>Textarea auto-grow"]
        FocusTrap["use:focusTrap<br/>Focus containment"]
    end

    subgraph Components["Svelte 5 Component Features"]
        Snippets["Snippets<br/>{#snippet name()}...{/snippet}<br/>{@render name()}"]
        Children["children prop<br/>Replaces <slot>"]
        TransitionBlock["{#key} blocks<br/>Transition triggers"]
    end

    subgraph Legacy["Svelte 4 Patterns Still Used"]
        IfEach["{#if} / {#each}<br/>Control flow"]
        BindThis["bind:this<br/>Element refs"]
        BindValue["bind:value<br/>Two-way binding"]
        OnMount["onMount()<br/>Lifecycle"]
        SvelteWindow["<svelte:window><br/>Global listeners"]
        SvelteHead["<svelte:head><br/>Meta tags"]
    end

    State -->|"folderStore, chatStore"| SvelteMap
    State -->|"folderStore"| SvelteSet
    Derived -->|"computed values"| Components
    Props -->|"every component"| Components
    Bindable -->|"ChatComposer.currentMessage"| Components

    Draggable -->|"DraggableSession"| SessionPanel["SessionPanel"]
    Droppable -->|"FolderTree drop zones"| FolderTree["FolderTree"]
    PasteImage -->|"ChatComposer"| Composer["ChatComposer"]
    AutoResize -->|"ChatComposer textarea"| Composer
    FocusTrap -->|"SessionContextMenu, NotePopup"| Modals["Modals"]

    Snippets -->|"Dialog, FolderTree"| Layout["Layout"]
    Children -->|"FolderTree, Dialog"| Layout

    style Runes fill:#e3f2fd,stroke:#1565C0
    style Reactivity fill:#f3e5f5,stroke:#9C27B0
    style Actions fill:#e8f5e9,stroke:#4CAF50
    style Components fill:#fff8e1,stroke:#FFC107
    style Legacy fill:#efebe9,stroke:#795548
    style Patterns fill:#fce4ec,stroke:#E91E63
```

---

## 7. Route Structure & Navigation

```mermaid
graph TB
    subgraph Routes["SvelteKit File-Based Routing"]
        Root["/<br/>+page.svelte<br/>Redirects to /chat/{uuid}"]
        Chat["/chat/[id]/<br/>+page.svelte<br/>URL-driven session"]
        Error["+error.svelte<br/>Error boundary page"]
        Layout["+layout.svelte<br/>Global: favicon, head"]
    end

    subgraph ChatPage["/chat/[id] Internal Structure"]
        LeftPanel["Left Panel (flex-1)"]
        RightPanel["Right Panel (sidebar)"]
    end

    subgraph LeftContent["Left Panel Content"]
        Header["ChatHeader"]
        Messages["ChatMessageList"]
        Composer["ChatComposer"]
    end

    subgraph RightContent["Right Panel Content"]
        SidebarLayout["SidebarLayout"]
        ContextSidebar["ContextSidebar"]
    end

    subgraph Navigation["Navigation Patterns"]
        Goto["goto(/chat/{uuid})"]
        BeforeNav["beforeNavigate<br/>cancel() during streaming"]
        PageStore["$page.params.id<br/>Reactive URL param"]
        PageReady["pageReady state<br/>Loading spinner"]
    end

    Layout --> Root
    Layout --> Chat
    Layout --> Error

    Root -->|"goto()"| Chat

    Chat --> LeftPanel
    Chat --> RightPanel

    LeftPanel --> Header
    LeftPanel --> Messages
    LeftPanel --> Composer

    RightPanel --> SidebarLayout
    RightPanel --> ContextSidebar

    SidebarLayout -->|"click session"| Goto
    Root -->|"new UUID"| Goto
    Chat -->|"streaming"| BeforeNav
    Chat -->|"params.id changes"| PageStore
    PageStore -->|"loadSession()"| ChatPage
    ChatPage -->|"loading"| PageReady

    style Routes fill:#e8f4f8,stroke:#2196F3
    style ChatPage fill:#e3f2fd,stroke:#1565C0
    style LeftContent fill:#f3e5f5,stroke:#9C27B0
    style RightContent fill:#fff3e0,stroke:#FF9800
    style Navigation fill:#fce4ec,stroke:#E91E63
```

---

## 8. Component Responsibility Matrix (Post-Refactor)

```mermaid
graph LR
    subgraph Orchestration["Page-Level Orchestrators"]
        ChatPage["+page.svelte<br/>━━━━━━━━━━━━━━<br/>• Mount + load session<br/>• Sidebar resize<br/>• Keyboard shortcuts<br/>• Navigation guards<br/>• Note popup state<br/>• pageReady loading state"]
        SidebarLayout["SidebarLayout<br/>━━━━━━━━━━━━━━<br/>• Compose panels<br/>• Folder store init"]
    end

    subgraph ChatComponents["Chat Components"]
        ChatHeader["ChatHeader<br/>━━━━━━━━━━━━━━<br/>• Title display + edit<br/>• Mode badge<br/>• Provider info"]
        ChatMessageList["ChatMessageList<br/>━━━━━━━━━━━━━━<br/>• Scroll management<br/>• Auto-scroll on new msg<br/>• Message rendering<br/>• Selection tracking"]
        ChatComposer["ChatComposer<br/>━━━━━━━━━━━━━━<br/>• Textarea + auto-resize<br/>• Image paste handling<br/>• Context files strip"]
        ComposerActions["ComposerActions<br/>━━━━━━━━━━━━━━<br/>• Tools toggle<br/>• Model selector<br/>• Send/stop button<br/>• Placeholder toasts"]
    end

    subgraph MessageComponents["Message Components"]
        MessageActions["MessageActions<br/>━━━━━━━━━━━━━━<br/>• Edit button<br/>• Delete button<br/>• Fork button<br/>• Copy button<br/>• Selection highlight"]
        MessageEditor["MessageEditor<br/>━━━━━━━━━━━━━━<br/>• Inline textarea<br/>• Save/cancel<br/>• Auto-resize"]
        SystemPromptBubble["SystemPromptBubble<br/>━━━━━━━━━━━━━━<br/>• Collapsed preview<br/>• Expanded content<br/>• Prompt inspector"]
    end

    subgraph SidebarComponents["Sidebar Panels"]
        SessionPanel["SessionPanel<br/>━━━━━━━━━━━━━━<br/>• Header + count badge<br/>• Error toast<br/>• Session forest<br/>• Event handlers"]
        ArchivedPanel["ArchivedPanel<br/>━━━━━━━━━━━━━━<br/>• Expand/collapse<br/>• Count badge<br/>• Archived sessions"]
        FolderTree["FolderTree<br/>━━━━━━━━━━━━━━<br/>• Drop zones<br/>• Create button<br/>• Error toast"]
        FolderItem["FolderItem<br/>━━━━━━━━━━━━━━<br/>• Expand/collapse<br/>• Session list<br/>• Pending state<br/>• Context menu"]
    end

    subgraph UIComponents["Shared UI"]
        Dialog["Dialog<br/>━━━━━━━━━━━━━━<br/>• Escape key<br/>• Backdrop click<br/>• Scroll lock<br/>• Snippet slots"]
        ConfirmDialog["ConfirmDialog<br/>━━━━━━━━━━━━━━<br/>• Uses Dialog<br/>• Auto-confirm mode"]
        ArchiveConfirmDialog["ArchiveConfirmDialog<br/>━━━━━━━━━━━━━━<br/>• Include children option<br/>• Remove from folder option"]
        MoveToFolderDialog["MoveToFolderDialog<br/>━━━━━━━━━━━━━━<br/>• Multi-folder select<br/>• Include children option"]
        TokenIndicator["TokenIndicator<br/>━━━━━━━━━━━━━━<br/>• Progress bar<br/>• Session tokens<br/>• Input estimate<br/>• Context %"]
    end

    style Orchestration fill:#e3f2fd,stroke:#1565C0
    style ChatComponents fill:#f3e5f5,stroke:#9C27B0
    style MessageComponents fill:#fce4ec,stroke:#E91E63
    style SidebarComponents fill:#e8f5e9,stroke:#4CAF50
    style UIComponents fill:#fff8e1,stroke:#FFC107
```

---

## 9. Hotspot Analysis (Post-Refactor)

```mermaid
graph TB
    subgraph Hotspots["Most Imported Modules"]
        FS["folderStore — 5 importers<br/>DraggableSession, FolderItem,<br/>FolderTree, SessionPanel,<br/>SidebarLayout"]
        API["api.ts — 19 importers<br/>10 components, 8 stores,<br/>+page"]
        SS["sessionStore — 4 importers<br/>+page, SessionPanel,<br/>ArchivedPanel, chatStore"]
        PR["promptStore — 4 importers<br/>ComposerActions, +page,<br/>chatStore, tokenStore"]
        PS["providerStore — 3 importers<br/>TokenIndicator, +page,<br/>chatStore"]
    end

    subgraph Risk["Coupling Risk Assessment"]
        LowRisk["Low Risk<br/>Leaf components with<br/>no dependents"]
        MedRisk["Medium Risk<br/>Used by 2-3 siblings"]
        HighRisk["High Risk<br/>Used by many components<br/>or is a type dependency"]
    end

    FS -->|"High"| HighRisk
    API -->|"High"| HighRisk
    SS -->|"Medium"| MedRisk
    PR -->|"Medium"| MedRisk
    PS -->|"Medium"| MedRisk

    subgraph Recommendations["Post-Refactor Status"]
        R1["folderStore: Stable API<br/>— most imported store, uses SvelteMap"]
        R2["chatStore: Session state only<br/>— no delegation getters"]
        R3["Direct imports: All stores<br/>— no facade pattern"]
    end

    style Hotspots fill:#e3f2fd,stroke:#1565C0
    style Risk fill:#fce4ec,stroke:#E91E63
    style Recommendations fill:#e8f5e9,stroke:#4CAF50
```

---

## 10. Shared Types Architecture

```mermaid
graph TB
    subgraph Types["$lib/types/"]
        Index["index.ts<br/>Re-exports all types"]
        States["states.ts<br/>AsyncState only<br/>(RemoteData removed 2026-06-16)"]
        TypesOwn["Owns:<br/>PastedImage, NotePopupState<br/>DragPayload, DropTarget<br/>FolderSession"]
    end

    subgraph AsyncState["AsyncState&lt;T&gt; — Single State Machine"]
        Idle["{ status: 'idle' }"]
        Loading["{ status: 'loading' }"]
        Error["{ status: 'error', message: string }"]
        Success["{ status: 'success', data: T }"]
    end

    subgraph DragTypes["Drag & Drop Types"]
        DragPayload["DragPayload<br/>{ type, id, title }"]
        DropTarget["DropTarget<br/>{ type, id }"]
    end

    subgraph Consumers["All Stores Use AsyncState"]
        ChatStore["chatStore"]
        EditorStore["editorStore"]
        PromptStore["promptStore"]
        FolderStore["folderStore"]
        SessionStore["sessionStore"]
        NotesStore["notesStore"]
        DragActions["dragdrop.ts → DragPayload, DropTarget"]
    end

    Index --> States
    Index --> TypesOwn
    States --> AsyncState
    TypesOwn --> DragPayload
    TypesOwn --> DropTarget

    AsyncState --> ChatStore
    AsyncState --> EditorStore
    AsyncState --> PromptStore
    AsyncState --> FolderStore
    AsyncState --> SessionStore
    AsyncState --> NotesStore
    DragPayload --> DragActions
    DropTarget --> DragActions

    style Types fill:#e8f4f8,stroke:#2196F3
    style AsyncState fill:#f3e5f5,stroke:#9C27B0
    style DragTypes fill:#e8f5e9,stroke:#4CAF50
    style Consumers fill:#fff3e0,stroke:#FF9800
```

---

## 11. Session State Machine

```mermaid
stateDiagram-v2
    [*] --> Active: create session
    [*] --> Forked: fork session

    state "Active (History)" as Active
    state "Foldered" as Foldered
    state "Archived" as Archived
    state "Forked" as Forked

    Active --> Foldered: assignSessionTree()
    Active --> Archived: archiveTree()
    Active --> Forked: forkSession()

    Foldered --> Active: unassignSessionTree()
    Foldered --> Archived: archiveTree()
    Foldered --> Foldered: assignSessionTree() (add to another)

    Archived --> Active: unarchiveTree()
    Archived --> Foldered: unarchiveTree() (if still in folder)

    Forked --> Foldered: assignSessionTree()
    Forked --> Archived: archiveTree()

    Active --> [*]: delete (if no children)
    Foldered --> [*]: delete (if no children)
    Archived --> [*]: delete (if no children)
    Forked --> [*]: delete (only leaf nodes)
```

### Session State Flags

```typescript
interface SessionFlags {
    is_archived: boolean; // archived_at IS NOT NULL
    is_foldered: boolean; // in session_folders table
    is_fork: boolean; // parent_id IS NOT NULL
    is_fork_parent: boolean; // has children
    children_count: number; // number of direct children
    folder_ids: string[]; // folders containing this session
}
```

### Tree Operations

| Operation                 | Frontend                                                         | Backend                                        |
| ------------------------- | ---------------------------------------------------------------- | ---------------------------------------------- |
| Archive tree              | `sessionStore.archiveTree(id, includeChildren)`                  | `POST /api/sessions/{id}/archive/tree`         |
| Unarchive tree            | `sessionStore.unarchiveTree(id, includeChildren)`                | `DELETE /api/sessions/{id}/archive/tree`       |
| Assign tree to folder     | `folderStore.assignSessionTree(folderId, id, includeChildren)`   | `POST /api/folders/{id}/sessions/{sid}/tree`   |
| Unassign tree from folder | `folderStore.unassignSessionTree(folderId, id, includeChildren)` | `DELETE /api/folders/{id}/sessions/{sid}/tree` |
| Get session flags         | `sessionStore.getSessionFlags(id)`                               | `GET /api/sessions/{id}/flags`                 |

---

## Diagram Maintenance

| Change                | Diagrams to Update                                   |
| --------------------- | ---------------------------------------------------- |
| New component         | 1 (Hierarchy), 8 (Responsibility)                    |
| New store             | 2 (Architecture), 3 (Consumer Map)                   |
| New route             | 7 (Routes)                                           |
| New action (use:)     | 6 (Svelte 5 Features)                                |
| New type              | 10 (Shared Types)                                    |
| Store refactor        | 2 (Architecture), 3 (Consumer Map), 9 (Hotspots)     |
| Component refactor    | 1 (Hierarchy), 8 (Responsibility)                    |
| Drag-drop changes     | 5 (Sidebar Architecture)                             |
| Chat flow changes     | 4 (Chat Data Flow)                                   |
| Session state changes | 11 (Session State Machine), session-state-machine.md |

### Last Updated

| Date       | Change                                                                                 | Diagrams      |
| ---------- | -------------------------------------------------------------------------------------- | ------------- |
| 2026-06-21 | Diagram↔code alignment: fix importer counts, add missing components, remove stale refs | 1, 2, 3, 6, 9 |
| 2026-06-21 | Delete dead code: SessionTree.svelte, ProviderPicker.svelte                            | 1, 9          |
| 2026-06-21 | Remove line counts and bar charts (stale noise)                                        | All           |
| 2026-06-17 | Session state machine: tree operations (archiveTree, assignTree, getSessionFlags)      | 2, 3, 5, 9    |
| 2026-06-17 | New components: ArchiveConfirmDialog, MoveToFolderDialog                               | 1, 8          |
| 2026-06-17 | DOM access timing fixes: waitForTimeout removal, proper waiting patterns               | - (E2E tests) |
| 2026-06-17 | Fix: SvelteMap/SvelteSet reactivity (remove $state wrapping, defer getSessions fetch)  | 2, 5, 6       |
| 2026-06-17 | Refactor v2 complete (all 8 phases)                                                    | All (updated) |
