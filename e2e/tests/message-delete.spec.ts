import { test, expect } from '@playwright/test';
import { ChatPage } from '../page-objects/ChatPage';
import { seedSession, deleteSession, getSessionState, SeedResult } from '../fixtures/seed';

test.describe('Message Deletion', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    // ── Single Delete ──────────────────────────────────────────────

    test('delete single assistant message', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 2 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(4);

        // Act - delete last assistant message
        await chatPage.deleteMessage(3);

        // Assert - one message removed
        await chatPage.expectMessageCount(3);

        // Verify remaining messages are from first pair
        const state = await getSessionState(page, session.session_id);
        expect(state.message_count).toBe(3);
        expect(state.roles).toEqual(['user', 'assistant', 'user']);
    });

    test('delete single user message without assistant reply', async ({ page }) => {
        // Arrange - create session with 1 pair, delete assistant first
        const session = await seedSession(page, { pairs: 1 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(2);

        // Delete assistant first
        await chatPage.deleteMessage(1);
        await chatPage.expectMessageCount(1);

        // Now delete the lone user message
        await chatPage.deleteMessage(0);
        await chatPage.expectMessageCount(0);
    });

    // ── Smart Delete (auto-promote for user messages with reply) ───

    test('smart delete on user message removes both user + assistant', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 2 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(4);

        // Act - click delete on first user message (has assistant reply)
        // The app should auto-promote to pair delete
        await chatPage.deleteMessage(0);

        // Assert - both user and assistant removed
        await chatPage.expectMessageCount(2);

        // Verify backend confirms pair deletion
        const state = await getSessionState(page, session.session_id);
        expect(state.message_count).toBe(2);
        expect(state.roles[0]).toBe('user'); // Second pair's user
        expect(state.roles[1]).toBe('assistant'); // Second pair's assistant
    });

    test('only one more-options button per message (actions in dropdown)', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 2 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);

        // Assert - each message should have exactly one more-options button
        const moreOptionsCount = await chatPage.moreOptionsButtons.count();
        expect(moreOptionsCount).toBe(4); // One per message
    });

    // ── Cancel Delete ──────────────────────────────────────────────

    test('cancel delete does not remove message', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 2 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(4);

        // Act - click delete but cancel
        await chatPage.cancelDelete(0);

        // Assert - messages remain unchanged
        await chatPage.expectMessageCount(4);
        await chatPage.expectConfirmDialogHidden();
    });

    // ── Confirm Dialog ─────────────────────────────────────────────

    test('confirm dialog shows correct message for delete', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 1 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);

        // Act - open dropdown and click delete
        await chatPage.moreOptionsButtons.first().click();
        await page.waitForSelector('[data-testid="delete-btn"]', { state: 'visible' });
        await chatPage.deleteButtons.first().click();

        // Assert
        await chatPage.expectConfirmDialogVisible();
        await expect(chatPage.confirmDialog).toContainText('Delete this message');
    });

    test('confirm dialog closes on escape key', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 1 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);

        // Act - open dropdown and click delete
        await chatPage.moreOptionsButtons.first().click();
        await page.waitForSelector('[data-testid="delete-btn"]', { state: 'visible' });
        await chatPage.deleteButtons.first().click();
        await chatPage.expectConfirmDialogVisible();
        await page.keyboard.press('Escape');

        // Assert
        await chatPage.expectConfirmDialogHidden();
        await chatPage.expectMessageCount(2); // Unchanged
    });

    // ── Error Handling ─────────────────────────────────────────────

    test('rollback on API error restores messages', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 1 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(2);

        // Intercept API to return error
        await page.route('**/api/sessions/*/messages/**', (route) => {
            if (route.request().method() === 'DELETE') {
                route.fulfill({
                    status: 500,
                    contentType: 'application/json',
                    body: JSON.stringify({ detail: 'Test error' })
                });
            } else {
                route.continue();
            }
        });

        // Act - attempt delete (open dropdown first)
        await chatPage.moreOptionsButtons.first().click();
        await page.waitForSelector('[data-testid="delete-btn"]', { state: 'visible' });
        await chatPage.deleteButtons.first().click();
        await chatPage.confirmOkButton.click();

        // Wait for error to be handled - check for error toast or message count stability
        // This replaces the fragile waitForTimeout(1000)
        await page.waitForFunction(
            () => {
                // Check if error toast appeared or if messages are still present
                const errorToast = document.querySelector('[data-testid="error-toast"]');
                const messageCount = document.querySelectorAll(
                    '[data-testid="chat-bubble"]'
                ).length;
                return errorToast || messageCount === 2;
            },
            { timeout: 5000 }
        );

        // Assert - messages restored (rollback)
        await chatPage.expectMessageCount(2);
    });

    // ── Sequential Deletes ─────────────────────────────────────────

    test('can delete multiple messages sequentially', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 3 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(6);

        // Act - delete assistant messages one by one
        await chatPage.deleteMessage(5); // Last assistant
        await chatPage.expectMessageCount(5);

        await chatPage.deleteMessage(3); // Second assistant
        await chatPage.expectMessageCount(4);

        await chatPage.deleteMessage(1); // First assistant
        await chatPage.expectMessageCount(3);

        // Verify backend state
        const state = await getSessionState(page, session.session_id);
        expect(state.message_count).toBe(3);
        expect(state.roles).toEqual(['user', 'user', 'user']);
    });
});
