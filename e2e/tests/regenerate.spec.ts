import { test, expect } from '@playwright/test';
import { ChatPage } from '../page-objects/ChatPage';
import { seedSession, getSessionState } from '../fixtures/seed';

test.describe('Message Regeneration', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    // ── Regenerate Button Visibility ───────────────────────────────

    test('regenerate button appears on last assistant message', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 2 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(4);

        // Assert - regenerate button should be visible on last assistant
        const regenerateButtons = page.getByTestId('regenerate-btn');
        await expect(regenerateButtons).toHaveCount(1);
    });

    test('regenerate button does not appear on non-last assistant messages', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 3 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(6);

        // Assert - only one regenerate button (on the last assistant)
        const regenerateButtons = page.getByTestId('regenerate-btn');
        await expect(regenerateButtons).toHaveCount(1);
    });

    test('regenerate button does not appear on user messages', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 1 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);

        // Assert - regenerate button should not be on user messages
        const userBubble = page.getByTestId('chat-bubble').first();
        const regenerateInUser = userBubble.getByTestId('regenerate-btn');
        await expect(regenerateInUser).toHaveCount(0);
    });

    // ── Regenerate Action ──────────────────────────────────────────

    test('regenerate replaces last assistant message', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 1 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(2);

        // Act - click regenerate
        const regenerateBtn = page.getByTestId('regenerate-btn');
        await regenerateBtn.click();

        // Wait for completion
        await chatPage.waitForBusyComplete();

        // Assert - still 2 messages (user + new assistant)
        await chatPage.expectMessageCount(2);
    });

    test('regenerate does not appear when no assistant messages', async ({ page }) => {
        // Arrange - seed and delete all assistant messages
        const session = await seedSession(page, { pairs: 1 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(2);

        // Delete assistant message
        await chatPage.deleteMessage(1);
        await chatPage.expectMessageCount(1);

        // Assert - no regenerate button
        const regenerateButtons = page.getByTestId('regenerate-btn');
        await expect(regenerateButtons).toHaveCount(0);
    });
});
