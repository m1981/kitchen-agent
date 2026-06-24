# Session State Diagrams

Mermaid diagrams for session movement between History, Folders, and Archive.

---

## 1. Session Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> Active: create session
    [*] --> Forked: fork session

    Active --> Foldered: assign to folder
    Active --> Archived: archive
    Active --> Forked: fork (creates child)

    Foldered --> Active: unassign from folder
    Foldered --> Archived: archive
    Foldered --> Foldered: assign to another folder

    Archived --> Active: unarchive (if not in folder)
    Archived --> Foldered: unarchive (if still in folder)

    Forked --> Foldered: assign to folder
    Forked --> Archived: archive

    Active --> [*]: delete
    Foldered --> [*]: delete
    Forked --> [*]: delete (only if no children)
    Archived --> [*]: delete
```

---

## 2. Session Movement Flow

```mermaid
flowchart TB
    subgraph History["History (Inbox)"]
        A[Active Session]
        F[Forked Session]
    end

    subgraph Folder["Folder View"]
        FA[Session in Folder A]
        FB[Session in Folder B]
    end

    subgraph Archive["Archive View"]
        AR[Archived Session]
    end

    %% History → Folder
    A -->|"assignSession(folderA)"| FA
    F -->|"assignSession(folderA)"| FA

    %% Folder → History
    FA -->|"unassignSession(folderA)"| A
    FB -->|"unassignSession(folderB)"| A

    %% Any → Archive
    A -->|"archive()"| AR
    FA -->|"archive()"| AR
    F -->|"archive()"| AR

    %% Archive → History/Folder
    AR -->|"unarchive()"| A
    AR -->|"unarchive() + still in folder"| FA

    %% Many-to-Many
    FA -->|"assignSession(folderB)"| FB

    style History fill:#e3f2fd,stroke:#1565C0
    style Folder fill:#e8f5e9,stroke:#4CAF50
    style Archive fill:#fff3e0,stroke:#FF9800
```

---

## 3. Fork Tree Scenarios

```mermaid
graph TB
    subgraph Scenario1["Scenario 1: Folder Parent Only"]
        direction TB
        Root1[Root A] -->|"assign to folder"| FolderA1[In Folder]
        Fork1A[Fork B] -->|"stays"| History1[In History]
        Fork1B[Fork C] -->|"stays"| History1
    end

    subgraph Scenario2["Scenario 2: Archive Parent Only"]
        direction TB
        Root2[Root A] -->|"archive"| Archive2[Archived]
        Fork2A[Fork B] -->|"stays"| History2[In History]
        Fork2B[Fork C] -->|"stays"| History2
    end

    subgraph Scenario3["Scenario 3: Delete Parent"]
        direction TB
        Root3[Root A] -->|"delete"| Error3[❌ BLOCKED]
        Fork3A[Fork B] -->|"is child of"| Root3
        Fork3B[Fork C] -->|"is child of"| Root3
    end

    style Scenario1 fill:#e3f2fd,stroke:#1565C0
    style Scenario2 fill:#fff3e0,stroke:#FF9800
    style Scenario3 fill:#fce4ec,stroke:#E91E63
```

---

## 4. Folder Assignment Matrix

```mermaid
graph LR
    subgraph Sessions["Sessions"]
        S1[Session 1]
        S2[Session 2]
        S3[Session 3]
    end

    subgraph Folders["Folders"]
        F1[Folder A]
        F2[Folder B]
        F3[Folder C]
    end

    S1 -->|"many-to-many"| F1
    S1 --> F2
    S2 --> F1
    S3 --> F3
    S3 --> F2

    style Sessions fill:#e3f2fd,stroke:#1565C0
    style Folders fill:#e8f5e9,stroke:#4CAF50
```

---

## 5. Visibility Matrix

```mermaid
graph TB
    subgraph Views["Where Sessions Appear"]
        H[History View]
        FV[Folder View]
        AV[Archive View]
    end

    subgraph States["Session States"]
        AS[Active + No Folder]
        AF[Active + In Folder]
        AR[Active + In Multiple Folders]
        AK[Archived]
        FK[Forked + No Folder]
        FF[Forked + In Folder]
    end

    AS -->|"visible"| H
    AF -->|"visible"| FV
    AF -->|"hidden"| H
    AR -->|"visible"| FV
    AR -->|"hidden"| H
    AK -->|"visible"| AV
    AK -->|"hidden"| H
    AK -->|"hidden"| FV
    FK -->|"visible"| H
    FF -->|"visible"| FV
    FF -->|"hidden"| H

    style Views fill:#e3f2fd,stroke:#1565C0
    style States fill:#e8f5e9,stroke:#4CAF50
```

---

## 6. Edge Case: Invisible Sessions

```mermaid
flowchart TB
    Start[Session X in Folder A] --> Archive[Archive Session X]
    Archive --> DeleteFolder[Delete Folder A]
    DeleteFolder --> Invisible[❌ Session X Invisible]

    Invisible --> Fix1["Fix 1: Auto-unarchive on folder delete"]
    Invisible --> Fix2["Fix 2: Archive view shows all"]
    Invisible --> Fix3["Fix 3: 'Show all' admin view"]

    style Start fill:#e8f5e9,stroke:#4CAF50
    style Invisible fill:#fce4ec,stroke:#E91E63
    style Fix1 fill:#e3f2fd,stroke:#1565C0
    style Fix2 fill:#e3f2fd,stroke:#1565C0
    style Fix3 fill:#e3f2fd,stroke:#1565C0
```

---

## 7. Edge Case: Fork Tree Fragmentation

```mermaid
flowchart TB
    Start[Fork Tree: A → B → C] --> FolderA[Folder A only]
    FolderA --> History["History shows B, C as orphans"]
    History --> Confused["User confused: Where is A?"]

    Confused --> Fix1["Fix 1: Folder entire tree"]
    Confused --> Fix2["Fix 2: Show ghost parent in History"]
    Confused --> Fix3["Fix 3: Show tree in folder"]

    style Start fill:#e8f5e9,stroke:#4CAF50
    style Confused fill:#fce4ec,stroke:#E91E63
    style Fix1 fill:#e3f2fd,stroke:#1565C0
    style Fix2 fill:#e3f2fd,stroke:#1565C0
    style Fix3 fill:#e3f2fd,stroke:#1565C0
```

---

## 8. Race Condition: Assign During Delete

```mermaid
sequenceDiagram
    participant User
    participant UI as Frontend
    participant API as Backend
    participant DB as Database

    User->>UI: Drag session to folder
    UI->>UI: Optimistic: show in folder
    UI->>API: POST /assign

    Note over User,API: Meanwhile, in another tab...

    User->>UI: Delete session
    UI->>API: DELETE /sessions/:id
    API->>DB: DELETE FROM sessions
    API-->>UI: 200 OK

    API->>DB: INSERT INTO session_folders
    DB-->>API: ❌ Foreign key violation

    API-->>UI: 500 Error
    UI->>UI: Rollback: remove from folder
    UI->>UI: Show error toast

    Note over UI: Session disappears from folder
```

---

## 9. Recommended UI Layout

```mermaid
graph TB
    subgraph Sidebar["Sidebar"]
        direction TB
        NewChat["+ New chat button"]

        History["📁 History (Inbox)"]
        History --> HistoryList["Sessions NOT in any folder"]

        Folders["📂 Folders"]
        Folders --> Folder1["Folder A (3)"]
        Folders --> Folder2["Folder B (5)"]
        Folder1 --> Folder1Sessions["Sessions in A"]
        Folder2 --> Folder2Sessions["Sessions in B"]

        Archive["🗄️ Archive"]
        Archive --> ArchiveList["All archived sessions"]

        Forks["🔀 Recent Forks"]
        Forks --> ForkList["Forked sessions"]
    end

    subgraph Main["Main Area"]
        direction TB
        ChatView["Chat View"]
    end

    HistoryList -->|"click"| ChatView
    Folder1Sessions -->|"click"| ChatView
    ArchiveList -->|"click"| ChatView
    ForkList -->|"click"| ChatView

    style Sidebar fill:#f5f5f5,stroke:#9E9E9E
    style Main fill:#e3f2fd,stroke:#1565C0
    style History fill:#e8f5e9,stroke:#4CAF50
    style Folders fill:#fff3e0,stroke:#FF9800
    style Archive fill:#fce4ec,stroke:#E91E63
    style Forks fill:#f3e5f5,stroke:#9C27B0
```

---

## 10. Operation Preconditions & Postconditions

```mermaid
graph LR
    subgraph Assign["assignSession(folderId, sessionId)"]
        direction TB
        APre["Preconditions:<br/>- session exists<br/>- folder exists<br/>- not already in folder"]
        APost["Postconditions:<br/>- session in folder<br/>- count incremented<br/>- cache invalidated"]
    end

    subgraph Unassign["unassignSession(folderId, sessionId)"]
        direction TB
        UPre["Preconditions:<br/>- session is in folder"]
        UPost["Postconditions:<br/>- session removed from folder<br/>- count decremented<br/>- appears in History"]
    end

    subgraph Archive["archive(sessionId)"]
        direction TB
        ARPre["Preconditions:<br/>- session exists<br/>- not archived"]
        ARPost["Postconditions:<br/>- archived_at set<br/>- hidden from all views"]
    end

    subgraph Unarchive["unarchive(sessionId)"]
        direction TB
        UAPre["Preconditions:<br/>- session is archived"]
        UAPost["Postconditions:<br/>- archived_at cleared<br/>- appears in History or folder"]
    end

    style Assign fill:#e8f5e9,stroke:#4CAF50
    style Unassign fill:#fff3e0,stroke:#FF9800
    style Archive fill:#fce4ec,stroke:#E91E63
    style Unarchive fill:#e3f2fd,stroke:#1565C0
```
