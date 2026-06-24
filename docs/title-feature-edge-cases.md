# Title Feature — Edge Cases & Error Handling

## Edge Cases Matrix

| #   | Scenario                            | Backend Behavior     | Frontend Behavior           | User Feedback                             |
| --- | ----------------------------------- | -------------------- | --------------------------- | ----------------------------------------- |
| 1   | **Empty session** (no messages)     | Return 400           | Show toast                  | "Cannot generate title for empty session" |
| 2   | **LLM API failure** (network, auth) | Return 500           | Show toast + keep menu open | "Title generation failed: {error}"        |
| 3   | **LLM returns empty text**          | Use fallback title   | Show toast                  | "Could not generate title, using default" |
| 4   | **LLM returns too long title**      | Truncate to 60 chars | Silently accept             | (none)                                    |
| 5   | **Session not found**               | Return 404           | Show toast                  | "Session not found"                       |
| 6   | **Rate limiting**                   | Return 429           | Show toast                  | "Too many requests, try again later"      |
| 7   | **Concurrent edits**                | Last write wins      | Refresh after save          | (none)                                    |
| 8   | **Title with special chars**        | Store as-is          | Display correctly           | (none)                                    |
| 9   | **Backend down**                    | Connection refused   | Show toast                  | "Cannot connect to server"                |
| 10  | **User cancels during generation**  | N/A                  | Disable menu items          | Show spinner                              |

---

## Implementation Plan

### 1. Backend Error Handling

```python
# Current issues:
# - Generic error messages
# - No validation for empty sessions
# - No handling for LLM returning empty text

# Improvements needed:
```

#### A. Validate session has messages

```python
if not ui_messages:
    raise HTTPException(
        status_code=400,
        detail="Cannot generate title for empty session",
    )
```

#### B. Handle empty LLM response

```python
title = normalized.text.strip()
if not title:
    # Fallback: use first user message snippet
    user_msgs = [m for m in ui_messages if m.get("role") == "user"]
    if user_msgs:
        title = user_msgs[0].get("content", "")[:50].strip()
        if len(user_msgs[0].get("content", "")) > 50:
            title += "..."
    else:
        title = f"Session {session_id[:8]}"
```

#### C. Better error messages

```python
except Exception as e:
    error_msg = str(e)
    if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
        detail = "API key invalid or missing"
    elif "rate" in error_msg.lower() or "429" in error_msg:
        detail = "Rate limited, try again later"
    elif "timeout" in error_msg.lower():
        detail = "Request timed out, try again"
    else:
        detail = f"Title generation failed: {error_msg}"
```

### 2. Frontend Error Handling

#### A. Toast notifications

```typescript
// In SessionPanel or page component
let titleError = $state('');
let titleErrorTimer: ReturnType<typeof setTimeout>;

function showTitleError(msg: string) {
    clearTimeout(titleErrorTimer);
    titleError = msg;
    titleErrorTimer = setTimeout(() => (titleError = ''), 5000);
}

async function handleTitleGenerate(id: string): Promise<void> {
    try {
        const result = await api.generateSessionTitle(id);
        await sessionStore.refresh();
    } catch (e) {
        const msg = e instanceof Error ? e.message : 'Unknown error';
        showTitleError(`Title generation failed: ${msg}`);
        throw e; // Re-throw so menu can handle it
    }
}
```

#### B. Loading state in context menu

```svelte
{#if menuState === 'generating-title'}
    <div class="px-3 py-2 text-xs text-muted">
        <span class="animate-spin inline-block mr-1">⏳</span>
        Generating title...
    </div>
{/if}
```

#### C. Disable other menu items while generating

```svelte
<button
    onclick={handleExport}
    disabled={isBusy}
    class:opacity-50={isBusy}
    class:cursor-not-allowed={isBusy}
>
```

### 3. UX Improvements

#### A. Optimistic update

```typescript
async function handleTitleGenerate(id: string): Promise<void> {
    // Show temporary "Generating..." title
    const node = sessionStore.flat.find((n) => n.id === id);
    if (node) {
        const originalTitle = node.title;
        node.title = 'Generating...';

        try {
            const result = await api.generateSessionTitle(id);
            await sessionStore.refresh();
        } catch (e) {
            // Revert on error
            node.title = originalTitle;
            throw e;
        }
    }
}
```

#### B. Retry button in error toast

```svelte
{#if titleError}
    <div class="error-toast">
        <span>{titleError}</span>
        <button onclick={() => handleTitleGenerate(lastFailedId)}>
            Retry
        </button>
    </div>
{/if}
```

#### C. Confirmation for overwrite

```svelte
{#if node.title && menuState === 'confirming-title-overwrite'}
    <div class="confirm-dialog">
        <p>Replace "{node.title}" with AI-generated title?</p>
        <button onclick={confirmGenerate}>Yes</button>
        <button onclick={cancelGenerate}>No</button>
    </div>
{/if}
```

---

## Testing Checklist

- [ ] Empty session → 400 error → toast shown
- [ ] LLM timeout → 500 error → toast shown
- [ ] LLM returns empty → fallback title used
- [ ] LLM returns long title → truncated to 60 chars
- [ ] Network error → connection error toast
- [ ] Click generate while already generating → button disabled
- [ ] Generate title for session with special chars → works
- [ ] Generate title → sidebar updates immediately
- [ ] Cancel during generation → no crash
- [ ] Multiple rapid clicks → only one request

---

## Priority Order

1. **Fix current bug** (AssembledContext params) ✅ Done
2. **Add empty session validation** (backend)
3. **Add fallback for empty LLM response** (backend)
4. **Add toast notifications** (frontend)
5. **Add loading states** (frontend)
6. **Add confirmation for overwrite** (frontend)
7. **Add retry button** (frontend)
