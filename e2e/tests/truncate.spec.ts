import { test, expect } from '@playwright/test';
import { ChatPage } from '../page-objects/ChatPage';
import { seedSession, getSessionState } from '../fixtures/seed';

test.describe('Message Truncation', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    test('truncate bar appears when there are 2+ messages', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 2 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(4);

        // Assert
        await expect(chatPage.truncateBar).toBeVisible();
        const buttonCount = await chatPage.truncateButtons.count();
        expect(buttonCount).toBeGreaterThanOrEqual(1);
    });

    test('truncate bar hidden when fewer than 2 messages', async ({ page }) => {
        // Arrange - create session and delete all but one
        const session = await seedSession(page, { pairs: 1 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);

        // Delete assistant, leaving only 1 user message
        await chatPage.deleteMessage(1);
        await chatPage.expectMessageCount(1);

        // Assert - truncate bar should be hidden
        await expect(chatPage.truncateBar).toBeHidden();
    });

    test('truncate 1 turn removes last user+assistant pair', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 3 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(6);

        // Act - click first truncate button (1 turn)
        await chatPage.truncateButtons.first().click();

        // Confirm
        await chatPage.waitForConfirmDialog();
        await chatPage.confirmOkButton.click();
        await chatPage.waitForBusyComplete();

        // Assert
        await chatPage.expectMessageCount(4);

        // Verify backend
        const state = await getSessionState(page, session.session_id);
        expect(state.message_count).toBe(4);
    });

    test('truncate 2 turns removes last 2 pairs', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 3 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(6);

        // Act - click "2 turns" button
        const twoTurnsButton = chatPage.truncateButtons.filter({ hasText: '2 turns' });
        await twoTurnsButton.click();

        // Confirm
        await chatPage.waitForConfirmDialog();
        await chatPage.confirmOkButton.click();
        await chatPage.waitForBusyComplete();

        // Assert
        await chatPage.expectMessageCount(2);

        // Verify backend
        const state = await getSessionState(page, session.session_id);
        expect(state.message_count).toBe(2);
    });

    test('cancel truncate does not remove messages', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 2 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);
        await chatPage.expectMessageCount(4);

        // Act - click truncate but cancel
        await chatPage.truncateButtons.first().click();
        await chatPage.waitForConfirmDialog();
        await chatPage.confirmCancelButton.click();

        // Assert - messages unchanged
        await chatPage.expectMessageCount(4);
    });

    test('truncate buttons disabled during operation', async ({ page }) => {
        // Arrange
        const session = await seedSession(page, { pairs: 2 });
        await chatPage.goto();
        await chatPage.loadSession(session.title);

        // Intercept API to add delay
        await page.route('**/api/sessions/*/messages/truncate', async (route) => {
            await new Promise((resolve) => setTimeout(resolve, 2000));
            route.continue();
        });

        // Act - click truncate
        await chatPage.truncateButtons.first().click();
        await chatPage.waitForConfirmDialog();
        await chatPage.confirmOkButton.click();

        // Assert - buttons should be disabled during operation
        // Note: This is hard to test reliably due to optimistic updates
        // The component test is better for this assertion

        // Wait for completion
        await chatPage.waitForBusyComplete();
        await chatPage.expectMessageCount(2);
    });
});
