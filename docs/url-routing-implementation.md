# URL-Based Session Routing Implementation

## Summary

Implemented URL-based routing for chat sessions to preserve the current session across browser refreshes. The URL (`/chat/{id}`) is now the single source of truth for the active session.

## Files Changed

### 1. **`frontend/src/routes/chat/[id]/+page.svelte`** (NEW)

- Moved the entire chat UI from `+page.svelte` to this dynamic route
- Session ID comes from `$page.params.id` via SvelteKit routing
- Added `$effect` to watch URL changes and load sessions automatically
- Added `beforeNavigate` guard to prevent navigation while streaming
- Uses `goto()` for all navigation (new chat, session switch, fork)

### 2. **`frontend/src/routes/+page.svelte`** (MODIFIED)

- Now just a redirect page: generates a new UUID and redirects to `/chat/{uuid}`
- Landing page behavior: always starts with a fresh chat

### 3. **`frontend/src/lib/stores/chat.svelte.ts`** (MODIFIED)

#### `loadSession(id)` — Enhanced 404 handling

```typescript
// Before: catch block just logged error
catch (e) {
    console.error('Failed to load session', e);
}

// After: graceful degradation for new/missing sessions
catch (e) {
    console.warn('Session not found or failed to load, starting fresh:', id);
    sessionId = id;
    messages = [];
    chatState = { status: 'idle' };
    // ... reset all state
}
```

#### `startNewChat()` → `resetForNewChat()`

- Renamed to clarify it only resets state, not navigation
- No longer generates UUID (URL handles this)
- No longer sets `sessionId` (will be set by `loadSession()`)

#### `forkSession()` — Returns new ID

```typescript
// Before: loaded session directly
await this.loadSession(data.new_session_id);

// After: returns ID for navigation
return data.new_session_id;
```

## Navigation Flow

### Before (No URL routing)

```
User clicks session → chatStore.loadSession(id) → sessionId changes in-memory
User refreshes → crypto.randomUUID() → blank new chat (lost!)
```

### After (URL-based)

```
User clicks session → goto('/chat/{id}') → URL changes → $effect → loadSession(id)
User refreshes → URL still has /chat/{id} → $effect → loadSession(id) → restored!
```

## Edge Cases Handled

| Scenario                                    | Behavior                                               |
| ------------------------------------------- | ------------------------------------------------------ |
| **New chat via URL** (`/chat/{fresh-uuid}`) | 404 → empty chat → first message creates session       |
| **Deleted session in URL**                  | 404 → empty chat                                       |
| **Streaming + navigation**                  | `beforeNavigate` cancels navigation                    |
| **Streaming + refresh**                     | Backend finishes, saves to DB, reload shows result     |
| **Browser back/forward**                    | SvelteKit fires `$effect` → `loadSession()` called     |
| **Sidebar resize URL params**               | Uses `replaceState` on search params only, no conflict |

## Testing

```bash
npm run check  # TypeScript: 0 errors
npm test       # Unit tests: 28 passed
```

## How to Test Manually

1. Open the app → redirects to `/chat/{uuid}`
2. Send a message → message appears
3. **Refresh the browser** (F5) → session is restored!
4. Copy the URL, open in new tab → same session loads
5. Click "New chat" → navigates to `/chat/{new-uuid}`
6. Click a session in sidebar → navigates to `/chat/{that-id}`
7. Use browser back/forward → correct session loads
8. Try to navigate while streaming → blocked by guard
