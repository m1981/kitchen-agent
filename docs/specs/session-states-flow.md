# Session States Flow — Implementation Reference

Quick reference for implementing session state transitions.

---

## State Table

| archived_at | in folder | parent_id | Display State                | Location     |
| ----------- | --------- | --------- | ---------------------------- | ------------ |
| NULL        | No        | NULL      | **Active**                   | History      |
| NULL        | Yes       | NULL      | **Foldered**                 | Folder only  |
| NULL        | No        | set       | **Forked**                   | History      |
| NULL        | Yes       | set       | **Forked + Foldered**        | Folder only  |
| set         | No        | NULL      | **Archived**                 | Archive view |
| set         | Yes       | NULL      | **Archived + Foldered**      | Archive view |
| set         | No        | set       | **Archived Fork**            | Archive view |
| set         | Yes       | set       | **Archived Fork + Foldered** | Archive view |

---

## Valid Operations by State

| State    | Can Send? | Can Archive?      | Can Folder?         | Can Fork? | Can Delete?         |
| -------- | --------- | ----------------- | ------------------- | --------- | ------------------- |
| Active   | ✅        | ✅                | ✅                  | ✅        | ✅ (if no children) |
| Foldered | ✅        | ✅ (ask unassign) | ✅ (add to another) | ✅        | ✅ (if no children) |
| Forked   | ✅        | ✅ (ask children) | ✅                  | ✅        | ✅ (if no children) |
| Archived | ❌        | ❌                | ❌                  | ❌        | ✅ (if no children) |

---

## Operation Flows

### 1. Assign to Folder

```
User drags session to folder
        │
        ▼
   ┌─────────────────────┐
   │ Is session archived? │
   └──────────┬──────────┘
        │           │
       Yes          No
        │           │
        ▼           ▼
   ┌────────┐  ┌─────────────────────┐
   │ BLOCK  │  │ Is session fork     │
   │        │  │ parent (has kids)?  │
   └────────┘  └──────────┬──────────┘
                     │           │
                    Yes          No
                     │           │
                     ▼           ▼
              ┌────────────┐  ┌────────────────┐
              │ Ask user:  │  │ Assign session │
              │ Include    │  │ to folder      │
              │ children?  │  └────────────────┘
              └─────┬──────┘
                    │
            ┌───────┴───────┐
           Yes              No
            │               │
            ▼               ▼
     ┌──────────────┐  ┌──────────────┐
     │ Assign       │  │ Assign       │
     │ session +    │  │ session      │
     │ all children │  │ only         │
     └──────────────┘  └──────────────┘
```

### 2. Archive Session

```
User clicks Archive
        │
        ▼
   ┌─────────────────────┐
   │ Is session in folder?│
   └──────────┬──────────┘
        │           │
       Yes          No
        │           │
        ▼           ▼
   ┌────────────┐  ┌─────────────────────┐
   │ Ask user:  │  │ Is session fork     │
   │ Remove from│  │ parent (has kids)?  │
   │ folder?    │  └──────────┬──────────┘
   └─────┬──────┘       │           │
         │             Yes          No
    ┌────┴────┐         │           │
   Yes        No        ▼           ▼
    │          │  ┌────────────┐  ┌────────────────┐
    ▼          ▼  │ Ask user:  │  │ Archive        │
┌────────┐ ┌─────┐│ Archive    │  │ session        │
│Unassign│ │BLOCK││ children?  │  └────────────────┘
│then    │ │     │└─────┬──────┘
│archive │ └─────┘      │
└────────┘         ┌────┴────┐
                   Yes        No
                    │          │
                    ▼          ▼
             ┌──────────┐  ┌──────────┐
             │ Archive  │  │ Archive  │
             │ session +│  │ session  │
             │ children │  │ only     │
             └──────────┘  └──────────┘
```

### 3. Delete Session

```
User clicks Delete
        │
        ▼
   ┌─────────────────────┐
   │ Has children?        │
   └──────────┬──────────┘
        │           │
       Yes          No
        │           │
        ▼           ▼
   ┌────────┐  ┌─────────────────────┐
   │ BLOCK  │  │ Show confirm dialog │
   │ "Delete│  └──────────┬──────────┘
   │ children│            │
   │ first" │     ┌──────┴──────┐
   └────────┘    Cancel        Confirm
                    │              │
                    ▼              ▼
               ┌────────┐    ┌─────────────────────┐
               │ Cancel │    │ Is session in folder?│
               └────────┘    └──────────┬──────────┘
                                   │           │
                                  Yes          No
                                   │           │
                                   ▼           ▼
                            ┌──────────┐  ┌──────────┐
                            │ Unassign │  │ Delete   │
                            │ + Delete │  │ session  │
                            └──────────┘  └──────────┘
```

---

## Code Changes Required

### Backend (Python)

#### New Endpoints

```python
# src/api/folders.py

@router.post("/{folder_id}/sessions/{session_id}/tree")
async def assign_session_tree(
    folder_id: str,
    session_id: str,
    body: AssignTreeRequest  # { include_children: bool }
):
    """Assign session (and optionally children) to folder."""
    ...

# src/api/sessions.py

@router.post("/{session_id}/archive/tree")
async def archive_session_tree(
    session_id: str,
    body: ArchiveTreeRequest  # { include_children: bool }
):
    """Archive session (and optionally children)."""
    ...
```

#### New Repository Methods

```python
# src/repositories/session_repo.py

def get_children(self, session_id: str) -> list[str]:
    """Get all descendant session IDs (recursive)."""
    ...

def archive_tree(self, session_id: str, include_children: bool) -> list[str]:
    """Archive session and optionally all children."""
    ...

def get_session_flags(self, session_id: str) -> dict:
    """Get session state flags (is_archived, is_foldered, has_children, etc.)."""
    ...

# src/repositories/folder_repo.py

def assign_tree(self, folder_id: str, session_id: str, include_children: bool) -> list[str]:
    """Assign session tree to folder."""
    ...
```

### Frontend (Svelte)

#### New Store Methods

```typescript
// src/lib/stores/sessions.svelte.ts

async archiveTree(id: string, includeChildren: boolean): Promise<void> {
  // Optimistic: stamp all affected sessions
  // API call
  // Rollback on error
}

async getSessionFlags(id: string): Promise<SessionFlags> {
  // Returns { isArchived, isFoldered, hasChildren, childrenCount }
}
```

```typescript
// src/lib/stores/folder.svelte.ts

async assignTree(folderId: string, sessionId: string, includeChildren: boolean): Promise<void> {
  // Optimistic: update all affected sessions
  // API call
  // Rollback on error
}
```

#### New Components

```svelte
<!-- src/lib/components/ArchiveConfirmDialog.svelte -->
<script lang="ts">
  type Props = {
    open: boolean;
    sessionTitle: string;
    hasChildren: boolean;
    childrenCount: number;
    isFoldered: boolean;
    folderName: string;
    onconfirm: (options: { includeChildren: boolean; removeFromFolder: boolean }) => void;
    oncancel: () => void;
  };
</script>

<!-- src/lib/components/MoveToFolderDialog.svelte -->
<script lang="ts">
  type Props = {
    open: boolean;
    sessionTitle: string;
    hasChildren: boolean;
    childrenCount: number;
    folders: Folder[];
    onconfirm: (options: { folderIds: string[]; includeChildren: boolean }) => void;
    oncancel: () => void;
  };
</script>
```

---

## Sidebar Changes

### Add Archive View

```svelte
<!-- src/lib/components/SidebarLayout.svelte -->
<script>
  import FolderPanel from './FolderPanel.svelte';
  import SessionPanel from './SessionPanel.svelte';
  import ArchivedPanel from './ArchivedPanel.svelte';  // NEW
</script>

<FolderPanel />
<SessionPanel />
<ArchivedPanel />  <!-- NEW: shows all archived sessions -->
```

### ArchivedPanel Component

```svelte
<!-- src/lib/components/ArchivedPanel.svelte -->
<script lang="ts">
  import { sessionStore } from '$lib/stores/sessions.svelte';

  const archivedSessions = $derived(
    sessionStore.flat.filter(n => n.archived_at !== null)
  );

  let expanded = $state(false);
</script>

{#if archivedSessions.length > 0}
  <div class="mt-4">
    <button onclick={() => expanded = !expanded}>
      🗄️ Archive ({archivedSessions.length})
    </button>

    {#if expanded}
      {#each archivedSessions as session (session.id)}
        <div class="flex items-center justify-between opacity-60">
          <span>{session.title}</span>
          <button onclick={() => sessionStore.unarchive(session.id)}>
            Restore
          </button>
        </div>
      {/each}
    {/if}
  </div>
{/if}
```

---

## Context Menu Changes

### Updated SessionContextMenu

```typescript
// Current menu items
const menuItems = [
    { label: 'Edit Title', action: 'edit' },
    { label: 'Fork', action: 'fork' },
    { label: 'Export', action: 'export' },
    { separator: true },
    { label: 'Delete', action: 'delete', danger: true }
];

// Proposed menu items
const menuItems = [
    { label: 'Edit Title', action: 'edit' },
    { label: 'Fork', action: 'fork', disabled: isArchived },
    { separator: true },
    { label: 'Move to Folder...', action: 'move-to-folder', disabled: isArchived },
    { label: isFoldered ? 'Remove from Folder' : null, action: 'remove-from-folder' },
    { separator: true },
    { label: isArchived ? 'Unarchive' : 'Archive', action: isArchived ? 'unarchive' : 'archive' },
    { label: 'Export', action: 'export' },
    { separator: true },
    { label: 'Delete', action: 'delete', danger: true }
];
```

---

## Testing Checklist

### Unit Tests

- [ ] `sessionRepo.get_children()` returns all descendants
- [ ] `sessionRepo.archive_tree()` archives recursively
- [ ] `folderRepo.assign_tree()` assigns recursively
- [ ] State flags computed correctly

### E2E Tests

- [ ] Archive single session
- [ ] Archive session with children (ask dialog)
- [ ] Archive foldered session (ask dialog)
- [ ] Assign session to folder
- [ ] Assign session tree to folder
- [ ] Unassign from folder
- [ ] Delete session (blocked if has children)
- [ ] Delete leaf session (allowed)
- [ ] Fork tree operations

### Edge Cases

- [ ] Archive → Delete folder → Session in Archive view
- [ ] Assign archived session → Blocked
- [ ] Fork archived session → Disabled
- [ ] Rapid operations → Debounce
- [ ] Network error → Rollback

---

## Implementation Order

1. **Backend: `get_children()` and `get_session_flags()`** (30m)
2. **Backend: `archive_tree()` and `assign_tree()`** (1h)
3. **Frontend: Store methods for tree operations** (1h)
4. **Frontend: ArchiveConfirmDialog component** (1h)
5. **Frontend: MoveToFolderDialog component** (1h)
6. **Frontend: Update SessionContextMenu** (30m)
7. **Frontend: Add ArchivedPanel to sidebar** (1h)
8. **E2E tests** (2h)

**Total: ~8 hours**
