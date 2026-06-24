# F003: Folder Organization

## Overview

Organizes chat sessions into colored folders with expand/collapse in the sidebar.

**Status**: Implemented  
**Last Updated**: 2026-06-17 — Fixed SvelteMap/SvelteSet reactivity bug

---

## 1. API Endpoints

| Method   | Path                                      | Description          |
| -------- | ----------------------------------------- | -------------------- |
| `POST`   | `/api/folders`                            | Create folder        |
| `GET`    | `/api/folders`                            | List all folders     |
| `PATCH`  | `/api/folders/{id}`                       | Update folder        |
| `DELETE` | `/api/folders/{id}`                       | Delete folder        |
| `POST`   | `/api/folders/{id}/sessions/{session_id}` | Assign session       |
| `DELETE` | `/api/folders/{id}/sessions/{session_id}` | Unassign session     |
| `GET`    | `/api/folders/{id}/sessions`              | List folder sessions |

---

## 2. Database Schema

```sql
CREATE TABLE IF NOT EXISTS folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#6B7280',
    icon TEXT DEFAULT '📁',
    parent_id TEXT,
    order_index INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES folders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_folders (
    session_id TEXT NOT NULL,
    folder_id TEXT NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, folder_id),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
);
```

---

## 3. Color Palette

| Name   | Hex       |
| ------ | --------- |
| Gray   | `#6B7280` |
| Red    | `#EF4444` |
| Orange | `#F97316` |
| Yellow | `#EAB308` |
| Green  | `#22C55E` |
| Blue   | `#3B82F6` |
| Purple | `#A855F7` |
| Pink   | `#EC4899` |

---

## 4. File Reference

| File                                                  | Purpose                              |
| ----------------------------------------------------- | ------------------------------------ |
| `src/repositories/folder_repo.py`                     | SQLite repository                    |
| `src/folder_service.py`                               | Business logic                       |
| `src/schemas.py`                                      | Pydantic schemas                     |
| `src/api/folders.py`                                  | FastAPI router                       |
| `frontend/src/lib/stores/folder.svelte.ts`            | Frontend store                       |
| `frontend/src/lib/stores/folder.test.ts`              | Store unit tests                     |
| `frontend/src/lib/components/FolderTree.svelte`       | Folder list + drops + activeId prop  |
| `frontend/src/lib/components/FolderItem.svelte`       | Single folder + session context menu |
| `frontend/src/lib/components/DraggableSession.svelte` | Drag wrapper                         |
| `frontend/src/lib/actions/dragdrop.ts`                | HTML5 DnD actions                    |

---

## 5. Frontend Store Architecture

### 5.1 Inbox Model

History shows only **unfiled sessions** (sessions not assigned to any folder).
This is the "inbox" pattern — sessions live in one place:

```
History (inbox)         Folders
─────────────────       ─────────────────────
Session C               Kitchen Projects
Session D                 • Session A
Session E                 • Session B
Session H                 • Session F
...                       • Session G
(ONLY unfiled)
```

`folderStore.folderedSessionIds: SvelteSet<string>` tracks all session IDs
that are assigned to any folder. `SessionPanel` filters the session tree to
exclude these IDs.

The set is updated on:

- `refresh()` — fetches all folder sessions on mount
- `assignSession()` — adds ID optimistically
- `unassignSession()` — removes ID optimistically
- `deleteFolder()` — removes all IDs from deleted folder

### 5.2 Class-Based Store

`folderStore` is class-based (not closure-based like other stores):

```typescript
class FolderStore {
    // $state — plain reactive primitives
    folders = $state<Folder[]>([]);
    fetchState = $state<AsyncState<Folder[]>>({ status: 'idle' });
    dragPayload = $state<DragPayload | null>(null);
    dropTarget = $state<DropTarget | null>(null);
    createDialogOpen = $state(false);
    editingFolderId = $state<string | null>(null);
    error = $state<string | null>(null);

    // SvelteMap/SvelteSet — built-in reactivity, NO $state wrapping
    folderSessions = new SvelteMap<string, FolderSession[]>();
    sessionsLoading = new SvelteMap<string, boolean>();
    sessionsError = new SvelteMap<string, string | null>();
    expandedFolders = new SvelteSet<string>();
    pendingOps = new SvelteMap<string, { type: string; targetId: string }>();
}
```

**Key rule:** `SvelteMap`/`SvelteSet` have built-in reactivity. Never wrap in `$state`.

### 5.2 Session Cache

Three `SvelteMap` instances handle lazy-loaded folder sessions:

| Map               | Purpose                   |
| ----------------- | ------------------------- |
| `folderSessions`  | Cached session data       |
| `sessionsLoading` | Duplicate-fetch guard     |
| `sessionsError`   | Per-folder error messages |

**Lifecycle:**

```
First expand                    Subsequent expand
────────────                    ─────────────────
getSessions("f1")               getSessions("f1")
       │                               │
       ▼                               ▼
has("f1")=false                  has("f1")=true
       │                               │
       ▼                               ▼
queueMicrotask(                  return cached data
  fetchSessions()               (no API call)
)
       │
       ▼
return [] (loading)
       │
       ▼
API call → set("f1", data)
       │
       ▼
$derived recomputes → show sessions
```

**`getSessions()` — must be pure (called from `$derived`):**

```typescript
getSessions(folderId: string): FolderSession[] {
  if (!this.folderSessions.has(folderId)) {
    queueMicrotask(() => this.fetchSessions(folderId));
    return [];
  }
  return this.folderSessions.get(folderId) ?? [];
}
```

**`fetchSessions()` — duplicate guard:**

```typescript
async fetchSessions(folderId: string): Promise<void> {
  if (this.sessionsLoading.get(folderId)) return;

  this.sessionsLoading.set(folderId, true);
  this.sessionsError.set(folderId, null);

  try {
    const data = await api.getFolderSessions(folderId);
    this.folderSessions.set(folderId, data);
  } catch (e) {
    this.sessionsError.set(folderId, msg);
  } finally {
    this.sessionsLoading.set(folderId, false);
  }
}
```

**Cache invalidation** — on assign/unassign, delete cache entry to force fresh fetch:

```typescript
invalidateSessions(folderId: string): void {
  this.folderSessions.delete(folderId);
}
```

### 5.3 Optimistic Updates

| Operation      | Optimistic Action           | Rollback               |
| -------------- | --------------------------- | ---------------------- |
| Assign session | Increment `session_count`   | Restore previous state |
| Unassign       | Decrement `session_count`   | Restore previous state |
| Create folder  | Append to `folders` array   | —                      |
| Delete folder  | Remove from `folders` array | Restore previous array |
| Update folder  | Merge fields optimistically | Restore previous array |

---

## 6. Drag & Drop

Uses native HTML5 DnD API via Svelte actions (`frontend/src/lib/actions/dragdrop.ts`):

- `use:draggable` on `DraggableSession` — sets `application/json` data
- `use:droppable` on folder drop zones — handles enter/over/leave/drop
- Custom drag ghost image (off-screen div)
- `dragCounter` for nested element enter/leave

```
DraggableSession                folderStore
     │                              │
     ├─ dragstart ─────────────────▶ startDrag(payload)
     │                              │
FolderItem (drop zone)              │
     │                              │
     ├─ dragenter ─────────────────▶ setDropTarget(target)
     │                              │
     ├─ drop ──────────────────────▶ assignSession(folderId, sessionId)
     │                                    │
     │                                    ├─ API call
     │                                    └─ invalidateSessions()
     │
     └─ dragend ───────────────────▶ endDrag()
```

---

## 7. Change History

### 2026-06-17: Inbox Model

History now shows only unfiled sessions (not assigned to any folder).
Sessions appear in ONE place only — either a folder or History.

**Changes:**

- Added `folderedSessionIds: SvelteSet<string>` to track foldered sessions
- `SessionPanel` filters `visibleRoots` and `activeCount` to exclude foldered IDs
- `FolderItem` updated with `activeId` prop for consistent active state styling
- Session rendering in folders matches `SessionTreeNode` styling

### 2026-06-17: SvelteMap/SvelteSet Reactivity

**Symptom:** Folder expand showed infinite loading skeleton. API returned 5 sessions but UI never updated.

**Root cause:**

1. `$state<SvelteMap>` wrapping broke SvelteMap's internal notification mechanism
2. `getSessions()` mutated state inside `$derived` computation (`state_unsafe_mutation`)

**Fix:**

```diff
- folderSessions = $state<SvelteMap<string, FolderSession[]>>(new SvelteMap());
+ folderSessions = new SvelteMap<string, FolderSession[]>();

  getSessions(folderId: string): FolderSession[] {
    if (!this.folderSessions.has(folderId)) {
-     this.fetchSessions(folderId);
+     queueMicrotask(() => this.fetchSessions(folderId));
      return [];
    }
    return this.folderSessions.get(folderId) ?? [];
  }
```

**Lesson:** `SvelteMap`/`SvelteSet` are reactive primitives — never wrap in `$state`. Methods called from `$derived` must be pure — use `queueMicrotask` to defer side effects.
