# Production Svelte 5 Patterns — Complete Architectural Guide

---

## 1. Typed State Machines (Status Enums over Booleans)

**Why:** Booleans explode combinatorially. Two booleans = 4 states, three = 8. Enums make impossible states unrepresentable.

```typescript
// src/lib/types/states.ts
export type AsyncStatus = 'idle' | 'loading' | 'streaming' | 'error' | 'success';

export type RemoteData<T, E = string> =
    | { status: 'idle' }
    | { status: 'loading' }
    | { status: 'streaming'; partial: string }
    | { status: 'error'; error: E }
    | { status: 'success'; data: T };
```

```svelte
<!-- Usage in component -->
<script lang="ts">
  import type { RemoteData } from '$lib/types/states';

  let response = $state<RemoteData<string>>({ status: 'idle' });
</script>

{#if response.status === 'idle'}
  <button onclick={() => response = { status: 'loading' }}>Ask</button>

{:else if response.status === 'loading'}
  <Spinner />

{:else if response.status === 'streaming'}
  <StreamingBubble text={response.partial} />

{:else if response.status === 'error'}
  <ErrorBanner message={response.error} />

{:else if response.status === 'success'}
  <ResultCard data={response.data} />
{/if}
```

---

## 2. Repository Pattern for API Calls

**Why:** Swap backends, mock in tests, add caching — all without touching a single component.

```typescript
// src/lib/repositories/chat.repository.ts
import type { Message, ChatResponse } from '$lib/types';

export interface IChatRepository {
    send(sessionId: string, message: string): Promise<ChatResponse>;
    getHistory(sessionId: string): Promise<Message[]>;
    clearSession(sessionId: string): Promise<void>;
}

// Real implementation
export class ChatRepository implements IChatRepository {
    constructor(
        private baseUrl: string,
        private getToken: () => string
    ) {}

    async send(sessionId: string, message: string): Promise<ChatResponse> {
        const res = await fetch(`${this.baseUrl}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${this.getToken()}`
            },
            body: JSON.stringify({ session_id: sessionId, message })
        });

        if (!res.ok) throw new ApiError(res.status, await res.text());
        return res.json();
    }

    async getHistory(sessionId: string): Promise<Message[]> {
        const res = await fetch(`${this.baseUrl}/sessions/${sessionId}/history`, {
            headers: { Authorization: `Bearer ${this.getToken()}` }
        });
        if (!res.ok) throw new ApiError(res.status, await res.text());
        return res.json();
    }

    async clearSession(sessionId: string): Promise<void> {
        await fetch(`${this.baseUrl}/sessions/${sessionId}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${this.getToken()}` }
        });
    }
}

// Mock for tests/storybook
export class MockChatRepository implements IChatRepository {
    async send(_sessionId: string, message: string): Promise<ChatResponse> {
        await new Promise((r) => setTimeout(r, 500)); // simulate latency
        return { text: `Echo: ${message}`, toolCalls: [] };
    }
    async getHistory(): Promise<Message[]> {
        return [];
    }
    async clearSession(): Promise<void> {}
}

// Error type
export class ApiError extends Error {
    constructor(
        public status: number,
        message: string
    ) {
        super(message);
        this.name = 'ApiError';
    }
}
```

```typescript
// src/lib/di.ts — wire it up once
import { ChatRepository, MockChatRepository } from '$lib/repositories/chat.repository';

const isDev = import.meta.env.MODE === 'test';

export const chatRepo = isDev
    ? new MockChatRepository()
    : new ChatRepository(import.meta.env.VITE_API_URL, () => localStorage.getItem('token') ?? '');
```

---

## 3. Rune-Based Store with Clear Ownership

**Why:** A well-designed store is the backbone of your app. Every field should be intentional — no accidental mutations.

```typescript
// src/lib/stores/chat.svelte.ts
import type { Message } from '$lib/types';
import type { RemoteData } from '$lib/types/states';
import { chatRepo } from '$lib/di';

function createChatStore() {
    // --- State (private shape, public reads via getters) ---
    let messages = $state<Message[]>([]);
    let status = $state<RemoteData<string>>({ status: 'idle' });
    let sessionId = $state<string>(crypto.randomUUID());
    let inputDraft = $state<string>('');

    return {
        // --- Reads ---
        get messages() {
            return messages;
        },
        get status() {
            return status;
        },
        get sessionId() {
            return sessionId;
        },
        get inputDraft() {
            return inputDraft;
        },
        get isBlocked() {
            return status.status === 'loading' || status.status === 'streaming';
        },

        // --- Writes ---
        setDraft(v: string) {
            inputDraft = v;
        },

        async send(text: string) {
            if (!text.trim() || this.isBlocked) return;

            messages.push({ role: 'user', content: text });
            inputDraft = '';
            status = { status: 'loading' };

            try {
                const data = await chatRepo.send(sessionId, text);
                messages.push({ role: 'assistant', content: data.text });
                status = { status: 'success', data: data.text };
            } catch (err) {
                const msg = err instanceof Error ? err.message : 'Unknown error';
                status = { status: 'error', error: msg };
            }
        },

        clearSession() {
            messages = [];
            status = { status: 'idle' };
            sessionId = crypto.randomUUID();
        }
    };
}

// Singleton — one instance for the whole app
export const chatStore = createChatStore();
```

---

## 4. Streaming with Async Iterators

**Why:** Real LLM UIs stream tokens. Polling is not acceptable commercially.

```typescript
// src/lib/repositories/chat.repository.ts (add to class)
async *stream(sessionId: string, message: string): AsyncGenerator<string> {
  const res = await fetch(`${this.baseUrl}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message })
  });

  if (!res.ok || !res.body) throw new ApiError(res.status, 'Stream failed');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });

      // SSE parsing
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data === '[DONE]') return;
          try {
            const parsed = JSON.parse(data);
            yield parsed.delta ?? '';
          } catch {}
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
```

```typescript
// In the store
async sendStreaming(text: string) {
  if (!text.trim() || this.isBlocked) return;

  messages.push({ role: 'user', content: text });
  inputDraft = '';

  // Add empty assistant bubble immediately
  messages.push({ role: 'assistant', content: '' });
  const lastIdx = messages.length - 1;

  status = { status: 'streaming', partial: '' };

  try {
    for await (const token of chatRepo.stream(sessionId, text)) {
      messages[lastIdx] = {
        ...messages[lastIdx],
        content: messages[lastIdx].content + token
      };
      status = { status: 'streaming', partial: messages[lastIdx].content };
    }
    status = { status: 'success', data: messages[lastIdx].content };
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Stream error';
    status = { status: 'error', error: msg };
  }
}
```

---

## 5. Compound Components Pattern

**Why:** Avoids "prop drilling hell" on complex widgets. The parent controls layout, children control their own rendering.

```svelte
<!-- src/lib/components/Card/index.svelte -->
<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    header?: Snippet;
    footer?: Snippet;
    children: Snippet;
    variant?: 'default' | 'elevated' | 'ghost';
  }

  let { header, footer, children, variant = 'default' }: Props = $props();

  const variants = {
    default:  'bg-white border border-gray-200',
    elevated: 'bg-white shadow-lg',
    ghost:    'bg-transparent'
  };
</script>

<div class="rounded-xl p-4 {variants[variant]}">
  {#if header}
    <header class="mb-3 border-b pb-3">
      {@render header()}
    </header>
  {/if}

  <div class="content">
    {@render children()}
  </div>

  {#if footer}
    <footer class="mt-3 border-t pt-3">
      {@render footer()}
    </footer>
  {/if}
</div>
```

```svelte
<!-- Usage -->
<Card variant="elevated">
  {#snippet header()}
    <h2 class="font-bold">Session Stats</h2>
  {/snippet}

  <p>Messages: {chatStore.messages.length}</p>

  {#snippet footer()}
    <button onclick={chatStore.clearSession}>Clear</button>
  {/snippet}
</Card>
```

---

## 6. Derived State via `$derived.by`

**Why:** Never compute in templates. Derived state is cacheable, testable, and readable.

```typescript
// src/lib/stores/chat.svelte.ts (add to store)

// Complex derivations belong in $derived.by, not template expressions
const stats = $derived.by(() => {
  const userMsgs      = messages.filter(m => m.role === 'user');
  const assistantMsgs = messages.filter(m => m.role === 'assistant');
  const totalTokens   = messages.reduce((acc, m) => acc + estimateTokens(m.content), 0);
  const hasError      = status.status === 'error';

  return {
    userCount:      userMsgs.length,
    assistantCount: assistantMsgs.length,
    totalTokens,
    hasError,
    isEmpty:        messages.length === 0
  };
});

// Expose it
get stats() { return stats; }
```

```svelte
<!-- ✅ Clean template — no logic inline -->
{#if chatStore.stats.isEmpty}
  <EmptyState />
{:else}
  <TokenCounter count={chatStore.stats.totalTokens} />
{/if}
```

---

## 7. Action Pattern for DOM Behaviours

**Why:** Reusable DOM logic (focus traps, auto-resize, intersection observers) without duplicating it per component.

```typescript
// src/lib/actions/autoresize.ts
import type { Action } from 'svelte/action';

export const autoresize: Action<HTMLTextAreaElement> = (node) => {
    function resize() {
        node.style.height = 'auto';
        node.style.height = `${node.scrollHeight}px`;
    }

    resize();
    node.addEventListener('input', resize);

    return {
        destroy() {
            node.removeEventListener('input', resize);
        }
    };
};
```

```typescript
// src/lib/actions/focustrap.ts
export const focusTrap: Action<HTMLElement> = (node) => {
    const focusable = 'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])';

    function handleKeydown(e: KeyboardEvent) {
        if (e.key !== 'Tab') return;

        const els = [...node.querySelectorAll<HTMLElement>(focusable)];
        const first = els[0];
        const last = els[els.length - 1];

        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    }

    node.addEventListener('keydown', handleKeydown);
    return {
        destroy() {
            node.removeEventListener('keydown', handleKeydown);
        }
    };
};
```

```svelte
<!-- Usage — clean, zero boilerplate in component -->
<textarea use:autoresize bind:value={chatStore.inputDraft}></textarea>

<dialog use:focusTrap>
  <!-- keyboard accessible modal -->
</dialog>
```

---

## 8. Context API for Dependency Injection

**Why:** Avoids prop drilling through 5 component layers. The context is scoped to a subtree, not global.

```typescript
// src/lib/context/chat.context.ts
import { getContext, setContext } from 'svelte';
import type { ChatStore } from '$lib/stores/chat.svelte';

const CHAT_KEY = Symbol('chat');

export function setChatContext(store: ChatStore) {
    setContext(CHAT_KEY, store);
}

export function useChatContext(): ChatStore {
    const ctx = getContext<ChatStore>(CHAT_KEY);
    if (!ctx) throw new Error('useChatContext must be used inside a ChatProvider');
    return ctx;
}
```

```svelte
<!-- src/lib/components/ChatProvider.svelte -->
<script lang="ts">
  import { setChatContext } from '$lib/context/chat.context';
  import { createChatStore } from '$lib/stores/chat.svelte';
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();

  // Each provider gets its OWN store instance — enables multiple chat sessions
  setChatContext(createChatStore());
</script>

{@render children()}
```

```svelte
<!-- DeepChild.svelte — no props needed, no imports of global store -->
<script lang="ts">
  import { useChatContext } from '$lib/context/chat.context';
  const chat = useChatContext();
</script>

<p>{chat.stats.totalTokens} tokens used</p>
```

---

## 9. Error Boundary Pattern

**Why:** One crashed component shouldn't white-screen your entire app.

```svelte
<!-- src/lib/components/ErrorBoundary.svelte -->
<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    children: Snippet;
    fallback?: Snippet<[Error]>;
  }

  let { children, fallback }: Props = $props();
  let error = $state<Error | null>(null);

  // Svelte 5 error boundary hook
  function onerror(err: Error) {
    error = err;
    console.error('[ErrorBoundary]', err);
  }
</script>

<svelte:boundary {onerror}>
  {#if error}
    {#if fallback}
      {@render fallback(error)}
    {:else}
      <div class="rounded border border-red-300 bg-red-50 p-4">
        <p class="font-bold text-red-700">Something went wrong</p>
        <pre class="text-sm text-red-600">{error.message}</pre>
        <button onclick={() => error = null}>Retry</button>
      </div>
    {/if}
  {:else}
    {@render children()}
  {/if}
</svelte:boundary>
```

```svelte
<!-- Usage -->
<ErrorBoundary>
  {#snippet fallback(err)}
    <MyCustomErrorUI message={err.message} />
  {/snippet}

  <RiskyComponent />
</ErrorBoundary>
```

---

## 10. Virtual List for Large Datasets

**Why:** Rendering 10,000 chat messages destroys performance. Only render what's visible.

```svelte
<!-- src/lib/components/VirtualList.svelte -->
<script lang="ts" generics="T">
  import type { Snippet } from 'svelte';

  interface Props {
    items: T[];
    itemHeight: number;
    renderItem: Snippet<[T, number]>;
    overscan?: number;
  }

  let { items, itemHeight, renderItem, overscan = 3 }: Props = $props();

  let scrollTop   = $state(0);
  let clientHeight = $state(0);

  const totalHeight  = $derived(items.length * itemHeight);
  const startIndex   = $derived(Math.max(0, Math.floor(scrollTop / itemHeight) - overscan));
  const endIndex     = $derived(Math.min(items.length, Math.ceil((scrollTop + clientHeight) / itemHeight) + overscan));
  const visibleItems = $derived(items.slice(startIndex, endIndex));
  const offsetY      = $derived(startIndex * itemHeight);
</script>

<div
  class="overflow-y-auto"
  style="height: 100%"
  onscroll={(e) => scrollTop = e.currentTarget.scrollTop}
  bind:clientHeight
>
  <div style="height: {totalHeight}px; position: relative;">
    <div style="transform: translateY({offsetY}px);">
      {#each visibleItems as item, i}
        {@render renderItem(item, startIndex + i)}
      {/each}
    </div>
  </div>
</div>
```

```svelte
<!-- Usage -->
<VirtualList items={chatStore.messages} itemHeight={80}>
  {#snippet renderItem(msg, i)}
    <ChatBubble role={msg.role} content={msg.content} />
  {/snippet}
</VirtualList>
```

---

## 11. Optimistic UI Updates

**Why:** Instant feedback. Users don't wait for the server to see their action reflected.

```typescript
// In store
async toggleFavourite(messageId: string) {
  // 1. Optimistically update immediately
  const msg = messages.find(m => m.id === messageId);
  if (!msg) return;

  const previousValue = msg.isFavourite;
  msg.isFavourite = !previousValue;   // instant UI update

  try {
    // 2. Confirm with server in background
    await chatRepo.toggleFavourite(messageId, msg.isFavourite);
  } catch {
    // 3. Rollback on failure
    msg.isFavourite = previousValue;
    status = { status: 'error', error: 'Failed to save favourite' };
  }
}
```

---

## 12. Form Validation with Typed Schema

**Why:** Validate once, share schema between frontend and backend. Runtime + compile-time safety.

```typescript
// src/lib/schemas/chat.schema.ts
import { z } from 'zod'; // pnpm add zod

export const MessageSchema = z.object({
    content: z.string().min(1, 'Message cannot be empty').max(4000, 'Message too long'),
    sessionId: z.string().uuid()
});

export type MessageForm = z.infer<typeof MessageSchema>;
```

```svelte
<!-- ChatInput.svelte -->
<script lang="ts">
  import { MessageSchema } from '$lib/schemas/chat.schema';

  let { onsend }: { onsend: (msg: string) => void } = $props();

  let text    = $state('');
  let errors  = $state<Record<string, string>>({});

  function validate(): boolean {
    const result = MessageSchema.safeParse({
      content:   text,
      sessionId: 'placeholder-uuid'
    });

    if (!result.success) {
      errors = Object.fromEntries(
        result.error.errors.map(e => [e.path[0], e.message])
      );
      return false;
    }

    errors = {};
    return true;
  }

  function handleSubmit() {
    if (!validate()) return;
    onsend(text);
    text = '';
  }
</script>

<div>
  <textarea bind:value={text} oninput={() => errors = {}} />
  {#if errors.content}
    <p class="text-sm text-red-500">{errors.content}</p>
  {/if}
  <button onclick={handleSubmit}>Send</button>
</div>
```

---

## Pattern Summary

| Pattern             | Problem Solved              | Complexity |
| ------------------- | --------------------------- | ---------- |
| State machines      | Boolean explosion           | Low        |
| Repository          | Testable API layer          | Low        |
| Rune store          | Predictable mutations       | Medium     |
| Streaming           | LLM token-by-token UI       | Medium     |
| Compound components | Flexible composition        | Low        |
| `$derived.by`       | Clean templates             | Low        |
| Actions             | Reusable DOM logic          | Low        |
| Context API         | Scoped DI, no prop drilling | Medium     |
| Error boundary      | Resilient UI                | Low        |
| Virtual list        | 10k+ item performance       | High       |
| Optimistic UI       | Perceived performance       | Medium     |
| Zod schemas         | Type-safe validation        | Low        |

These patterns are not Svelte-specific inventions — they map directly to React's patterns (hooks → runes, context → context, HOC → snippets). The advantage in Svelte 5 is that the boilerplate is dramatically lower while the guarantees are the same.
