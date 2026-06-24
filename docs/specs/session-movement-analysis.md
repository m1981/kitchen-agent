# Session Movement Analysis

## History ↔ Folders ↔ Archive (with Branched Sessions)

**Created**: 2026-06-17  
**Status**: Design Document

---

## 1. Data Model Summary

### Sessions Table

```sql
CREATE TABLE sessions (
    id               TEXT PRIMARY KEY,
    title            TEXT,
    parent_id        TEXT,           -- For fork/branch relationships
    fork_turn_index  INTEGER,        -- Which turn was forked at
    root_id          TEXT,           -- Root of the fork tree
    archived_at      TIMESTAMP,      -- NULL = active, non-NULL = archived
    updated_at       TIMESTAMP,
    ...
);
```

### Folders Table

```sql
CREATE TABLE folders (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    parent_id    TEXT,               -- Nested folders (CASCADE delete)
    order_index  INTEGER,
    ...
);
```

### Session-Folder Junction Table

```sql
CREATE TABLE session_folders (
    session_id   TEXT NOT NULL,
    folder_id    TEXT NOT NULL,
    assigned_at  TIMESTAMP,
    PRIMARY KEY (session_id, folder_id),  -- Composite key
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
);
```

---

## 2. Session States & Transitions

### State Diagram

```
                    ┌──────────────────────────────────────────────────────────┐
                    │                    SESSION LIFECYCLE                      │
                    └──────────────────────────────────────────────────────────┘

    ┌─────────┐      create      ┌─────────────┐
    │  (new)  │ ──────────────────►│   ACTIVE    │
    └─────────┘                    │ (History)   │
                                   └──────┬──────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
            ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
            │   FOLDERED   │      │   ARCHIVED   │      │   FORKED     │
            │ (in folder)  │      │ (archived)   │      │ (branched)   │
            └──────┬───────┘      └──────┬───────┘      └──────┬───────┘
                   │                     │                     │
                   │    ┌────────────────┼─────────────────────┘
                   │    │                │
                   ▼    ▼                ▼
            ┌──────────────────────────────────────┐
            │         COMPOUND STATES              │
            │  • Foldered + Archived               │
            │  • Forked + Foldered                 │
            │  • Forked + Archived                 │
            │  • Forked + Foldered + Archived      │
            └──────────────────────────────────────┘
```

### State Properties

| State             | `archived_at` | In `session_folders` | `parent_id` | Can Send? | Visible in History?  |
| ----------------- | ------------- | -------------------- | ----------- | --------- | -------------------- |
| Active            | NULL          | No                   | Any         | ✅ Yes    | ✅ Yes               |
| Foldered          | NULL          | Yes                  | Any         | ✅ Yes    | ❌ No (inbox filter) |
| Archived          | timestamp     | Any                  | Any         | ❌ No     | ❌ No (hidden)       |
| Forked            | NULL          | No                   | set         | ✅ Yes    | ✅ Yes               |
| Forked + Foldered | NULL          | Yes                  | set         | ✅ Yes    | ❌ No                |
| Forked + Archived | timestamp     | Any                  | set         | ❌ No     | ❌ No                |

---

## 3. Movement Operations

### 3.1 History → Folder (Assign)

**Operation**: `folderStore.assignSession(folderId, sessionId)`

**Preconditions**:

- Session exists
- Folder exists
- Session is not already in this folder (UNIQUE constraint)

**Side Effects**:

- Increments `folder.session_count`
- Adds to `folderedSessionIds` set
- Invalidates folder session cache
- Session disappears from History (inbox filter)

**Edge Cases**:

| #   | Scenario                          | Current Behavior          | Expected Behavior                         |
| --- | --------------------------------- | ------------------------- | ----------------------------------------- |
| 1   | Session already in another folder | ✅ Allowed (many-to-many) | ✅ Session can be in multiple folders     |
| 2   | Session already in THIS folder    | ✅ INSERT OR IGNORE       | ✅ No-op, no error                        |
| 3   | Session is archived               | ❓ Not checked            | ⚠️ Should we allow?                       |
| 4   | Session is a fork (has children)  | ✅ Allowed                | ✅ Only this session moves, children stay |
| 5   | Session is a fork (has parent)    | ✅ Allowed                | ✅ Fork moves independently               |
| 6   | Drag-drop during streaming        | ✅ Allowed                | ⚠️ Should disable during streaming        |
| 7   | Folder is deleted while dragging  | ❌ Unclear                | ⚠️ Need drop target validation            |

**Bug Risk**:

- **Fork tree fragmentation**: If you folder a parent but not children, the tree becomes fragmented in History view. Children appear as orphans.

---

### 3.2 Folder → History (Unassign)

**Operation**: `folderStore.unassignSession(folderId, sessionId)`

**Preconditions**:

- Session is in the specified folder

**Side Effects**:

- Decrements `folder.session_count`
- Removes from `folderedSessionIds` set
- Invalidates folder session cache
- Session reappears in History (inbox filter)

**Edge Cases**:

| #   | Scenario                    | Current Behavior         | Expected Behavior           |
| --- | --------------------------- | ------------------------ | --------------------------- |
| 1   | Session in multiple folders | ✅ Only removes from one | ✅ Correct                  |
| 2   | Session is archived         | ❓ Not checked           | ⚠️ Should unarchive first?  |
| 3   | Session is a fork parent    | ✅ Allowed               | ✅ Only this session moves  |
| 4   | Session is a fork child     | ✅ Allowed               | ✅ Fork moves independently |
| 5   | Rapid unassign-assign       | ✅ Optimistic update     | ⚠️ Race condition possible  |

**Bug Risk**:

- **Invisible archived sessions**: If you unassign an archived session, it goes to History but History filters out archived sessions. The session becomes invisible!

---

### 3.3 History/Archive (Archive)

**Operation**: `sessionStore.archive(id)`

**Preconditions**:

- Session exists
- Session is not already archived

**Side Effects**:

- Sets `archived_at` timestamp
- Session disappears from History AND folders (archived filter)

**Edge Cases**:

| #   | Scenario                  | Current Behavior | Expected Behavior        |
| --- | ------------------------- | ---------------- | ------------------------ |
| 1   | Archive session in folder | ✅ Allowed       | ✅ Hides from folder too |
| 2   | Archive fork parent       | ✅ Allowed       | ⚠️ What about children?  |
| 3   | Archive fork child        | ✅ Allowed       | ⚠️ What about parent?    |
| 4   | Archive active session    | ❓ Not checked   | ⚠️ Should warn user      |
| 5   | Archive while streaming   | ❓ Not checked   | ⚠️ Should disable        |

**Critical Question**: Should archiving a fork parent also archive all children?

**Current Behavior**: No cascading. Children become orphans (visible in History but parent is hidden).

---

### 3.4 Archive → History (Unarchive)

**Operation**: `sessionStore.unarchive(id)`

**Preconditions**:

- Session exists
- Session is archived

**Side Effects**:

- Clears `archived_at` to NULL
- Session reappears in History (or folder if still assigned)

**Edge Cases**:

| #   | Scenario                      | Current Behavior       | Expected Behavior                 |
| --- | ----------------------------- | ---------------------- | --------------------------------- |
| 1   | Unarchive session in folder   | ✅ Reappears in folder | ✅ Correct                        |
| 2   | Unarchive fork parent         | ✅ Only parent         | ⚠️ Should children unarchive too? |
| 3   | Unarchive fork child          | ✅ Only child          | ⚠️ Should parent unarchive too?   |
| 4   | Unarchive when folder deleted | ✅ Goes to History     | ✅ Correct                        |

---

### 3.5 Fork (Branch) Creation

**Operation**: `forkSession(sourceId, turnIndex)`

**Creates**: New session with:

- `parent_id` = source session ID
- `fork_turn_index` = turnIndex
- `root_id` = source's root_id (or source if it's a root)

**Side Effects**:

- New session appears in History
- Source session unchanged
- Session tree updated

**Edge Cases**:

| #   | Scenario                  | Current Behavior        | Expected Behavior        |
| --- | ------------------------- | ----------------------- | ------------------------ |
| 1   | Fork a foldered session   | ✅ Fork goes to History | ✅ Correct (fork is new) |
| 2   | Fork an archived session  | ❓ Not checked          | ⚠️ Should we allow?      |
| 3   | Fork a fork (nested fork) | ✅ Allowed              | ✅ Creates fork chain    |
| 4   | Fork while streaming      | ❓ Not checked          | ⚠️ Should disable        |
| 5   | Delete source before fork | ❌ Error                | ✅ Expected behavior     |

---

## 4. Fork Tree Scenarios

### 4.1 Simple Fork Tree

```
Root Session (A)
├── Fork @ turn 2 (B)
└── Fork @ turn 5 (C)
```

**Movement Rules**:

- Moving A to folder: Only A moves, B and C stay in History
- Archiving A: Only A archived, B and C still visible
- Deleting A: ❌ BLOCKED (has children)

**Problem**: Users expect tree operations to be hierarchical.

### 4.2 Deep Fork Chain

```
Session A
└── Fork @ turn 3 (B)
    └── Fork @ turn 2 (C)
        └── Fork @ turn 1 (D)
```

**Movement Rules**:

- Each session is independent
- Moving B doesn't affect A, C, or D
- Deleting B: ❌ BLOCKED (C is child)

**Problem**: Can't delete intermediate nodes without deleting all descendants first.

### 4.3 Fork + Folder Combinations

```
Folder "Kitchen Project"
├── Session A (original)
└── Session B (fork of A)

History (inbox)
└── Session C (fork of A, not in folder)
```

**Scenarios**:

1. Move B to History: B appears in inbox, still in folder? No, unassigned.
2. Move C to folder: C disappears from inbox, appears in folder.
3. Archive A: A hidden in folder, B and C still visible.
4. Delete folder: A and B go to History.

---

## 5. Edge Cases & Bugs

### 5.1 🔴 Critical: Invisible Sessions

**Scenario**:

1. Session X is in Folder A
2. User archives Session X
3. User deletes Folder A
4. Session X is archived AND not in any folder
5. Session X is invisible (not in History, not in any folder)

**Current Behavior**: Session exists in DB but unreachable.

**Fix Options**:

1. Unarchive on folder delete
2. Show archived sessions in special "Archive" view
3. Add "Show all sessions" admin view

---

### 5.2 🔴 Critical: Fork Tree Fragmentation

**Scenario**:

1. Root session A has forks B and C
2. User folders A but not B or C
3. History shows B and C as orphaned sessions
4. User confused: "Where is A?"

**Current Behavior**: Tree structure broken in UI.

**Fix Options**:

1. Folder entire fork tree when parent is foldered
2. Show fork parent in History even if foldered (ghost entry)
3. Show fork tree in folder view (nested structure)

---

### 5.3 🟡 Medium: Archive + Folder Conflict

**Scenario**:

1. Session X is in Folder A
2. User archives Session X
3. Session X disappears from Folder A
4. User confused: "Where did my session go?"

**Current Behavior**: Archived sessions hidden everywhere.

**Fix Options**:

1. Show archived sessions in folder (greyed out)
2. Require unarchive before folder view
3. Add "Show archived" toggle per folder

---

### 5.4 🟡 Medium: Many-to-Many Folder Assignment

**Scenario**:

1. Session X is in Folder A AND Folder B
2. User archives Session X
3. Session X disappears from BOTH folders

**Current Behavior**: Correct (archived = hidden everywhere).

**But**: If user unassigns from Folder A, should it stay in Folder B?

**Answer**: Yes, independent operations.

---

### 5.5 🟡 Medium: Race Conditions

**Scenario**:

1. User drags session to Folder A
2. While dragging, another tab deletes the session
3. Drop completes, but session is gone

**Current Behavior**: Optimistic update shows session in folder, then rolls back.

**Fix**: Validate session exists before assign.

---

### 5.6 🟢 Low: Cascade Delete Semantics

**Current Behavior**:

- Delete folder → CASCADE deletes `session_folders` entries
- Delete session → CASCADE deletes `session_folders` entries
- Delete session → CASCADE deletes notes

**Missing**:

- Delete fork parent → BLOCKED (has children)
- No cascade for fork trees

---

## 6. Proposed State Machine

### 6.1 Valid Transitions

```typescript
type SessionState = 'active' | 'foldered' | 'archived' | 'forked';

interface Transition {
    from: SessionState[];
    to: SessionState;
    action: string;
    preconditions?: string[];
}

const transitions: Transition[] = [
    // History → Folder
    {
        from: ['active', 'forked'],
        to: 'foldered',
        action: 'assignSession',
        preconditions: ['session exists', 'folder exists', 'not already in folder']
    },

    // Folder → History
    {
        from: ['foldered'],
        to: 'active',
        action: 'unassignSession',
        preconditions: ['session is in folder']
    },

    // Any → Archived
    {
        from: ['active', 'foldered', 'forked'],
        to: 'archived',
        action: 'archive',
        preconditions: ['session exists', 'not already archived']
    },

    // Archived → Previous State
    {
        from: ['archived'],
        to: 'active', // or 'foldered' if still assigned
        action: 'unarchive',
        preconditions: ['session is archived']
    },

    // Create Fork
    {
        from: ['active', 'foldered'],
        to: 'forked',
        action: 'forkSession',
        preconditions: ['source exists', 'turn_index valid']
    }
];
```

### 6.2 Compound States

```typescript
interface SessionFlags {
    isArchived: boolean;
    isFoldered: boolean;
    isFork: boolean;
    isForkParent: boolean;
    hasActiveChildren: boolean;
    hasArchivedChildren: boolean;
}

// Derived states
function getDisplayState(flags: SessionFlags): DisplayState {
    if (flags.isArchived) return 'hidden'; // Unless "show archived" enabled
    if (flags.isFoldered) return 'in-folder';
    if (flags.isFork) return 'fork-inbox';
    return 'inbox';
}
```

---

## 7. Recommended Fixes

### 7.1 Immediate (P0)

| #   | Issue                       | Fix                                    | Effort |
| --- | --------------------------- | -------------------------------------- | ------ |
| 1   | Invisible archived sessions | Add "Archive" view in sidebar          | 2h     |
| 2   | Fork tree fragmentation     | Show fork indicator in History         | 1h     |
| 3   | Archive during streaming    | Disable archive button while streaming | 30m    |

### 7.2 Short-term (P1)

| #   | Issue                          | Fix                              | Effort |
| --- | ------------------------------ | -------------------------------- | ------ |
| 4   | Cascade archive for fork trees | Option to archive entire tree    | 2h     |
| 5   | Folder fork trees              | Option to folder entire tree     | 2h     |
| 6   | Archive visibility in folders  | Show archived in folder (greyed) | 1h     |

### 7.3 Long-term (P2)

| #   | Issue                   | Fix                              | Effort |
| --- | ----------------------- | -------------------------------- | ------ |
| 7   | Many-to-many folder UX  | Show "also in..." indicator      | 2h     |
| 8   | Fork tree visualization | Tree view in folder              | 4h     |
| 9   | Bulk operations         | Select multiple → folder/archive | 4h     |

---

## 8. Test Scenarios

### 8.1 Movement Tests

```typescript
describe('Session Movement', () => {
    test('assign session to folder removes from History');
    test('unassign session returns to History');
    test('assign to multiple folders (many-to-many)');
    test('unassign from one folder keeps in others');
    test('archive session hides from History AND folders');
    test('unarchive session returns to previous location');
    test('assign archived session (blocked or allowed?)');
    test('unassign archived session (invisible!)');
});
```

### 8.2 Fork Tree Tests

```typescript
describe('Fork Tree Movement', () => {
    test('fork appears in History regardless of parent location');
    test('folder parent does NOT folder children');
    test('archive parent does NOT archive children');
    test('delete parent BLOCKED if children exist');
    test('delete children allows parent deletion');
    test('fork of foldered session creates fork in History');
    test('fork of archived session (blocked or allowed?)');
});
```

### 8.3 Edge Case Tests

```typescript
describe('Edge Cases', () => {
    test('delete folder unarchives sessions (prevents invisible)');
    test('assign during streaming is disabled');
    test('assign to deleted folder shows error');
    test('rapid assign-unassign race condition');
    test('fork chain: A→B→C, delete B blocked');
    test('fork chain: A→B→C, delete C allows B deletion');
});
```

---

## 9. Open Questions

| #   | Question                                           | Options                                   | Recommendation        |
| --- | -------------------------------------------------- | ----------------------------------------- | --------------------- |
| 1   | Should archived sessions be assignable to folders? | Yes / No / With warning                   | No (archive = frozen) |
| 2   | Should archiving a parent archive children?        | Yes / No / Ask user                       | Ask user (checkbox)   |
| 3   | Should foldering a parent folder children?         | Yes / No / Ask user                       | No (independent)      |
| 4   | Where do archived sessions appear?                 | Nowhere / Archive view / Greyed in folder | Archive view          |
| 5   | Can you fork an archived session?                  | Yes / No                                  | No (read-only)        |
| 6   | Can you send messages in archived session?         | Yes / No                                  | No (read-only)        |
| 7   | What happens to folders when session deleted?      | Cascade / Restrict                        | Cascade (current)     |
| 8   | What happens to forks when session deleted?        | Cascade / Restrict                        | Restrict (current)    |

---

## 10. Implementation Priority

### Phase 1: Fix Critical Bugs (4h)

- [ ] Add Archive view in sidebar
- [ ] Disable archive/send during streaming
- [ ] Show fork indicators in History

### Phase 2: Improve Fork UX (4h)

- [ ] Option to archive/unarchive entire fork tree
- [ ] Option to folder entire fork tree
- [ ] Show fork tree in folder view

### Phase 3: Advanced Features (8h)

- [ ] Many-to-many folder indicators
- [ ] Bulk operations (multi-select)
- [ ] Fork tree visualization
- [ ] Session movement history (audit log)

---

## Appendix: Current Code References

| Operation            | Frontend                        | Backend                            |
| -------------------- | ------------------------------- | ---------------------------------- |
| Archive              | `sessionStore.archive()`        | `session_repo.archive_session()`   |
| Unarchive            | `sessionStore.unarchive()`      | `session_repo.unarchive_session()` |
| Assign to folder     | `folderStore.assignSession()`   | `folder_repo.assign_session()`     |
| Unassign from folder | `folderStore.unassignSession()` | `folder_repo.unassign_session()`   |
| Fork                 | `chatStore.forkSession()`       | `session_repo.fork_session()`      |
| Delete               | `sessionStore.delete()`         | `session_repo.delete_session()`    |
| Delete folder        | `folderStore.deleteFolder()`    | `folder_repo.delete_folder()`      |
