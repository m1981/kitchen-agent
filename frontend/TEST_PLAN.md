Test Design: Component vs E2E

### Testing Pyramid for Message Deletion Feature

```
           ╱╲
          ╱  ╲         E2E Tests (few)
         ╱    ╲        - Full user flows
        ╱──────╲       - Real API integration
       ╱        ╲
      ╱ Component ╲    Component Tests (many)
     ╱    Tests    ╲   - Isolated component behavior
    ╱───────────────╲  - Mocked dependencies
   ╱   Unit Tests    ╲ - Pure logic, no DOM
  ╱───────────────────╲
```

────────────────────────────────────────────────────────────────────────────────

1.  Component Tests (Vitest + Playwright)

### Test File Structure

```
  src/lib/components/
  ├── ChatMessageList.svelte
  ├── ChatMessageList.spec.ts      # Component tests
  ├── ConfirmDialog.svelte
  ├── ConfirmDialog.spec.ts
  ├── TruncateBar.svelte
  ├── TruncateBar.spec.ts
  └── ...

  src/lib/stores/
  ├── chat.svelte.ts
  ├── chat.spec.ts                 # Store unit tests
  └── ...
```

────────────────────────────────────────────────────────────────────────────────

### ChatMessageList.spec.ts

```typescript
import { render, screen, fireEvent } from 'vitest-browser-svelte';
import { describe, it, expect, vi } from 'vitest';
import ChatMessageList from './ChatMessageList.svelte';
import type { Message } from '$lib/api';

// Test fixtures
const mockMessages: Message[] = [
	{ role: 'user', content: 'Hello', turn_id: 'user-1' },
	{ role: 'assistant', content: 'Hi there', turn_id: 'asst-1' },
	{ role: 'user', content: 'How are you?', turn_id: 'user-2' },
	{ role: 'assistant', content: 'I am fine', turn_id: 'asst-2' }
];

const defaultProps = {
	messages: mockMessages,
	isLoading: false,
	isBusy: false,
	editingTurnId: null,
	editDraft: '',
	isSavingEdit: false,
	editErrorMessage: '',
	onfork: vi.fn(),
	onedit: vi.fn(),
	ondelete: vi.fn(),
	ondeletepair: vi.fn(),
	onsaveedit: vi.fn(),
	oncanceledit: vi.fn(),
	ondraftchange: vi.fn()
};

describe('ChatMessageList', () => {
	// ── Rendering ──────────────────────────────────────────────────

	it('renders correct number of chat bubbles', () => {
		render(ChatMessageList, { props: defaultProps });

		const bubbles = screen.getAllByTestId('chat-bubble');
		expect(bubbles).toHaveLength(4);
	});

	it('renders user messages on the right', () => {
		render(ChatMessageList, { props: defaultProps });

		const userBubbles = screen.getAllByTestId('chat-bubble[data-chat-bubble="user"]');
		expect(userBubbles[0]).toHaveClass('justify-end');
	});

	it('renders assistant messages on the left', () => {
		render(ChatMessageList, { props: defaultProps });

		const asstBubbles = screen.getAllByTestId('chat-bubble[data-chat-bubble="assistant"]');
		expect(asstBubbles[0]).toHaveClass('justify-start');
	});

	// ── Action Buttons ─────────────────────────────────────────────

	it('shows edit button for messages with turn_id', () => {
		render(ChatMessageList, { props: defaultProps });

		const editButtons = screen.getAllByTestId('edit-btn');
		expect(editButtons).toHaveLength(4); // All messages have turn_id
	});

	it('hides edit button for legacy messages without turn_id', () => {
		const legacyMessages: Message[] = [{ role: 'user', content: 'Legacy', turn_id: undefined }];
		render(ChatMessageList, {
			props: { ...defaultProps, messages: legacyMessages }
		});

		const editButtons = screen.queryAllByTestId('edit-btn');
		expect(editButtons).toHaveLength(0);
	});

	it('shows delete-pair button only for user messages with following assistant', () => {
		render(ChatMessageList, { props: defaultProps });

		const pairButtons = screen.getAllByTestId('delete-pair-btn');
		expect(pairButtons).toHaveLength(2); // user-1 and user-2 have assistants
	});

	// ── Button Disabled State (THE KEY TEST) ───────────────────────

	it('disables all action buttons when isBusy=true', () => {
		render(ChatMessageList, {
			props: { ...defaultProps, isBusy: true }
		});

		const editButtons = screen.getAllByTestId('edit-btn');
		const deleteButtons = screen.getAllByTestId('delete-btn');
		const forkButtons = screen.getAllByTestId('fork-btn');

		editButtons.forEach((btn) => expect(btn).toBeDisabled());
		deleteButtons.forEach((btn) => expect(btn).toBeDisabled());
		forkButtons.forEach((btn) => expect(btn).toBeDisabled());
	});

	it('enables all action buttons when isBusy=false', () => {
		render(ChatMessageList, {
			props: { ...defaultProps, isBusy: false }
		});

		const editButtons = screen.getAllByTestId('edit-btn');
		const deleteButtons = screen.getAllByTestId('delete-btn');

		editButtons.forEach((btn) => expect(btn).not.toBeDisabled());
		deleteButtons.forEach((btn) => expect(btn).not.toBeDisabled());
	});

	// ── Delete Flow ────────────────────────────────────────────────

	it('calls ondelete when delete button is clicked and confirmed', async () => {
		const ondelete = vi.fn();
		render(ChatMessageList, {
			props: { ...defaultProps, ondelete }
		});

		// Click delete button
		const deleteBtn = screen.getAllByTestId('delete-btn')[0];
		await fireEvent.click(deleteBtn);

		// Confirm dialog should appear
		const confirmBtn = screen.getByTestId('confirm-ok');
		await fireEvent.click(confirmBtn);

		// ondelete should be called with correct turn_id
		expect(ondelete).toHaveBeenCalledWith('user-1');
	});

	it('does not call ondelete when cancelled', async () => {
		const ondelete = vi.fn();
		render(ChatMessageList, {
			props: { ...defaultProps, ondelete }
		});

		// Click delete button
		const deleteBtn = screen.getAllByTestId('delete-btn')[0];
		await fireEvent.click(deleteBtn);

		// Cancel dialog
		const cancelBtn = screen.getByTestId('confirm-cancel');
		await fireEvent.click(cancelBtn);

		// ondelete should NOT be called
		expect(ondelete).not.toHaveBeenCalled();
	});

	// ── Loading State ──────────────────────────────────────────────

	it('shows loading indicator when isLoading=true', () => {
		render(ChatMessageList, {
			props: { ...defaultProps, isLoading: true }
		});

		const indicator = screen.getByTestId('loading-indicator');
		expect(indicator).toBeInTheDocument();
	});

	it('hides loading indicator when isLoading=false', () => {
		render(ChatMessageList, {
			props: { ...defaultProps, isLoading: false }
		});

		const indicator = screen.queryByTestId('loading-indicator');
		expect(indicator).not.toBeInTheDocument();
	});
});
```

────────────────────────────────────────────────────────────────────────────────

### ConfirmDialog.spec.ts

```typescript
import { render, screen, fireEvent } from 'vitest-browser-svelte';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ConfirmDialog from './ConfirmDialog.svelte';

describe('ConfirmDialog', () => {
	const defaultProps = {
		message: 'Are you sure?',
		onconfirm: vi.fn(),
		oncancel: vi.fn()
	};

	beforeEach(() => {
		vi.clearAllMocks();
		// Reset auto-confirm flag
		(window as any).__testHelpers = { autoConfirm: false };
	});

	it('renders the message', () => {
		render(ConfirmDialog, { props: defaultProps });

		expect(screen.getByText('Are you sure?')).toBeInTheDocument();
	});

	it('calls onconfirm when confirm button clicked', async () => {
		const onconfirm = vi.fn();
		render(ConfirmDialog, {
			props: { ...defaultProps, onconfirm }
		});

		await fireEvent.click(screen.getByTestId('confirm-ok'));
		expect(onconfirm).toHaveBeenCalledOnce();
	});

	it('calls oncancel when cancel button clicked', async () => {
		const oncancel = vi.fn();
		render(ConfirmDialog, {
			props: { ...defaultProps, oncancel }
		});

		await fireEvent.click(screen.getByTestId('confirm-cancel'));
		expect(oncancel).toHaveBeenCalledOnce();
	});

	it('calls oncancel when backdrop clicked', async () => {
		const oncancel = vi.fn();
		render(ConfirmDialog, {
			props: { ...defaultProps, oncancel }
		});

		// Click the backdrop (parent div)
		const backdrop = screen.getByTestId('confirm-dialog').parentElement;
		await fireEvent.click(backdrop!);
		expect(oncancel).toHaveBeenCalledOnce();
	});

	it('calls oncancel on Escape key', async () => {
		const oncancel = vi.fn();
		render(ConfirmDialog, {
			props: { ...defaultProps, oncancel }
		});

		await fireEvent.keyDown(window, { key: 'Escape' });
		expect(oncancel).toHaveBeenCalledOnce();
	});

	it('calls onconfirm on Enter key', async () => {
		const onconfirm = vi.fn();
		render(ConfirmDialog, {
			props: { ...defaultProps, onconfirm }
		});

		await fireEvent.keyDown(window, { key: 'Enter' });
		expect(onconfirm).toHaveBeenCalledOnce();
	});

	// ── Auto-confirm mode ──────────────────────────────────────────

	it('auto-confirms when __testHelpers.autoConfirm is true', async () => {
		(window as any).__testHelpers = { autoConfirm: true };

		const onconfirm = vi.fn();
		render(ConfirmDialog, {
			props: { ...defaultProps, onconfirm }
		});

		// Wait for requestAnimationFrame
		await vi.waitFor(() => {
			expect(onconfirm).toHaveBeenCalledOnce();
		});
	});

	it('does not auto-confirm when __testHelpers.autoConfirm is false', () => {
		(window as any).__testHelpers = { autoConfirm: false };

		const onconfirm = vi.fn();
		render(ConfirmDialog, {
			props: { ...defaultProps, onconfirm }
		});

		expect(onconfirm).not.toHaveBeenCalled();
	});
});
```

────────────────────────────────────────────────────────────────────────────────

### Store Unit Tests: chat.spec.ts

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createChatStore } from './chat.svelte';

// Mock the API
vi.mock('$lib/api', () => ({
	api: {
		deleteMessage: vi.fn(),
		getSession: vi.fn(),
		truncateMessages: vi.fn()
	}
}));

describe('chatStore.deleteMessage', () => {
	let store: ReturnType<typeof createChatStore>;

	beforeEach(() => {
		store = createChatStore();
		// Load some test messages
		store.messages = [
			{ role: 'user', content: 'Hello', turn_id: 'user-1' },
			{ role: 'assistant', content: 'Hi', turn_id: 'asst-1' }
		];
	});

	it('removes message optimistically before API call', async () => {
		const { api } = await import('$lib/api');
		// Make API hang
		vi.mocked(api.deleteMessage).mockReturnValue(new Promise(() => {}));

		const promise = store.deleteMessage('asst-1');

		// Message should be removed immediately
		expect(store.messages).toHaveLength(1);
		expect(store.messages[0].turn_id).toBe('user-1');
	});

	it('rolls back on API failure', async () => {
		const { api } = await import('$lib/api');
		vi.mocked(api.deleteMessage).mockRejectedValue(new Error('Network error'));

		await store.deleteMessage('asst-1');

		// Messages should be restored
		expect(store.messages).toHaveLength(2);
		expect(store.editState.status).toBe('error');
	});

	it('auto-promotes to pair-delete for user message with assistant reply', async () => {
		const { api } = await import('$lib/api');
		vi.mocked(api.deleteMessage).mockResolvedValue({
			deleted: true,
			turn_id: 'user-1',
			delete_pair: true
		});

		await store.deleteMessage('user-1');

		// Both messages should be removed
		expect(store.messages).toHaveLength(0);
		// API should be called with deletePair=true
		expect(api.deleteMessage).toHaveBeenCalledWith(expect.any(String), 'user-1', true);
	});

	it('does not auto-promote for assistant message', async () => {
		const { api } = await import('$lib/api');
		vi.mocked(api.deleteMessage).mockResolvedValue({
			deleted: true,
			turn_id: 'asst-1',
			delete_pair: false
		});

		await store.deleteMessage('asst-1');

		// Only assistant message removed
		expect(store.messages).toHaveLength(1);
		expect(api.deleteMessage).toHaveBeenCalledWith(expect.any(String), 'asst-1', false);
	});

	it('cancels edit when deleting the message being edited', async () => {
		const { api } = await import('$lib/api');
		vi.mocked(api.deleteMessage).mockResolvedValue({
			deleted: true,
			turn_id: 'user-1',
			delete_pair: true
		});

		// Start editing user-1
		store.startEditing('user-1');
		expect(store.editingTurnId).toBe('user-1');

		// Delete user-1
		await store.deleteMessage('user-1');

		// Edit should be cancelled
		expect(store.editingTurnId).toBeNull();
	});

	it('blocks concurrent delete operations', async () => {
		const { api } = await import('$lib/api');
		// Make first API hang
		vi.mocked(api.deleteMessage).mockReturnValue(new Promise(() => {}));

		// Start first delete
		const promise1 = store.deleteMessage('user-1');
		expect(store.editState.status).toBe('loading');

		// Try second delete - should be blocked
		await store.deleteMessage('asst-1');

		// API should only be called once
		expect(api.deleteMessage).toHaveBeenCalledOnce();
	});
});
```

────────────────────────────────────────────────────────────────────────────────

2.  E2E Tests (Playwright)

### Test File Structure

```
  e2e/
  ├── fixtures/
  │   └── seed.ts              # Test data helpers
  ├── tests/
  │   ├── message-delete.spec.ts
  │   ├── message-edit.spec.ts
  │   └── truncate.spec.ts
  ├── page-objects/
  │   └── ChatPage.ts          # Page Object Model
  └── playwright.config.ts
```

────────────────────────────────────────────────────────────────────────────────

### Page Object Model: ChatPage.ts

```typescript
import { Page, Locator } from '@playwright/test';

export class ChatPage {
	readonly page: Page;
	readonly chatBubbles: Locator;
	readonly deleteButtons: Locator;
	readonly deletePairButtons: Locator;
	readonly editButtons: Locator;
	readonly confirmDialog: Locator;
	readonly confirmOkButton: Locator;
	readonly confirmCancelButton: Locator;
	readonly busyIndicator: Locator;
	readonly truncateBar: Locator;

	constructor(page: Page) {
		this.page = page;
		this.chatBubbles = page.getByTestId('chat-bubble');
		this.deleteButtons = page.getByTestId('delete-btn');
		this.deletePairButtons = page.getByTestId('delete-pair-btn');
		this.editButtons = page.getByTestId('edit-btn');
		this.confirmDialog = page.getByTestId('confirm-dialog');
		this.confirmOkButton = page.getByTestId('confirm-ok');
		this.confirmCancelButton = page.getByTestId('confirm-cancel');
		this.busyIndicator = page.getByTestId('app-busy');
		this.truncateBar = page.getByTestId('truncate-bar');
	}

	async goto() {
		await this.page.goto('http://localhost:5173');
	}

	async loadSession(title: string) {
		await this.page.locator(`aside button:has-text("${title}")`).click();
		await this.waitForMessagesLoaded();
	}

	async waitForMessagesLoaded() {
		await this.page.waitForSelector('[data-testid="chat-bubble"]');
	}

	async getMessageCount() {
		return this.chatBubbles.count();
	}

	async getMessageText(index: number) {
		return this.chatBubbles.nth(index).textContent();
	}

	async deleteMessage(index: number) {
		await this.deleteButtons.nth(index).click();
		await this.confirmOkButton.click();
		await this.waitForBusyComplete();
	}

	async deletePair(index: number) {
		await this.deletePairButtons.nth(index).click();
		await this.confirmOkButton.click();
		await this.waitForBusyComplete();
	}

	async waitForBusyComplete() {
		await this.busyIndicator.getAttribute('data-busy-recent', { value: 'false' });
	}

	async expectMessageCount(count: number) {
		await this.page.waitForFunction(
			(expected) => document.querySelectorAll('[data-testid="chat-bubble"]').length === expected,
			count
		);
	}

	async expectButtonDisabled(testid: string, index: number = 0) {
		const button = this.page.getByTestId(testid).nth(index);
		await button.waitFor({ state: 'attached' });
		const isDisabled = await button.isDisabled();
		if (!isDisabled) {
			throw new Error(`Expected ${testid}[${index}] to be disabled`);
		}
	}
}
```

────────────────────────────────────────────────────────────────────────────────

### E2E Test: message-delete.spec.ts

```typescript
import { test, expect } from '@playwright/test';
import { ChatPage } from '../page-objects/ChatPage';
import { seedSession } from '../fixtures/seed';

test.describe('Message Deletion', () => {
	let chatPage: ChatPage;

	test.beforeEach(async ({ page }) => {
		chatPage = new ChatPage(page);
	});

	test('delete single assistant message', async ({ page }) => {
		// Arrange - seed a session with 2 turn-pairs
		const session = await seedSession(page, { pairs: 2 });
		await chatPage.goto();
		await chatPage.loadSession(session.title);
		await chatPage.expectMessageCount(4);

		// Act - delete last assistant message
		await chatPage.deleteMessage(3);

		// Assert
		await chatPage.expectMessageCount(3);
	});

	test('delete pair removes user + assistant', async ({ page }) => {
		const session = await seedSession(page, { pairs: 2 });
		await chatPage.goto();
		await chatPage.loadSession(session.title);
		await chatPage.expectMessageCount(4);

		// Find index of first delete-pair button
		await chatPage.deletePair(0);

		await chatPage.expectMessageCount(2);
	});

	test('auto-promotes single delete to pair delete for user message', async ({ page }) => {
		const session = await seedSession(page, { pairs: 2 });
		await chatPage.goto();
		await chatPage.loadSession(session.title);
		await chatPage.expectMessageCount(4);

		// Click single delete on first user message (has assistant reply)
		await chatPage.deleteMessage(0);

		// Both user and assistant should be removed
		await chatPage.expectMessageCount(2);
	});

	test('cancel delete does not remove message', async ({ page }) => {
		const session = await seedSession(page, { pairs: 2 });
		await chatPage.goto();
		await chatPage.loadSession(session.title);

		// Click delete but cancel
		await chatPage.deleteButtons.first().click();
		await chatPage.confirmCancelButton.click();

		// Messages should remain
		await chatPage.expectMessageCount(4);
	});

	test('handles API error gracefully', async ({ page }) => {
		const session = await seedSession(page, { pairs: 1 });
		await chatPage.goto();
		await chatPage.loadSession(session.title);

		// Intercept API to return error
		await page.route('**/api/sessions/*/messages/*', (route) => {
			route.fulfill({ status: 500, body: 'Server error' });
		});

		// Attempt delete
		await chatPage.deleteButtons.first().click();
		await chatPage.confirmOkButton.click();

		// Wait for error state
		await page.waitForSelector('[role="alert"]');

		// Messages should be restored (rollback)
		await chatPage.expectMessageCount(2);
	});
});
```

────────────────────────────────────────────────────────────────────────────────

3.  Test Coverage Matrix

```
 ┌────────────────────────┬───────────────────────────────────┬───────────────────────────────┬──────────────────────┐
 │ Feature                │ Component Test                    │ E2E Test                      │ Notes                │
 ├────────────────────────┼───────────────────────────────────┼───────────────────────────────┼──────────────────────┤
 │ Delete single message  │ ✅ Calls ondelete with correct    │ ✅ Full flow with API         │ Component mocks API  │
 │                        │ turn_id                           │                               │                      │
 ├────────────────────────┼───────────────────────────────────┼───────────────────────────────┼──────────────────────┤
 │ Delete pair            │ ✅ Shows button only for          │ ✅ Removes both messages      │                      │
 │                        │ user+assistant                    │                               │                      │
 ├────────────────────────┼───────────────────────────────────┼───────────────────────────────┼──────────────────────┤
 │ Auto-promote           │ ✅ Store logic tested in unit     │ ✅ Verify 4→2 messages        │ Component test is    │
 │                        │ test                              │                               │ faster               │
 ├────────────────────────┼───────────────────────────────────┼───────────────────────────────┼──────────────────────┤
 │ Button disabled        │ ✅ Direct DOM assertion           │ ⚠️ Hard to test (timing)      │ Component test wins  │
 │ (isBusy)               │                                   │                               │                      │
 ├────────────────────────┼───────────────────────────────────┼───────────────────────────────┼──────────────────────┤
 │ Confirm dialog         │ ✅ All interactions tested        │ ✅ Used in delete flow        │                      │
 ├────────────────────────┼───────────────────────────────────┼───────────────────────────────┼──────────────────────┤
 │ Optimistic update      │ ✅ Store removes before API       │ ✅ UI updates instantly       │                      │
 ├────────────────────────┼───────────────────────────────────┼───────────────────────────────┼──────────────────────┤
 │ Rollback on error      │ ✅ Store restores on failure      │ ✅ Intercept API, verify      │                      │
 │                        │                                   │ restore                       │                      │
 ├────────────────────────┼───────────────────────────────────┼───────────────────────────────┼──────────────────────┤
 │ Cancel edit on delete  │ ✅ Store cancels editingTurnId    │ ✅ Open editor, delete,       │                      │
 │                        │                                   │ verify close                  │                      │
 └────────────────────────┴───────────────────────────────────┴───────────────────────────────┴──────────────────────┘
```

4.  Recommended Test Distribution

```
 ┌──────────────────┬───────┬───────────────────────────────────────────┬────────┐
 │ Layer            │ Count │ Focus                                     │ Speed  │
 ├──────────────────┼───────┼───────────────────────────────────────────┼────────┤
 │ Store unit tests │ ~15   │ Business logic, state transitions         │ <100ms │
 ├──────────────────┼───────┼───────────────────────────────────────────┼────────┤
 │ Component tests  │ ~25   │ Rendering, props, events, disabled states │ <500ms │
 ├──────────────────┼───────┼───────────────────────────────────────────┼────────┤
 │ E2E tests        │ ~10   │ Critical user flows, API integration      │ <30s   │
 └──────────────────┴───────┴───────────────────────────────────────────┴────────┘
```

5.  Key Insight

The "button disabled during operation" problem is a component test concern, not an E2E concern.

```typescript
// ✅ Component test - instant, reliable
it('disables buttons when isBusy=true', () => {
	render(ChatMessageList, { props: { ...defaultProps, isBusy: true } });
	expect(screen.getByTestId('delete-btn')).toBeDisabled();
});

// ❌ E2E test - timing nightmare
test('buttons disabled during delete', async ({ page }) => {
	// Optimistic update happens in <1ms
	// By the time we check, operation is complete
	// This test will be flaky
});
```

Best practice: Test the contract (component accepts isBusy prop and disables buttons) at the component level. Test  
 the integration (delete flow works end-to-end) at the E2E level. Don't try to test timing-sensitive UI states in E2E  
 tests.
